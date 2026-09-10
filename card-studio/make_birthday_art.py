# -*- coding: utf-8 -*-
"""
「YOUR DAY」生日数字收藏卡 · 程序化美术生成器
==============================================
设计原则(本版重点):
  * 照片不是"贴上去的矩形", 而是羽化融入整张卡面: 四边渐变、下半部过渡到深蓝底
  * 不抠图、不改人物、不重造背景; 只做裁切/调色/暗部压制/局部景深
  * 人物/照片是第一视觉主体; 卡框、文字、星点、Holo 只做辅助
  * 年龄(配置提供时)= 卡面核心视觉元素; 未提供则完全不出现(不虚构)
  * CARD #XXXX = 数字收藏卡的固定身份标识

输出 1024x1536: source / subject / background / lineart / text / effects
用法: python make_birthday_art.py <原照片> <项目目录>
"""
import json, math, os, random, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1024, 1536
PHOTO_TOP, PHOTO_BOTTOM = 118, 1232          # 照片带(全宽, 羽化融入)
FADE_TOP, FADE_SIDE, FADE_BOTTOM = 150, 78, 340
FRAME_OUT, FRAME_IN = 30, 46
random.seed(20260909)

FONTS = r"C:\Windows\Fonts"
SERIF = os.path.join(FONTS, "pala.ttf")
SANS = os.path.join(FONTS, "segoeui.ttf")
SANS_SB = os.path.join(FONTS, "seguisb.ttf")

GOLD = (222, 201, 160)
GOLD_DEEP = (168, 135, 79)
CHAMP = (232, 217, 181)
INK_BG = (10, 15, 28)
ROSE = (217, 166, 160)
WARM = (255, 246, 224)
NAVY = np.array([0.039, 0.059, 0.110], dtype=np.float32)   # #0a0f1c


def log(m):
    print("[生日卡] " + m, flush=True)


# ---------------------------------------------------------------- 基础工具
def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype(os.path.join(FONTS, "georgia.ttf"), size)


def star4(d, cx, cy, r, fill, ratio=0.24):
    pts = [(cx, cy - r), (cx + r * ratio, cy - r * ratio), (cx + r, cy),
           (cx + r * ratio, cy + r * ratio), (cx, cy + r),
           (cx - r * ratio, cy + r * ratio), (cx - r, cy), (cx - r * ratio, cy - r * ratio)]
    d.polygon(pts, fill=fill)


def rot_rect(cx, cy, w, h, ang):
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [(cx + x * c - y * s, cy + x * s + y * c)
            for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]


def tracked(d, xy, text, fnt, fill, tracking=0.0, center=False):
    widths = [d.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    x = xy[0] - total / 2 if center else xy[0]
    for ch, w in zip(text, widths):
        d.text((x, xy[1]), ch, font=fnt, fill=fill)
        x += w + tracking
    return total


def text_width(d, text, fnt, tracking=0.0):
    widths = [d.textlength(ch, font=fnt) for ch in text]
    return sum(widths) + tracking * max(0, len(text) - 1)


# ---------------------------------------------------------------- 照片层(羽化融入)
def grade_photo(src_path):
    """裁切 + 调色 + 暗部压制 + 局部景深 + 底部融入深蓝 + 四边羽化。"""
    pw, ph = W, PHOTO_BOTTOM - PHOTO_TOP
    im = Image.open(src_path).convert("RGB")
    iw, ih = im.size
    log(f"原始照片 {iw}x{ih}")
    scale = max(pw / iw, ph / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    cx = (nw - pw) // 2
    cy = int((nh - ph) * (0.40 if ih > iw else 0.5))
    im = im.crop((cx, cy, cx + pw, cy + ph))

    a = np.asarray(im).astype(np.float32) / 255.0
    lum = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
    a = np.clip(a, 0, 1) ** 1.07                     # 暗部压制
    a = 1.0 - (1.0 - a) ** 1.16                      # 高光滚降
    warm = np.clip(lum, 0, 1)[..., None]
    a[..., 0] *= 1.0 + 0.055 * warm[..., 0]          # 高光偏暖
    a[..., 2] *= 1.0 - 0.075 * warm[..., 0]
    cold = np.clip(1.0 - lum, 0, 1) ** 2 * 0.20      # 暗部偏冷蓝
    a = a * (1.0 - cold[..., None]) + NAVY * cold[..., None]
    l2 = (a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722)[..., None]
    a = l2 + (a - l2) * 0.90                         # 降饱和
    a = np.clip(a, 0, 1)

    img = Image.fromarray((a * 255).astype(np.uint8), "RGB")
    blur = img.filter(ImageFilter.GaussianBlur(2.6))            # 局部景深
    yy, xx = np.mgrid[0:ph, 0:pw]
    d = np.sqrt(((xx - pw / 2) / (pw / 2)) ** 2 + ((yy - ph / 2) / (ph / 2)) ** 2)
    k = np.clip((d - 0.62) / 0.55, 0, 1) ** 1.4 * 0.85
    a = np.asarray(Image.composite(blur, img, Image.fromarray((k * 255).astype(np.uint8), "L"))
                   ).astype(np.float32) / 255.0
    a *= (1.0 - np.clip((d - 0.25) / 0.95, 0, 1) ** 1.6 * 0.42)[..., None]   # 暗角

    # —— 与卡面融合: 上半部轻微压暗, 下半部渐次过渡到深蓝底 ——
    yn = yy / ph
    t_top = np.clip((0.14 - yn) / 0.14, 0, 1) ** 1.2 * 0.42
    t_bot = np.clip((yn - 0.52) / 0.48, 0, 1) ** 1.35 * 0.72
    a = a * (1.0 - (t_top + t_bot)[..., None]) + NAVY * (t_top + t_bot)[..., None]
    a += np.random.default_rng(4).normal(0, 0.006, a.shape)     # 细颗粒
    a = np.clip(a, 0, 1)
    photo = Image.fromarray((a * 255).astype(np.uint8), "RGB")

    # —— 羽化蒙版: 四边柔和消失, 不做矩形硬边 ——
    dl = np.clip(xx / FADE_SIDE, 0, 1)
    dr = np.clip((pw - 1 - xx) / FADE_SIDE, 0, 1)
    dt = np.clip(yy / FADE_TOP, 0, 1)
    db = np.clip((ph - 1 - yy) / FADE_BOTTOM, 0, 1)
    m = np.minimum(np.minimum(dl, dr), np.minimum(dt, db))
    m = (m * m * (3 - 2 * m)) ** 0.92                            # smoothstep
    mask = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8), "L")
    mask = mask.filter(ImageFilter.GaussianBlur(6))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(photo, (0, PHOTO_TOP), mask)
    return canvas


# ---------------------------------------------------------------- 背景层
def make_background():
    im = Image.new("RGBA", (W, H), INK_BG + (255,))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(10 + 12 * t), int(15 + 18 * t), int(28 + 26 * t)) + (255,))
    bg = im.convert("RGB").convert("RGBA")
    for (cx, cy, r, col, al, bl) in [(210, 190, 460, (152, 120, 62), 34, 140),
                                     (890, 1300, 470, (38, 62, 96), 34, 140),
                                     (512, 660, 320, (122, 100, 60), 13, 150)]:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (al,))
        bg.alpha_composite(layer.filter(ImageFilter.GaussianBlur(bl)))
    hair = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hair)
    for _ in range(260):
        y = random.randint(0, H - 1)
        x0 = random.randint(0, W - 200)
        hd.line([(x0, y), (x0 + random.randint(120, 420), y)],
                fill=(120, 140, 175, random.randint(3, 8)), width=1)
    bg.alpha_composite(hair)
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([512 - 335, 700 - 335, 512 + 335, 700 + 335],
                                 outline=GOLD + (14,), width=1)
    bg.alpha_composite(ring.filter(ImageFilter.GaussianBlur(0.6)))
    arr = np.asarray(bg.convert("RGB")).astype(np.float32) + \
        np.random.default_rng(9).normal(0, 2.0, (H, W, 3))
    bg = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    yy, xx = np.mgrid[0:H, 0:W]
    dd = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vig = 1.0 - np.clip((dd - 0.45) / 0.95, 0, 1) ** 1.5 * 0.45
    arr = np.asarray(bg.convert("RGB")).astype(np.float32) * vig[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


# ---------------------------------------------------------------- 线稿层(照片上的极细刻线)
def make_lineart():
    """极细发丝线, 只在照片区域, 供全息扫掠时透出一点点光泽。"""
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for r, a in ((330, 46), (300, 34)):
        d.ellipse([512 - r, 660 - r, 512 + r, 660 + r], outline=(a, a, a), width=1)
    for (x0, y0, x1, y1) in [(150, 300, 330, 480), (700, 900, 880, 1080)]:
        d.line([(x0, y0), (x1, y1)], fill=(52, 52, 52), width=2)
        d.line([(x0 - 14, y0 + 6), (x1 - 14, y1 + 6)], fill=(64, 64, 64), width=1)
    return im


# ---------------------------------------------------------------- 文字 + 卡框层(最前)
def make_text(cfg):
    """文案来自 card-config.json。年龄(age)存在时成为核心视觉元素。"""
    T_HB = cfg.get("subtitle") or "HAPPY BIRTHDAY"
    T_MAIN = cfg.get("title") or "YOUR DAY"
    T_SUB = cfg.get("tagline") or "A DAY WORTH KEEPING"
    T_DATE = cfg.get("technique") or ""
    T_NO = cfg.get("edition") or "CARD #0001"
    T_DC = cfg.get("collection") or "DIGITAL COLLECTIBLE"
    age = str(cfg.get("age") or "").strip()

    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # —— 精细双线卡框 + 四角星芒(卡牌自身边缘) ——
    d.rectangle([FRAME_OUT, FRAME_OUT, W - FRAME_OUT - 1, H - FRAME_OUT - 1],
                outline=GOLD + (205,), width=2)
    d.rectangle([FRAME_IN, FRAME_IN, W - FRAME_IN - 1, H - FRAME_IN - 1],
                outline=GOLD_DEEP + (150,), width=1)
    for (x, y, sx, sy) in [(FRAME_OUT, FRAME_OUT, 1, 1), (W - FRAME_OUT - 1, FRAME_OUT, -1, 1),
                           (FRAME_OUT, H - FRAME_OUT - 1, 1, -1),
                           (W - FRAME_OUT - 1, H - FRAME_OUT - 1, -1, -1)]:
        d.line([(x, y), (x + sx * 62, y)], fill=GOLD + (170,), width=1)
        d.line([(x, y), (x, y + sy * 62)], fill=GOLD + (170,), width=1)
        star4(d, x + sx * 78, y + sy * 78, 6.5, GOLD + (185,))

    # —— 顶部小标题 ——
    f_hb = font(SANS_SB, 26)
    tracked(d, (W / 2, 150), T_HB, f_hb, CHAMP + (238,), tracking=11.5, center=True)
    star4(d, W / 2, 182, 6.0, GOLD + (210,))
    d.line([(W / 2 - 150, 182), (W / 2 - 30, 182)], fill=GOLD + (120,), width=1)
    d.line([(W / 2 + 30, 182), (W / 2 + 150, 182)], fill=GOLD + (120,), width=1)

    # —— 分割细线(两端渐隐) ——
    y = 1214
    for i in range(816):
        al = int(min(1.0, min(i, 815 - i) / 60.0) * 58)
        d.point((104 + i, y), fill=GOLD + (al,))

    xl, xr = 104, W - 104
    if age:
        # —— 年龄 = 核心视觉: 大号暖金数字, 恰好压在照片融入底色的过渡带上 ——
        f_age = font(SERIF, 182)
        d.text((xl + 3, 1312 + 3), age, font=f_age, fill=(120, 96, 52, 120), anchor="ls")
        d.text((xl, 1312), age, font=f_age, fill=(238, 228, 202, 255), anchor="ls")
        aw = d.textlength(age, font=f_age)
        star4(d, xl + aw + 30, 1200, 7.0, GOLD + (195,))
        # —— YOUR DAY 作为副线 ——
        f_main = font(SERIF, 44)
        tracked(d, (xl + 4, 1362), T_MAIN, f_main, (240, 232, 214, 245), tracking=7.0)
        f_sub = font(SANS, 14)
        tracked(d, (xl + 6, 1398), T_SUB, f_sub, GOLD + (140,), tracking=5.0)
    else:
        # —— 无年龄: YOUR DAY 回归主标题(不虚构数字) ——
        f_main = font(SERIF, 104)
        tracked(d, (xl, 1332), T_MAIN, f_main, (244, 236, 218, 255), tracking=1.5)
        f_sub = font(SANS, 17)
        tracked(d, (xl + 4, 1372), T_SUB, f_sub, GOLD + (150,), tracking=6.0)

    # —— 右下身份信息: 日期 / CARD # / 收藏标识 ——
    f_date = font(SANS, 26)
    if T_DATE:
        wd = text_width(d, T_DATE, f_date, 2.0)
        tracked(d, (xr - 212 + (212 - wd), 1252), T_DATE, f_date, GOLD + (228,), tracking=2.0)
    f_no = font(SANS, 19)
    wn = text_width(d, T_NO, f_no, 1.4)
    tracked(d, (xr - wn, 1292), T_NO, f_no, (176, 160, 128, 235), tracking=1.4)
    return im


# ---------------------------------------------------------------- 前景装饰层
def make_effects():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def clear_of_face(x, y):
        return math.hypot((x - 512) / 1.0, (y - 620) / 1.35) > 235 or random.random() < 0.18

    far = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(far)
    for _ in range(150):
        x, y = random.randint(20, W - 20), random.randint(20, H - 20)
        if not clear_of_face(x, y):
            continue
        r = random.uniform(1.2, 3.4)
        fd.ellipse([x - r, y - r, x + r, y + r], fill=WARM + (random.randint(60, 130),))
    im.alpha_composite(far.filter(ImageFilter.GaussianBlur(0.5)))

    bok = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bok)
    for _ in range(5):
        x, y = random.randint(60, W - 60), random.randint(60, H - 60)
        r = random.uniform(18, 30)
        bd.ellipse([x - r, y - r, x + r, y + r], fill=(255, 232, 186, random.randint(20, 32)))
    im.alpha_composite(bok.filter(ImageFilter.GaussianBlur(9)))

    for _ in range(10):
        x, y = random.randint(70, W - 70), random.randint(70, H - 70)
        if not clear_of_face(x, y):
            continue
        r = random.uniform(8, 16)
        a = random.randint(160, 215)
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        star4(gd, x, y, r, GOLD + (a,), ratio=0.18)
        star4(gd, x, y, r * 0.42, (255, 250, 235, min(255, a + 35)), ratio=0.5)
        im.alpha_composite(g.filter(ImageFilter.GaussianBlur(0.6)))

    for _ in range(22):
        x, y = random.randint(40, W - 40), random.randint(40, H - 40)
        if not clear_of_face(x, y):
            continue
        col = random.choice([GOLD, CHAMP, GOLD, ROSE])
        ImageDraw.Draw(im).polygon(
            rot_rect(x, y, random.uniform(3, 5.5), random.uniform(9, 16), random.uniform(0, 180)),
            fill=col + (random.randint(85, 140),))

    for box, a0, a1 in [((-60, 120, 460, 640), 200, 330), ((600, 980, 1120, 1500), 20, 120)]:
        arc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(arc).arc(box, start=a0, end=a1, fill=GOLD + (26,), width=1)
        im.alpha_composite(arc.filter(ImageFilter.GaussianBlur(1.0)))
    return im


# ---------------------------------------------------------------- 主流程
def main():
    photo = sys.argv[1] if len(sys.argv) > 1 else \
        "card-studio/projects/card-mtss5ijz/assets/source.png"
    proj = Path(sys.argv[2] if len(sys.argv) > 2 else "demo-birthday")
    out = proj / "assets"
    out.mkdir(parents=True, exist_ok=True)

    cfg = {}
    cfg_path = proj / "card-config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf8"))
        log(f"文案来源: {cfg_path.name} | age={cfg.get('age') or '(未提供, 不显示年龄)'}")

    Image.open(photo).convert("RGB").save(out / "source.png")
    log("原图已留底 assets/source.png")
    grade_photo(photo).save(out / "subject.png")
    log("照片层完成(羽化融入 + 调色 + 暗部压制 + 局部景深)")
    make_background().save(out / "background.png")
    log("背景层完成")
    make_lineart().save(out / "lineart.png")
    log("线稿层完成(照片上极细刻线)")
    make_text(cfg).save(out / "text.png")
    log("卡框 + 文字层完成" + ("(含年龄核心元素)" if str(cfg.get("age") or "").strip() else ""))
    make_effects().save(out / "effects.png")
    log("前景装饰层完成")
    log("全部完成 → " + str(out))


if __name__ == "__main__":
    main()
