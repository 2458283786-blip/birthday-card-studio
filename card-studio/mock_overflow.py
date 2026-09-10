# -*- coding: utf-8 -*-
"""
溢出效果 · 视觉 Mock(不修改卡牌系统)
=====================================
做法: 拿现有卡面合成结果, 在"超大画布"(卡面居中, 四边留溢出区)上另外画一层
溢出装饰; 该层有自己的深度 → 按与 shader 相同的视差公式位移, 于是它相对卡面
会多移动一点; 最后把"卡面 + 溢出"作为一个整体做透视压缩 → 一起转。

输出: birthday-set/previews/mock-*.png
用法: python card-studio/mock_overflow.py
"""
import json, math, random, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render_previews import (SET, OUT, compose_front, view_vector,  # noqa: E402
                            parallax_shift, f, tracked, SANS, CJK)

CARD_W, CARD_H = 1024, 1536
OV_W, OV_H = 1500, 2150                      # 溢出画布(卡面居中, 四边留 ~24%)
CX, CY = (OV_W - CARD_W) // 2, (OV_H - CARD_H) // 2
IN = (CX, CY, CX + CARD_W, CY + CARD_H)
random.seed(88)

GOLD = (232, 201, 138)
EMBER = (196, 82, 63)
ROSE = (217, 140, 122)
CORAL = (232, 121, 106)
BUTTER = (246, 210, 122)
SKY = (127, 178, 217)
APRICOT = (240, 168, 104)


def tapered(d, pts, color, w0, alpha0, glow=True):
    """沿折线画一条由粗到细的笔触。"""
    n = len(pts) - 1
    for k in range(n):
        u = k / max(1, n - 1)
        wd = max(1, int(w0 * (1 - u) ** 1.3))
        a = int(alpha0 * (1 - u) ** 0.85)
        d.line([pts[k], pts[k + 1]], fill=color + (a,), width=wd)


def curve(x0, y0, ang, ln, bend, steps=30):
    c, s = math.cos(ang), math.sin(ang)
    out = []
    for k in range(steps + 1):
        u = k / steps
        b = math.sin(u * math.pi) * bend
        out.append((x0 + c * ln * u - s * b, y0 + s * ln * u + c * b))
    return out


def diorama_overflow():
    """暖金/余烬笔触扫出卡外 + 火星颗粒(集中在左下/右侧, 力度更足)。"""
    im = Image.new("RGBA", (OV_W, OV_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    strokes = [
        (IN[0] + 330, IN[3] - 180, math.radians(200), 700, 90, GOLD, 27, 200),
        (IN[0] + 170, IN[3] - 430, math.radians(214), 560, 70, EMBER, 22, 175),
        (IN[2] - 190, IN[1] + 260, math.radians(8), 620, 80, GOLD, 19, 150),
    ]
    for (x, y, ang, ln, bend, col, w0, a0) in strokes:
        pts = curve(x, y, ang, ln, bend, 34)
        # 先铺一层宽而淡的"颜料晕"
        tapered(d, pts, col, int(w0 * 2.1), int(a0 * 0.22))
        # 再压一道余烬描边
        tapered(d, [(px + 5, py + 4) for (px, py) in pts], EMBER, max(3, w0 - 6), int(a0 * 0.55))
        # 主线
        tapered(d, pts, col, w0, a0)

    def outside_biased():
        for _ in range(200):
            x, y = random.randint(30, OV_W - 30), random.randint(30, OV_H - 30)
            deep_inside = IN[0] + 90 < x < IN[2] - 90 and IN[1] + 90 < y < IN[3] - 90
            if deep_inside:
                continue
            return x, y
        return random.randint(30, OV_W - 30), random.randint(30, OV_H - 30)

    for _ in range(64):                                  # 火星
        x, y = outside_biased()
        for _try in range(4):
            if y < IN[3] - 200 or x > IN[0] + 200:       # 主要落在下半 / 左侧
                break
            x, y = outside_biased()
        col = random.choice([GOLD, EMBER, ROSE, (255, 246, 224)])
        r = random.uniform(1.8, 4.6)
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (random.randint(110, 215),))
    for _ in range(9):                                   # 十字星芒飞到卡外
        x, y = outside_biased()
        r = random.uniform(9, 18)
        a = random.randint(170, 225)
        star4 = [(x, y - r), (x + r * 0.18, y - r * 0.18), (x + r, y), (x + r * 0.18, y + r * 0.18),
                 (x, y + r), (x - r * 0.18, y + r * 0.18), (x - r, y), (x - r * 0.18, y - r * 0.18)]
        d.polygon(star4, fill=GOLD + (a,))
        d.ellipse([x - 2.6, y - 2.6, x + 2.6, y + 2.6], fill=(255, 250, 235, min(255, a + 30)))
    im = im.filter(ImageFilter.GaussianBlur(0.8))
    for (gx, gy, r) in [(IN[0] - 120, IN[3] - 140, 330), (IN[2] + 90, IN[1] + 260, 280)]:
        lay = Image.new("RGBA", (OV_W, OV_H), (0, 0, 0, 0))
        ImageDraw.Draw(lay).ellipse([gx - r, gy - r, gx + r, gy + r], fill=(184, 122, 52, 40))
        im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(80)))
    return im


def celebration_overflow():
    """彩色纸屑 + 小圆点 + 丝带卷: 集中在左上与右下两簇, 明确"飞出卡外"。"""
    im = Image.new("RGBA", (OV_W, OV_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pal = [CORAL, BUTTER, SKY, APRICOT, (255, 255, 255)]
    clusters = [
        (IN[0] - 60, IN[1] + 40, 330),          # 左上簇
        (IN[2] + 40, IN[3] - 60, 360),          # 右下簇
    ]

    def pick():
        cx, cy, rad = random.choice(clusters)
        ang = random.uniform(0, 2 * math.pi)
        rr = rad * math.sqrt(random.random())
        return cx + math.cos(ang) * rr, cy + math.sin(ang) * rr

    def deep_inside(x, y):
        return IN[0] + 70 < x < IN[2] - 70 and IN[1] + 70 < y < IN[3] - 70

    placed = 0
    while placed < 54:
        x, y = pick()
        if not (0 < x < OV_W and 0 < y < OV_H):
            continue
        if deep_inside(x, y) and random.random() > 0.22:
            continue
        placed += 1
        col = random.choice(pal)
        if random.random() < 0.4:
            r = random.uniform(5, 11)
            d.ellipse([x - r, y - r, x + r, y + r], fill=col + (random.randint(150, 235),))
        else:
            w, h, ang = random.uniform(8, 12), random.uniform(16, 26), random.uniform(0, 180)
            c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            pts = [(x + px * c - py * s, y + px * s + py * c)
                   for px, py in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
            d.polygon(pts, fill=col + (random.randint(165, 240),))
    # 两条丝带: 从卡面内卷出卡外
    for (x0, y0, ang, ln, bend, col, w0) in [
            (IN[0] + 210, IN[1] + 210, math.radians(238), 560, 110, CORAL, 14),
            (IN[2] - 180, IN[3] - 240, math.radians(-24), 520, 100, BUTTER, 12)]:
        pts = curve(x0, y0, ang, ln, bend, 36)
        tapered(d, [(px + 3, py + 3) for (px, py) in pts], (255, 255, 255), max(2, w0 - 8), 70)
        tapered(d, pts, col, w0, 215)
    # 角部小弧(只露一段在卡外)
    for (box, a0, a1, col) in [((IN[0] - 190, IN[1] - 150, IN[0] + 210, IN[1] + 250), 100, 200, SKY),
                               ((IN[2] - 210, IN[3] - 250, IN[2] + 190, IN[3] + 150), 280, 20, APRICOT)]:
        d.arc(box, start=a0, end=a1, fill=col + (110,), width=4)
    return im.filter(ImageFilter.GaussianBlur(0.4))


def render_mock(tpl, key, rx, ry, foil, maker):
    cfg = json.loads((SET / tpl / "card-config.json").read_text(encoding="utf8"))
    card = Image.fromarray((compose_front(tpl, cfg, rx, ry, foil) * 255).astype(np.uint8), "RGB").convert("RGBA")

    view = view_vector(rx, ry)
    dx, dy = parallax_shift(view, 0.88)                    # 溢出层自己的深度
    ov = maker()
    ov = ov.transform((OV_W, OV_H), Image.AFFINE, (1, 0, dx * OV_W, 0, 1, dy * OV_H),
                      resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))

    base = Image.new("RGBA", (OV_W, OV_H), (7, 9, 16, 255))
    card_l = Image.new("RGBA", (OV_W, OV_H), (0, 0, 0, 0))
    card_l.alpha_composite(card, (CX, CY))
    sh_l = Image.new("RGBA", (OV_W, OV_H), (0, 0, 0, 0))
    ImageDraw.Draw(sh_l).rectangle([CX + 16, CY + 26, CX + CARD_W + 16, CY + CARD_H + 26], fill=(0, 0, 0, 165))
    sh_l = sh_l.filter(ImageFilter.GaussianBlur(40))
    if ry:                                                  # 阴影 / 卡面 / 溢出 一起转
        squeeze = max(0.45, math.cos(abs(ry)))
        w2 = max(1, int(OV_W * squeeze))
        card_l = card_l.resize((w2, OV_H), Image.Resampling.LANCZOS)
        ov = ov.resize((w2, OV_H), Image.Resampling.LANCZOS)
        sh_l = sh_l.resize((w2, OV_H), Image.Resampling.LANCZOS)
        base = base.resize((w2, OV_H), Image.Resampling.LANCZOS)
    base.alpha_composite(sh_l)
    base.alpha_composite(card_l)
    base.alpha_composite(ov)

    board = Image.new("RGB", (1240, 1720), (10, 14, 22))
    sc = min(1120 / base.width, 1560 / base.height)
    r = base.resize((int(base.width * sc), int(base.height * sc)), Image.Resampling.LANCZOS)
    board.paste(r, ((1240 - r.width) // 2, (1720 - r.height) // 2), r)
    p = OUT / f"mock-{tpl}-{key}.png"
    board.save(p)
    print("saved", p.name, flush=True)
    return board


def sheet(items, title):
    pad, cap = 24, 52
    cw, ch = items[0][0].width, items[0][0].height
    n = len(items)
    W = pad + n * (cw + pad)
    H = pad + 70 + ch + cap
    cv = Image.new("RGB", (W, H), (8, 11, 18))
    d = ImageDraw.Draw(cv)
    d.text((pad + 6, 20), title, font=f(CJK, 30), fill=(240, 232, 214))
    for i, (img, cap_txt) in enumerate(items):
        x = pad + i * (cw + pad)
        cv.paste(img, (x, 70))
        tracked(d, (x + cw / 2, 70 + ch + 14), cap_txt, f(CJK, 20), (203, 185, 143), 2, True)
    return cv


def main():
    items = []
    for tpl, maker, foil in [("diorama", diorama_overflow, 0.95), ("celebration", celebration_overflow, 0.55)]:
        for key, rx, ry in [("front", -0.035, -0.15), ("tilt", -0.105, -0.52)]:
            items.append((render_mock(tpl, key, rx, ry, foil, maker), f"{tpl} · {'正面' if key=='front' else '倾斜'}"))
    sheet(items, "溢出效果 Mock · 卡面 + 画布外延(溢出层独立深度)").save(OUT / "mock-sheet.png")
    # 挂到预览页(幂等)
    idx = OUT / "index.html"
    if idx.exists():
        html = idx.read_text(encoding="utf8")
        if "mock-sheet.png" not in html:
            block = ('<section><h2>溢出效果 Mock(溢出层独立深度 · 与卡片一起转)</h2>'
                     '<a href="./mock-sheet.png"><img src="./mock-sheet.png" /></a>'
                     '<p>' + " · ".join(
                         f'<a href="./mock-{t}-{k}.png">{t} {"正面" if k == "front" else "倾斜"}</a>'
                         for t in ("diorama", "celebration") for k in ("front", "tilt")) +
                     '</p></section>')
            idx.write_text(html.replace("</main>", block + "\n</main>"), encoding="utf8")
            print("previews/index.html 已挂上 mock 区块")
    print("done →", OUT / "mock-sheet.png")


if __name__ == "__main__":
    main()
