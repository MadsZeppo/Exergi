#!/usr/bin/env python3
"""Render dependency-light PNG plots from frozen H&M benchmark artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmarks" / "hm_day1"
PLOTS = SOURCE / "plots"
WIDTH, HEIGHT = 1200, 720


def canvas(title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f7f6f3")
    draw = ImageDraw.Draw(image)
    draw.text((60, 38), title, fill="#16181c", font=ImageFont.load_default(28))
    draw.text((60, 78), subtitle, fill="#5f646c", font=ImageFont.load_default(16))
    return image, draw


def axes(draw: ImageDraw.ImageDraw, x0: int = 100, y0: int = 620) -> None:
    draw.line((x0, 120, x0, y0), fill="#777777", width=2)
    draw.line((x0, y0, 1130, y0), fill="#777777", width=2)


def calibration(months: int) -> None:
    image, draw = canvas(
        f"Calibration — {months} months imported history",
        "Final untouched 30-day window; dashed diagonal is perfect calibration",
    )
    axes(draw)
    draw.line((100, 620, 1130, 120), fill="#999999", width=2)
    path = SOURCE / f"calibration_{months}m.json"
    if not path.exists():
        draw.text((300, 330), "NOT EVALUABLE — insufficient history coverage", fill="#b23c3c")
    else:
        rows = json.loads(path.read_text())
        points = []
        for row in rows:
            x = 100 + int(float(row["predicted_rate"]) * 1030)
            y = 620 - int(float(row["actual_rate"]) * 500)
            points.append((x, y))
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#2f5fe0")
        if len(points) > 1:
            draw.line(points, fill="#2f5fe0", width=3)
    draw.text((500, 660), "Predicted repeat rate", fill="#16181c")
    draw.text((12, 330), "Actual", fill="#16181c")
    image.save(PLOTS / f"calibration_{months}m.png")


def learning_curve() -> None:
    data = pd.read_csv(SOURCE / "history_learning_curve.csv")
    image, draw = canvas(
        "History-length learning curve",
        "12m is absent because RelBench cannot supply 12m history plus a full 30d future",
    )
    axes(draw)
    for metric, color, scale in (("auroc", "#2f5fe0", 1.0), ("lift_at_10", "#1f7a4d", 3.0)):
        points = []
        for row in data.to_dict("records"):
            x = 100 + int((float(row["history_months"]) - 5) / 8 * 1030)
            y = 620 - int(float(row[metric]) / scale * 500)
            points.append((x, y))
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=color)
            label = f"{float(row[metric]):.2f}" + ("x" if metric == "lift_at_10" else "")
            draw.text((x + 12, y - 8), label, fill=color)
            if metric == "auroc":
                draw.text((x - 8, 635), f"{int(row['history_months'])}m", fill="#16181c")
        draw.line(points, fill=color, width=4)
    draw.text((920, 150), "Blue: AUROC", fill="#2f5fe0")
    draw.text((920, 180), "Green: top-10 lift / 3", fill="#1f7a4d")
    image.save(PLOTS / "history_learning_curve.png")


def buyers() -> None:
    data = pd.read_csv(SOURCE / "history_learning_curve.csv")
    image, draw = canvas("Predicted versus actual repeat buyers", "Final untouched 30-day window")
    max_value = max(data["repeat_buyers_predicted"].max(), data["repeat_buyers_actual"].max())
    for index, row in enumerate(data.to_dict("records")):
        y = 210 + index * 210
        pred = int(float(row["repeat_buyers_predicted"]) / max_value * 850)
        actual = int(float(row["repeat_buyers_actual"]) / max_value * 850)
        draw.text((50, y + 25), f"{int(row['history_months'])}m", fill="#16181c")
        draw.rectangle((150, y, 150 + pred, y + 45), fill="#2f5fe0")
        draw.rectangle((150, y + 58, 150 + actual, y + 103), fill="#1f7a4d")
        draw.text(
            (160 + pred, y + 12),
            f"pred {row['repeat_buyers_predicted']:.0f}",
            fill="#16181c",
        )
        draw.text(
            (160 + actual, y + 70),
            f"actual {row['repeat_buyers_actual']:.0f}",
            fill="#16181c",
        )
    image.save(PLOTS / "predicted_vs_actual_buyers.png")


def lift() -> None:
    data = pd.read_csv(SOURCE / "history_learning_curve.csv")
    image, draw = canvas(
        "Top-decile lift", "Known-customer repeat propensity; not causal targeting value"
    )
    for index, row in enumerate(data.to_dict("records")):
        x = 280 + index * 430
        height = int(float(row["lift_at_10"]) / 3 * 450)
        draw.rectangle((x, 610 - height, x + 170, 610), fill="#2f5fe0")
        draw.text((x + 45, 625), f"{int(row['history_months'])}m", fill="#16181c")
        draw.text((x + 45, 580 - height), f"{row['lift_at_10']:.2f}x", fill="#16181c")
    image.save(PLOTS / "decile_lift.png")


def main() -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    for months in (6, 9, 12):
        calibration(months)
    learning_curve()
    buyers()
    lift()


if __name__ == "__main__":
    main()
