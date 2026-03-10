#!/usr/bin/env python3
"""Generate a formula cloud image from LaTeX formulas or formula images."""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


@dataclass
class FormulaItem:
    """A rendered formula and its weight used to size it in the cloud."""

    image: Image.Image
    weight: float
    label: str
    repeat: int = 1


@dataclass
class PlacedFormula:
    image: Image.Image
    x: int
    y: int


class FormulaCloudGenerator:
    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        background: tuple[int, int, int, int] = (255, 255, 255, 255),
        random_seed: int | None = 42,
        allowed_angles: tuple[int, ...] = (0, 45, 90, 135, 180, 225, 270, 315),
        shape: str = "rectangle",
    ) -> None:
        self.width = width
        self.height = height
        self.background = background
        self.rng = random.Random(random_seed)
        self.allowed_angles = allowed_angles
        self.shape = shape
        self.shape_mask = self._build_shape_mask(shape)

    def _build_shape_mask(self, shape: str) -> np.ndarray:
        yy, xx = np.indices((self.height, self.width))
        cx = (self.width - 1) / 2
        cy = (self.height - 1) / 2

        if shape == "rectangle":
            return np.ones((self.height, self.width), dtype=bool)

        if shape == "square":
            half_side = min(self.width, self.height) / 2
            return (np.abs(xx - cx) <= half_side) & (np.abs(yy - cy) <= half_side)

        if shape == "circle":
            radius = min(self.width, self.height) / 2
            return ((xx - cx) ** 2 + (yy - cy) ** 2) <= radius**2

        if shape == "diamond":
            radius = min(self.width, self.height) / 2
            return (np.abs(xx - cx) + np.abs(yy - cy)) <= radius

        raise ValueError(f"Unsupported shape: {shape}")

    @staticmethod
    def render_latex_to_image(
        latex: str,
        fontsize: int = 40,
        dpi: int = 300,
        color: str = "black",
    ) -> Image.Image:
        """Render one LaTeX formula into a cropped RGBA image."""
        fig = plt.figure(figsize=(0.01, 0.01), dpi=dpi)
        text = fig.text(0, 0, f"${latex}$", fontsize=fontsize, color=color)
        fig.canvas.draw()

        bbox = text.get_window_extent()
        width_px, height_px = bbox.width, bbox.height

        fig.set_size_inches((width_px + 20) / dpi, (height_px + 20) / dpi)
        text.set_position((10 / dpi, 10 / dpi))

        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        plt.close(fig)

        pil = Image.fromarray(rgba).convert("RGBA")
        return FormulaCloudGenerator.trim_transparent_margin(pil)

    @staticmethod
    def trim_transparent_margin(image: Image.Image) -> Image.Image:
        alpha = image.split()[-1]
        bbox = alpha.getbbox()
        if bbox is None:
            return image
        return image.crop(bbox)

    @staticmethod
    def load_formula_image(path: Path) -> Image.Image:
        image = Image.open(path).convert("RGBA")
        return FormulaCloudGenerator.trim_transparent_margin(image)

    @staticmethod
    def scale_image(image: Image.Image, target_long_side: int) -> Image.Image:
        w, h = image.size
        if max(w, h) == target_long_side:
            return image
        ratio = target_long_side / max(w, h)
        new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
        return image.resize(new_size, Image.Resampling.LANCZOS)

    def _collides(self, mask: np.ndarray, x: int, y: int, alpha: np.ndarray) -> bool:
        h, w = alpha.shape
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            return True
        occupied = mask[y : y + h, x : x + w]
        available = self.shape_mask[y : y + h, x : x + w]
        pixels = alpha > 0
        if np.any(pixels & ~available):
            return True
        return np.any(pixels & occupied)

    def _transform_formula(self, image: Image.Image, target_size: int) -> Image.Image:
        scaled = self.scale_image(image, target_size)
        angle = self.rng.choice(self.allowed_angles)
        if angle == 0:
            return scaled
        return self.trim_transparent_margin(
            scaled.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        )

    def _place_one(self, mask: np.ndarray, image: Image.Image) -> PlacedFormula | None:
        alpha = np.array(image.split()[-1]) > 0
        h, w = alpha.shape

        center_x, center_y = self.width // 2, self.height // 2

        max_radius = int(math.hypot(self.width, self.height))
        angle = self.rng.random() * 2 * math.pi
        for radius in range(0, max_radius, 3):
            for _ in range(8):
                x = int(center_x + radius * math.cos(angle) - w / 2)
                y = int(center_y + radius * math.sin(angle) - h / 2)
                if not self._collides(mask, x, y, alpha):
                    region = mask[y : y + h, x : x + w]
                    region |= alpha
                    return PlacedFormula(image=image, x=x, y=y)
                angle += math.pi / 4
        return None

    def generate(self, items: Iterable[FormulaItem]) -> Image.Image:
        expanded_items: list[FormulaItem] = []
        for item in items:
            expanded_items.extend([item] * max(1, item.repeat))

        items_list = sorted(expanded_items, key=lambda t: t.weight, reverse=True)
        if not items_list:
            raise ValueError("No formulas/images provided.")

        max_size = min(self.width, self.height) // 3
        min_size = max(40, max_size // 6)
        max_weight = max(item.weight for item in items_list)
        min_weight = min(item.weight for item in items_list)
        weight_span = max(max_weight - min_weight, 1e-6)

        mask = np.zeros((self.height, self.width), dtype=bool)
        canvas = Image.new("RGBA", (self.width, self.height), self.background)

        placed = 0
        for item in items_list:
            normalized = (item.weight - min_weight) / weight_span
            target_size = int(min_size + normalized * (max_size - min_size))
            transformed = self._transform_formula(item.image, target_size)
            position = self._place_one(mask, transformed)
            if position:
                canvas.alpha_composite(position.image, (position.x, position.y))
                placed += 1

        if placed == 0:
            raise RuntimeError("Failed to place formulas, try a larger canvas.")
        return canvas


def load_items_from_json(json_path: Path) -> list[FormulaItem]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    items: list[FormulaItem] = []

    for item in data:
        weight = float(item.get("weight", 1.0))
        repeat = max(1, int(item.get("repeat", 1)))
        if "latex" in item:
            img = FormulaCloudGenerator.render_latex_to_image(
                item["latex"],
                fontsize=int(item.get("fontsize", 40)),
                color=item.get("color", "black"),
            )
            items.append(FormulaItem(img, weight, item["latex"], repeat=repeat))
        elif "image" in item:
            path = Path(item["image"])
            img = FormulaCloudGenerator.load_formula_image(path)
            items.append(FormulaItem(img, weight, str(path), repeat=repeat))
        else:
            raise ValueError("Each item must contain either 'latex' or 'image'.")

    return items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate formula cloud from LaTeX or images")
    parser.add_argument("--input", type=Path, required=True, help="JSON file describing formulas/images")
    parser.add_argument("--output", type=Path, default=Path("formula_cloud.png"), help="Output image")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--shape",
        type=str,
        choices=["rectangle", "square", "circle", "diamond"],
        default="rectangle",
        help="Cloud silhouette shape",
    )
    parser.add_argument(
        "--angles",
        type=str,
        default="0,45,90,135,180,225,270,315",
        help="Allowed rotation angles in degrees, comma-separated",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    items = load_items_from_json(args.input)

    angle_values = tuple(int(x.strip()) % 360 for x in args.angles.split(",") if x.strip())
    if not angle_values:
        raise ValueError("--angles must include at least one integer angle")

    generator = FormulaCloudGenerator(
        width=args.width,
        height=args.height,
        random_seed=args.seed,
        allowed_angles=angle_values,
        shape=args.shape,
    )
    result = generator.generate(items)
    result.save(args.output)
    print(f"Saved formula cloud: {args.output}")


if __name__ == "__main__":
    main()
