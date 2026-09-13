# -*- coding: utf-8 -*-
"""
DL2 · 总览图(contact sheet)
===========================
把同一 Design Language 的所有照片结果拼成一页, 便于横向对比品牌一致性。

用法: python card-studio/dl2/make_sheet.py [--lang editorial] [--out dl2/out/sheet-editorial.png]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = r"C:\Windows\Fonts"
COLS = 2


def f(size, bold=False):
    return ImageFont.truetype(FONTS + (r"\msyhbd.ttc" if bold else r"\msyh.ttc"), size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="editorial")
    ap.add_argument("--dir", default="dl2/out")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = Path(a.dir)
    cards = sorted(c for c in d.glob(f"*-{a.lang}.png") if not c.name.startswith("sheet-"))
    if not cards:
        print("没有找到结果:", d / f"*-{a.lang}.png")
        return 1
    tw = 420
    th = int(tw * 1536 / 1024)
    cap = 34
    rows = (len(cards) + COLS - 1) // COLS
    gap = 18
    W = COLS * tw + (COLS + 1) * gap
    H = rows * (th + cap) + (rows + 1) * gap
    sheet = Image.new("RGB", (W, H), (16, 18, 24))
    dr = ImageDraw.Draw(sheet)
    for i, c in enumerate(cards):
        r, col = divmod(i, COLS)
        x = gap + col * (tw + gap)
        y = gap + r * (th + cap + gap)
        sheet.paste(Image.open(c).convert("RGB").resize((tw, th), Image.Resampling.LANCZOS), (x, y))
        dr.rectangle([x, y, x + tw - 1, y + th - 1], outline=(70, 74, 84), width=1)
        dr.text((x, y + th + 8), c.stem.replace(f"-{a.lang}", ""), font=f(19, True), fill=(228, 224, 214))
    out = Path(a.out) if a.out else d / f"sheet-{a.lang}.png"
    sheet.save(out)
    print("总览:", out, sheet.size, f"({len(cards)} 张)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
