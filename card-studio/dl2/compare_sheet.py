# -*- coding: utf-8 -*-
"""
DL2 · 三套语言并排对比图
=======================
同一张照片 × Editorial / Cinema / Memory 横向并排, 一眼看清区别。

用法: python card-studio/dl2/compare_sheet.py --photo 04-sea-dress
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = r"C:\Windows\Fonts"
LANGS = [("editorial", "Editorial 杂志"), ("cinema", "Cinema 电影"), ("memory", "Memory 相册")]


def f(size, bold=False):
    return ImageFont.truetype(FONTS + (r"\msyhbd.ttc" if bold else r"\msyh.ttc"), size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", default="04-sea-dress")
    ap.add_argument("--dir", default="dl2/out")
    a = ap.parse_args()
    d = Path(a.dir)
    tw = 380
    th = int(tw * 1536 / 1024)
    gap, cap = 16, 40
    W = len(LANGS) * tw + (len(LANGS) + 1) * gap
    H = th + cap + gap * 2 + 46
    sheet = Image.new("RGB", (W, H), (16, 18, 24))
    dr = ImageDraw.Draw(sheet)
    dr.text((gap, 12), f"{a.photo} —— 同一张照片的三种 Design Language", font=f(21, True),
            fill=(232, 228, 218))
    for i, (lang, label) in enumerate(LANGS):
        p = d / f"{a.photo}-{lang}.png"
        x = gap + i * (tw + gap)
        y = 46 + gap
        if p.exists():
            sheet.paste(Image.open(p).convert("RGB").resize((tw, th), Image.Resampling.LANCZOS), (x, y))
        else:
            dr.rectangle([x, y, x + tw, y + th], outline=(90, 90, 90))
            dr.text((x + 20, y + 20), "缺失", font=f(20), fill=(200, 120, 120))
        dr.rectangle([x, y, x + tw - 1, y + th - 1], outline=(70, 74, 84), width=1)
        dr.text((x, y + th + 10), label, font=f(19, True), fill=(228, 224, 214))
    out = d / f"compare-{a.photo}.png"
    sheet.save(out)
    print("对比图:", out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
