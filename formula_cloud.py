#!/usr/bin/env python3
"""Generate a formula cloud image from LaTeX formulas or formula images."""

from __future__ import annotations

import argparse
import io
import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
    center: tuple[float, float]


class FormulaCloudGenerator:
    MIN_LATEX_FONT_SIZE = 32

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

        if shape == "heart":
            margin = 0.88
            nx = ((xx - cx) / (self.width / 2)) / margin
            ny = ((cy - yy) / (self.height / 2)) / margin
            return ((nx**2 + ny**2 - 1) ** 3 - nx**2 * ny**3) <= 0

        raise ValueError(f"Unsupported shape: {shape}")

    @staticmethod
    def render_latex_to_image(
        latex: str,
        fontsize: int = 40,
        dpi: int = 300,
        color: str = "black",
    ) -> Image.Image:
        """Render one LaTeX formula into a cropped RGBA image."""
        import matplotlib.pyplot as plt
        from matplotlib.transforms import Bbox

        latex = FormulaCloudGenerator.normalize_latex_input(latex)
        fontsize = max(FormulaCloudGenerator.MIN_LATEX_FONT_SIZE, fontsize)
        fig_width = max(2.0, fontsize / 10)
        fig_height = max(1.6, fontsize / 12)
        fig = plt.figure(figsize=(fig_width, fig_height), dpi=dpi)
        fig.patch.set_alpha(0)
        text = fig.text(
            0.5,
            0.5,
            f"${latex}$",
            fontsize=fontsize,
            color=color,
            ha="center",
            va="center",
        )
        fig.canvas.draw()

        renderer = fig.canvas.get_renderer()
        bbox_pixels = text.get_window_extent(renderer=renderer).expanded(1.18, 1.3)
        bbox_inches = Bbox.from_extents(*(bbox_pixels.extents / dpi))

        output = io.BytesIO()
        fig.savefig(
            output,
            format="png",
            dpi=dpi,
            transparent=True,
            bbox_inches=bbox_inches,
            pad_inches=0,
        )
        plt.close(fig)
        output.seek(0)

        pil = Image.open(output).convert("RGBA")
        edge_padding = max(4, fontsize // 10)
        return FormulaCloudGenerator.trim_transparent_margin(pil, padding=edge_padding)

    @staticmethod
    def normalize_latex_input(latex: str) -> str:
        """Normalize user-provided LaTeX text.

        - Strip optional surrounding `$...$` wrappers.
        - Collapse accidental over-escaped slashes (`\\\...` -> `\\`).
        """
        normalized = latex.strip()
        if normalized.startswith("$") and normalized.endswith("$") and len(normalized) >= 2:
            normalized = normalized[1:-1].strip()
        # Keep canonical LaTeX line breaks ("\\") intact while reducing
        # accidental over-escaping from JSON strings.
        normalized = re.sub(r"\\{3,}", r"\\\\", normalized)

        matrix_wrappers = {
            "matrix": ("", ""),
            "bmatrix": (r"\left[", r"\right]"),
            "pmatrix": (r"\left(", r"\right)"),
            "Bmatrix": (r"\left\{", r"\right\}"),
            "vmatrix": (r"\left|", r"\right|"),
            "Vmatrix": (r"\left\|", r"\right\|"),
            "cases": (r"\left\{", r"\right."),
        }
        for env, (left_wrap, right_wrap) in matrix_wrappers.items():
            pattern = re.compile(rf"\\begin\{{{env}\}}(.*?)\\end\{{{env}\}}", re.DOTALL)

            def _replace_env(match: re.Match[str]) -> str:
                body = match.group(1)
                # Accept a common typo where matrix rows are separated by a
                # single backslash ("\\ ") instead of canonical "\\\\".
                body = re.sub(r"(?<!\\)\\(?![A-Za-z\\])", r"\\\\", body)
                # Convert primitive row breaks to canonical matrix row breaks.
                body = re.sub(r"\\cr\s*", r"\\\\ ", body)
                body = body.strip()
                if body.endswith(r"\\"):
                    body = body[: -len(r"\\")].rstrip()
                matrix_core = rf"\matrix{{{body}}}"
                return f"{left_wrap}{matrix_core}{right_wrap}" if left_wrap or right_wrap else matrix_core

            normalized = pattern.sub(_replace_env, normalized)

        normalized = re.sub(
            r"\\system\{([^}]*)\}",
            lambda m: "\\begin{cases}" + m.group(1).replace(";", r"\\") + "\\end{cases}",
            normalized,
        )
        return normalized

    @staticmethod
    def trim_transparent_margin(image: Image.Image, padding: int = 0) -> Image.Image:
        alpha = image.split()[-1]
        bbox = alpha.getbbox()
        if bbox is None:
            return image
        left, top, right, bottom = bbox
        if padding > 0:
            left = max(0, left - padding)
            top = max(0, top - padding)
            right = min(image.width, right + padding)
            bottom = min(image.height, bottom + padding)
        return image.crop((left, top, right, bottom))

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

    def _is_far_enough_from_same_label(
        self,
        center: tuple[float, float],
        same_label_centers: list[tuple[float, float]],
        min_distance: float,
    ) -> bool:
        return all(
            math.hypot(center[0] - old_center[0], center[1] - old_center[1]) >= min_distance
            for old_center in same_label_centers
        )

    def _place_one(
        self,
        mask: np.ndarray,
        image: Image.Image,
        same_label_centers: list[tuple[float, float]],
    ) -> PlacedFormula | None:
        alpha = np.array(image.split()[-1]) > 0
        h, w = alpha.shape

        center_x, center_y = self.width // 2, self.height // 2
        min_distance = max(w, h) * 1.5

        max_radius = int(math.hypot(self.width, self.height))
        angle = self.rng.random() * 2 * math.pi
        for radius in range(0, max_radius, 3):
            for _ in range(8):
                x = int(center_x + radius * math.cos(angle) - w / 2)
                y = int(center_y + radius * math.sin(angle) - h / 2)
                candidate_center = (x + w / 2, y + h / 2)
                if not self._collides(mask, x, y, alpha) and self._is_far_enough_from_same_label(
                    candidate_center,
                    same_label_centers,
                    min_distance,
                ):
                    region = mask[y : y + h, x : x + w]
                    region |= alpha
                    return PlacedFormula(image=image, x=x, y=y, center=candidate_center)
                angle += math.pi / 4
        return None

    def generate(self, items: Iterable[FormulaItem]) -> Image.Image:
        base_items = list(items)
        if not base_items:
            raise ValueError("No formulas/images provided.")

        max_weight = max(item.weight for item in base_items)
        min_weight = min(item.weight for item in base_items)
        weight_span = max(max_weight - min_weight, 1e-6)

        expanded_items: list[FormulaItem] = []
        max_inverse_repeat = 6
        for item in base_items:
            # Higher weight -> fewer copies. Lower weight -> more copies.
            inverse_normalized = (max_weight - item.weight) / weight_span
            inverse_multiplier = 1 + inverse_normalized * (max_inverse_repeat - 1)
            effective_repeat = max(1, int(round(item.repeat * inverse_multiplier)))
            expanded_items.extend([item] * effective_repeat)

        items_list = sorted(expanded_items, key=lambda t: t.weight, reverse=True)

        max_size = min(self.width, self.height) // 3
        min_size = max(90, max_size // 4)

        mask = np.zeros((self.height, self.width), dtype=bool)
        canvas = Image.new("RGBA", (self.width, self.height), self.background)
        centers_by_label: dict[str, list[tuple[float, float]]] = {}

        placed = 0
        for item in items_list:
            normalized = (item.weight - min_weight) / weight_span
            target_size = int(min_size + normalized * (max_size - min_size))
            transformed = self._transform_formula(item.image, target_size)
            same_label_centers = centers_by_label.setdefault(item.label, [])
            position = self._place_one(mask, transformed, same_label_centers)
            if position:
                canvas.alpha_composite(position.image, (position.x, position.y))
                same_label_centers.append(position.center)
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
        choices=["rectangle", "square", "circle", "diamond", "heart"],
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
