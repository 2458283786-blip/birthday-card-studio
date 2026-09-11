# -*- coding: utf-8 -*-
"""
生成"模板字段位置预览图"(工坊用)
================================
每套 Birthday 模板出一张图: 卡面 + 编号标记(① ② ③…)+ 右侧字段图例,
让你一眼看清"我填的每个字段会出现在卡上的哪里"。

输出: card-studio/template-previews/<tpl>.png
用法: python card-studio/template_previews.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "template-previews"
SRC = OUT / "_src"
DEMO = ROOT / "demo-birthday" / "assets" / "source.png"
FONTS = r"C:\Windows\Fonts"

SAMPLE = {
    "title": "张三", "subtitle": "HAPPY BIRTHDAY", "tagline": "A DAY WORTH KEEPING",
    "technique": "2026.09.09", "edition": "CARD #0001", "name": "小明",
    "age": "20", "wish": "MAY EVERY YEAR BE KIND TO YOU",
    "collection": "BIRTHDAY COLLECTIBLE", "description": "MADE WITH CARD STUDIO.",
}

# (编号, 字段名, 说明, 徽标位置)
FIELDS = {
    "celebration": [
        (1, "副标题", "subtitle", (450, 118)),
        (2, "名字", "name → FOR NAME", (620, 172)),
        (3, "年龄", "age · 大数字", (60, 1150)),
        (4, "卡名", "title", (60, 1306)),
        (5, "一句话", "tagline", (60, 1370)),
        (6, "日期", "technique", (958, 1284)),
        (7, "编号", "edition", (958, 1352)),
    ],
    "soft": [
        (1, "副标题", "subtitle", (430, 144)),
        (2, "名字", "name → FOR NAME", (620, 196)),
        (3, "年龄", "age · 金环内", (100, 1240)),
        (4, "卡名", "title", (300, 1215)),
        (5, "一句话", "tagline", (300, 1285)),
        (6, "日期", "technique", (300, 1352)),
        (7, "编号", "edition", (300, 1418)),
    ],
    "pop": [
        (1, "副标题", "subtitle", (150, 128)),
        (2, "年龄", "age · 大数字", (60, 1120)),
        (3, "卡名", "title", (210, 1296)),
        (4, "名字", "name → FOR NAME", (210, 1360)),
        (5, "日期", "technique", (958, 1378)),
        (6, "编号", "edition", (958, 1442)),
    ],
    "diorama": [
        (1, "副标题", "subtitle", (430, 148)),
        (2, "名字", "name → FOR NAME", (620, 212)),
        (3, "年龄", "age · 大数字", (60, 1200)),
        (4, "卡名", "title", (60, 1356)),
        (5, "一句话", "tagline", (60, 1420)),
        (6, "日期", "technique", (958, 1248)),
        (7, "编号", "edition", (958, 1316)),
    ],
    "night": [
        (1, "名字 / 卡名", "name 优先, 留空则用 title", (400, 58)),
        (2, "副标题", "subtitle", (700, 100)),
        (3, "年龄", "age · 大数字", (60, 1280)),
        (4, "祝福语", "wish", (60, 1428)),
        (5, "日期", "technique", (700, 1286)),
        (6, "编号", "edition", (780, 1330)),
    ],
}

BACK_NOTE = ("背面固定放: 编号(edition) + 日期(technique);", "系列名与背面描述也只出现在背面。",
             "可选字段留空 → 卡面完全不出现(不留占位)。")


def f(size, bold=False):
    return ImageFont.truetype(FONTS + (r"\msyhbd.ttc" if bold else r"\msyh.ttc"), size)


def build_front(tpl):
    """用示例数据跑一遍真实流程, 得到卡面正片。"""
    proj = SRC / tpl
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    cfg = dict(SAMPLE)
    cfg.update({"backStyle": tpl, "createdBy": "", "ownedBy": ""})
    (proj / "card-config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf8")
    r = subprocess.run([sys.executable, "-u", str(HERE / "birthday_system.py"),
                        str(DEMO), str(proj), tpl], cwd=str(ROOT))
    if r.returncode != 0:
        raise RuntimeError(f"{tpl} 生成失败")
    out = Image.open(proj / "assets" / "background.png").convert("RGBA")
    for name in ("subject", "effects", "text"):
        p = proj / "assets" / f"{name}.png"
        if p.exists():
            out.alpha_composite(Image.open(p).convert("RGBA"))
    return out.convert("RGB")


def annotate(front, tpl):
    scale = 0.80
    cw, ch = int(1024 * scale), int(1536 * scale)
    card = front.resize((cw, ch), Image.Resampling.LANCZOS)
    legend_w = 470
    canvas = Image.new("RGB", (cw + legend_w, ch), (17, 20, 28))
    canvas.paste(card, (0, 0))
    d = ImageDraw.Draw(canvas, "RGBA")

    def badge(x, y, n):
        r = 19
        d.ellipse([x - r, y - r, x + r, y + r], fill=(232, 121, 106, 245))
        d.text((x, y + 1), str(n), font=f(23, True), fill=(255, 255, 255), anchor="mm")

    for n, _label, _hint, (x, y) in FIELDS[tpl]:
        badge(int(x * scale), int(y * scale), n)

    lx, ly = cw + 34, 74
    d.text((lx, 34), "字段落位图", font=f(30, True), fill=(240, 236, 226))
    d.text((lx, ly - 6), f"模板: {tpl}", font=f(19), fill=(200, 190, 170))
    ly += 34
    for n, label, hint, _pos in FIELDS[tpl]:
        d.ellipse([lx, ly + 4, lx + 26, ly + 30], fill=(232, 121, 106, 245))
        d.text((lx + 13, ly + 18), str(n), font=f(17, True), fill=(255, 255, 255), anchor="mm")
        d.text((lx + 40, ly + 3), label, font=f(21, True), fill=(238, 232, 220))
        d.text((lx + 40, ly + 30), hint, font=f(15), fill=(170, 165, 155))
        ly += 60
    ly += 8
    for i, line in enumerate(BACK_NOTE):
        d.text((lx, ly + i * 26), line, font=f(15), fill=(150, 145, 138))
    return canvas


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for tpl in FIELDS:
        front = build_front(tpl)
        img = annotate(front, tpl)
        p = OUT / f"{tpl}.png"
        img.save(p)
        print(f"  {tpl:12s} → {p.relative_to(ROOT)}  {img.size}")
    shutil.rmtree(SRC, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
