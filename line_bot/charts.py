"""
K 線圖產生（台銀牌告日線近似 OHLC）+ MA20。
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

INK = "#0B1F1C"
PAPER = "#FAFAF8"
ACCENT = "#1F6F63"
MUTED = "#6B7280"
GRID = "#E8EAE9"
UP = "#0F766E"
DOWN = "#B91C1C"
HEADER = "#0B1F1C"
MA_COLOR = "#D97706"


def _to_ohlc(records: list[dict], limit: int = 40) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records).copy()
    if "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("spot_buy", "spot_sell", "cash_buy", "cash_sell"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = float("nan")

    spot_ok = df["spot_sell"].fillna(0).ne(0).sum() >= max(5, len(df) // 4)
    if spot_ok:
        df["open"] = df["spot_buy"].fillna(df["spot_sell"])
        df["high"] = df[["cash_sell", "spot_sell", "spot_buy"]].max(axis=1)
        df["low"] = df[["cash_buy", "spot_sell", "spot_buy"]].min(axis=1)
        df["close"] = df["spot_sell"]
    else:
        df["open"] = df["cash_buy"].fillna(df["cash_sell"])
        df["high"] = df[["cash_sell", "cash_buy"]].max(axis=1)
        df["low"] = df[["cash_buy", "cash_sell"]].min(axis=1)
        df["close"] = df["cash_sell"]

    df = df.dropna(subset=["date", "close"]).sort_values("date")
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"] = df[["low", "open", "close"]].min(axis=1)
    df["MA20"] = df["close"].rolling(20).mean()
    return df.tail(limit).reset_index(drop=True)


def generate_kline_png(
    records: list[dict],
    title: str = "",
    limit: int = 40,
) -> Optional[bytes]:
    """近 N 日 K 線 + MA20 + 最新收／區間高低標註。"""
    df = _to_ohlc(records, limit=limit)
    if len(df) < 5:
        logger.warning("K 線資料不足: %d", len(df))
        return None

    width, height = 800, 400
    margin_l, margin_r, margin_t, margin_b = 58, 20, 52, 52
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    img = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15
        )
        font_axis = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11
        )
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10
        )
    except OSError:
        try:
            font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
            font_axis = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11)
            font_small = font_axis
        except OSError:
            font_title = font_axis = font_small = ImageFont.load_default()

    last = df.iloc[-1]
    hi = float(df["high"].max())
    lo = float(df["low"].min())
    close = float(last["close"])
    draw.rectangle([0, 0, width, 44], fill=HEADER)
    label = title or "K-Line"
    draw.text((14, 8), label, fill="#7A9E96", font=font_title)
    draw.text(
        (14, 26),
        f"Close {close:.4f}  ·  High {hi:.4f}  ·  Low {lo:.4f}  ·  MA20",
        fill="#A7C4BE",
        font=font_small,
    )

    ymin, ymax = lo, hi
    if ymax <= ymin:
        ymax = ymin + 1e-6
    pad = (ymax - ymin) * 0.1
    ymin -= pad
    ymax += pad

    def y_of(v: float) -> float:
        return margin_t + (1 - (v - ymin) / (ymax - ymin)) * plot_h

    for i in range(5):
        gy = margin_t + plot_h * i / 4
        draw.line([(margin_l, gy), (width - margin_r, gy)], fill=GRID, width=1)
        val = ymax - (ymax - ymin) * i / 4
        draw.text((6, gy - 6), f"{val:.4f}", fill=MUTED, font=font_axis)

    n = len(df)
    slot = plot_w / n
    body_w = max(3, min(12, slot * 0.55))

    for i, row in df.iterrows():
        x = margin_l + (i + 0.5) * slot
        o, h, l, c = map(float, (row["open"], row["high"], row["low"], row["close"]))
        color = UP if c >= o else DOWN
        draw.line([(x, y_of(h)), (x, y_of(l))], fill=color, width=2)
        top, bot = min(y_of(o), y_of(c)), max(y_of(o), y_of(c))
        if abs(bot - top) < 1:
            bot = top + 1
        draw.rectangle(
            [x - body_w / 2, top, x + body_w / 2, bot],
            fill=color,
            outline=color,
        )

    # MA20
    ma_pts = []
    for i, row in df.iterrows():
        if pd.notna(row.get("MA20")):
            x = margin_l + (i + 0.5) * slot
            ma_pts.append((x, y_of(float(row["MA20"]))))
    if len(ma_pts) >= 2:
        draw.line(ma_pts, fill=MA_COLOR, width=2)

    for idx in (0, n // 2, n - 1):
        x = margin_l + (idx + 0.5) * slot
        ds = df.iloc[idx]["date"].strftime("%m/%d")
        draw.text((x - 12, height - 36), ds, fill=MUTED, font=font_axis)

    draw.text(
        (margin_l, height - 20),
        f"近 {n} 日日K · 橘線 MA20 · 台銀牌告近似 OHLC",
        fill=MUTED,
        font=font_small,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
