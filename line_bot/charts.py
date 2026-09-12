"""
K 線圖產生（台銀牌告日線近似 OHLC）。

Open≈即期買 / High≈現金賣 / Low≈現金買 / Close≈即期賣；
若即期無效則改用現金買賣。
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
UP = "#1F6F63"
DOWN = "#B42318"
HEADER = "#0B1F1C"


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
    # 修正 high/low 與 open/close 不一致
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"] = df[["low", "open", "close"]].min(axis=1)
    return df.tail(limit).reset_index(drop=True)


def generate_kline_png(
    records: list[dict],
    title: str = "",
    limit: int = 40,
) -> Optional[bytes]:
    """繪製近 N 日 K 線圖，回傳 PNG bytes。"""
    df = _to_ohlc(records, limit=limit)
    if len(df) < 5:
        logger.warning("K 線資料不足: %d", len(df))
        return None

    width, height = 800, 360
    margin_l, margin_r, margin_t, margin_b = 56, 24, 48, 36
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    img = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        font_axis = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except OSError:
        try:
            font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
            font_axis = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
        except OSError:
            font_title = ImageFont.load_default()
            font_axis = font_title

    draw.rectangle([0, 0, width, 36], fill=HEADER)
    label = title or "K-Line"
    draw.text((16, 10), label, fill="#7A9E96", font=font_title)

    ymin = float(df["low"].min())
    ymax = float(df["high"].max())
    if ymax <= ymin:
        ymax = ymin + 1e-6
    pad = (ymax - ymin) * 0.08
    ymin -= pad
    ymax += pad

    def y_of(v: float) -> float:
        return margin_t + (1 - (v - ymin) / (ymax - ymin)) * plot_h

    # 水平格線
    for i in range(5):
        gy = margin_t + plot_h * i / 4
        draw.line([(margin_l, gy), (width - margin_r, gy)], fill=GRID, width=1)
        val = ymax - (ymax - ymin) * i / 4
        draw.text((8, gy - 6), f"{val:.4f}", fill=MUTED, font=font_axis)

    n = len(df)
    slot = plot_w / n
    body_w = max(3, min(14, slot * 0.55))

    for i, row in df.iterrows():
        x = margin_l + (i + 0.5) * slot
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        color = UP if c >= o else DOWN
        y_h, y_l = y_of(h), y_of(l)
        y_o, y_c = y_of(o), y_of(c)
        # 影線
        draw.line([(x, y_h), (x, y_l)], fill=color, width=1)
        # 實體
        top, bot = min(y_o, y_c), max(y_o, y_c)
        if abs(bot - top) < 1:
            bot = top + 1
        draw.rectangle(
            [x - body_w / 2, top, x + body_w / 2, bot],
            fill=color,
            outline=color,
        )

    # 日期標籤（首中尾）
    for idx in (0, n // 2, n - 1):
        x = margin_l + (idx + 0.5) * slot
        ds = df.iloc[idx]["date"].strftime("%m/%d")
        draw.text((x - 14, height - 24), ds, fill=MUTED, font=font_axis)

    draw.text(
        (margin_l, height - 22),
        f"近 {n} 日 · 台銀牌告近似 OHLC",
        fill=MUTED,
        font=font_axis,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()
