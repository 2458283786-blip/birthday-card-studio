# -*- coding: utf-8 -*-
"""
Birthday 数字收藏卡 · 四套模板生成器
=====================================
同一个品牌系统下的四种 Birthday 视觉语言:
  celebration  明亮开心 · 奶油白/柔黄/暖橙/珊瑚粉 · 照片上方出血 + 底部色块排版
  soft         温柔浪漫 · 米白/奶油/香槟金/淡粉   · 照片长渐变融入 + 杂志式留白
  pop          年轻大胆 · 蓝/黄/红/粉/橙        · 斜切色块 + 巨大数字排版
  night        高级安静 · 深蓝/黑/香槟金         · 照片羽化融入深色 + 大号暖金数字

所有模板共用同一套层结构与 Holo/Parallax 技术, 只改变视觉语言。
输出 1024x1536 六层: subject / background / lineart / text / effects (+source)

用法: python birthday_system.py <原照片> <项目目录> <模板名>
"""
import json, math, os, random, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1024, 1536
FONTS = r"C:\Windows\Fonts"
SERIF = os.path.join(FONTS, "pala.ttf")
SANS = os.path.join(FONTS, "segoeui.ttf")
SANS_SB = os.path.join(FONTS, "seguisb.ttf")
SANS_BLACK = os.path.join(FONTS, "bahnschrift.ttf")
ARIAL_BD = os.path.join(FONTS, "arialbd.ttf")

TEMPLATES = ["celebration", "soft", "pop", "night", "diorama"]

PALETTE = {
    "celebration": {"bg": (251, 246, 236), "ink": (58, 52, 44), "gold": (196, 150, 74),
                    "a": (232, 121, 106), "b": (246, 210, 122), "c": (240, 168, 104),
                    "d": (127, 178, 217), "soft": (255, 255, 255)},
    "soft": {"bg": (247, 242, 234), "ink": (91, 82, 72), "gold": (216, 195, 160),
             "a": (232, 210, 206), "b": (239, 231, 218), "c": (216, 195, 160),
             "d": (214, 188, 168), "soft": (255, 253, 249)},
    "pop": {"bg": (255, 253, 246), "ink": (20, 20, 20), "gold": (255, 212, 0),
            "a": (43, 76, 255), "b": (255, 212, 0), "c": (255, 75, 62),
            "d": (255, 154, 193), "soft": (255, 122, 47)},
    "night": {"bg": (10, 15, 28), "ink": (240, 232, 214), "gold": (222, 201, 160),
              "a": (168, 135, 79), "b": (38, 62, 96), "c": (120, 100, 60),
              "d": (217, 166, 160), "soft": (14, 21, 38)},
    # 立体画框: 深底 + 暖金 + 玫红余烬, 层距最大, 金箔光扫最强
    "diorama": {"bg": (8, 11, 20), "ink": (242, 232, 213), "gold": (232, 201, 138),
                "a": (168, 118, 58), "b": (196, 82, 63), "c": (217, 140, 122),
                "d": (120, 96, 52), "soft": (16, 26, 46)},
}
NAVY = np.array([0.039, 0.059, 0.110], dtype=np.float32)
CREAM = np.array([0.984, 0.965, 0.925], dtype=np.float32)


def log(m):
    print(f"[{m}]", flush=True)


def font(path, size):
    for p in (path, ARIAL_BD, os.path.join(FONTS, "georgia.ttf")):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    raise RuntimeError("no font")


def star4(d, cx, cy, r, fill, ratio=0.24):
    d.polygon([(cx, cy - r), (cx + r * ratio, cy - r * ratio), (cx + r, cy),
               (cx + r * ratio, cy + r * ratio), (cx, cy + r),
               (cx - r * ratio, cy + r * ratio), (cx - r, cy), (cx - r * ratio, cy - r * ratio)], fill=fill)


def rot_rect(cx, cy, w, h, ang):
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [(cx + x * c - y * s, cy + x * s + y * c)
            for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]


def tracked(d, xy, text, fnt, fill, tracking=0.0, center=False, shadow=None):
    text = str(text)
    widths = [d.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    x = xy[0] - total / 2 if center else xy[0]
    if shadow:
        sx, sy, sc = shadow
        xx = x + sx
        for ch, w in zip(text, widths):
            d.text((xx, xy[1] + sy), ch, font=fnt, fill=sc)
            xx += w + tracking
    for ch, w in zip(text, widths):
        d.text((x, xy[1]), ch, font=fnt, fill=fill)
        x += w + tracking
    return total


def tw(d, text, fnt, tracking=0.0):
    text = str(text)
    return sum(d.textlength(ch, font=fnt) for ch in text) + tracking * max(0, len(text) - 1)


# ---------------------------------------------------------------- 照片: 裁切 + 调色 + 融合
def photo_layer(src_path, tpl, box, mask_kind):
    """box=(l,t,r,b) 照片可见区域; mask_kind 决定融合方式。保留原图, 不抠图。
    若素材本身带透明通道(透明 PNG), Diorama 会自动切成真·立体抠图模式。"""
    raw = ImageOps.exif_transpose(Image.open(src_path))   # 手机横拍带 EXIF 旋转时必须先摆正
    if "A" in raw.getbands():
        alpha = raw.convert("RGBA").getchannel("A")
        has_alpha = (np.asarray(alpha) < 8).mean() > 0.004
        if has_alpha and tpl == "diorama":
            return _cutout_place(raw.convert("RGBA"), 880, 1010, 700)
        if has_alpha and tpl == "night":
            # 透明主体(已抠好的图): 直接浮在卡面上, 保留原透明, 不铺照片带
            return _cutout_place(raw.convert("RGBA"), 920, 930, 655)
    cfg = {
        "celebration": dict(scale_crop=0.42, bright=1.05, contrast=1.10, sat=1.00, warm=0.05,
                            crush=1.03, lift=0.012, blur=2.2, edge_k=0.55, vig=0.18,
                            fade_to=CREAM, fade_bottom=0.30, fade_top=0.02, grain=0.005),
        "soft": dict(scale_crop=0.40, bright=1.04, contrast=1.04, sat=0.94, warm=0.035,
                     crush=1.01, lift=0.018, blur=3.2, edge_k=0.85, vig=0.08,
                     fade_to=np.array([0.969, 0.949, 0.918], dtype=np.float32),
                     fade_bottom=0.52, fade_top=0.03, grain=0.006),
        "pop": dict(scale_crop=0.44, bright=1.03, contrast=1.16, sat=1.14, warm=0.02,
                    crush=1.12, lift=0.0, blur=1.6, edge_k=0.35, vig=0.22,
                    fade_to=np.array([0.11, 0.19, 1.0], dtype=np.float32), fade_bottom=0.14,
                    fade_top=0.0, grain=0.006),
        "night": dict(scale_crop=0.40, bright=1.00, contrast=1.17, sat=1.00, warm=0.05,
                      crush=1.11, lift=0.0, blur=2.0, edge_k=0.6, vig=0.48,
                      fade_to=NAVY, fade_bottom=0.24, fade_top=0.03, grain=0.006),
        # 立体画框: 保留原片色彩(不压不灰), 底部较短融入, 靠投影+顶缘反光营造浮雕
        "diorama": dict(scale_crop=0.40, bright=1.02, contrast=1.12, sat=1.02, warm=0.04,
                        crush=1.05, lift=0.0, blur=2.0, edge_k=0.5, vig=0.34,
                        fade_to=np.array([0.031, 0.043, 0.078], dtype=np.float32),
                        fade_bottom=0.34, fade_top=0.06, grain=0.006),
    }[tpl]

    l, t, r, b = box
    pw, ph = r - l, b - t
    im = ImageOps.exif_transpose(Image.open(src_path)).convert("RGB")
    iw, ih = im.size
    scale = max(pw / iw, ph / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    cx = (nw - pw) // 2
    cy = int((nh - ph) * (cfg["scale_crop"] if ih > iw else 0.5))
    # —— 智能构图: 以"细节密度重心"(通常是人脸/人物)决定裁剪位置 ——
    try:
        gg = np.asarray(im.convert("L").resize((64, 64), Image.Resampling.BILINEAR), dtype=np.float32)
        e = np.zeros((64, 64), np.float32)
        e[:, :63] += np.abs(np.diff(gg, axis=1))
        e[:63, :] += np.abs(np.diff(gg, axis=0))
        e = e / (e.sum() + 1e-6)
        cxx, cyy = np.meshgrid(np.arange(64), np.arange(64))
        sx = float((e * cxx).sum()) / 64.0
        sy = float((e * cyy).sum()) / 64.0
        if nw > pw:
            cx = int(np.clip(sx * nw - 0.50 * pw, 0, nw - pw))
        if nh > ph:
            cy = int(np.clip(sy * nh - 0.50 * ph, 0, nh - ph))   # 头顶留出更多空间, 顶部小标题不压头发
    except Exception:
        pass
    im = im.crop((cx, cy, cx + pw, cy + ph))

    a = np.asarray(im).astype(np.float32) / 255.0
    a = np.clip(a * cfg["bright"], 0, 1)
    a = np.clip((a - 0.5) * cfg["contrast"] + 0.5, 0, 1)
    a = np.clip(a, 0, 1) ** cfg["crush"]
    a = a + cfg["lift"] * (1.0 - a)
    lum = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
    l2 = lum[..., None]
    a = l2 + (a - l2) * cfg["sat"]
    if cfg["warm"]:
        a[..., 0] *= 1.0 + cfg["warm"] * np.clip(lum, 0, 1)
        a[..., 2] *= 1.0 - cfg["warm"] * 1.3 * np.clip(lum, 0, 1)
    a = np.clip(a, 0, 1)
    img = Image.fromarray((a * 255).astype(np.uint8), "RGB")

    # 局部景深(边缘轻微虚化) + 暗角
    blur = img.filter(ImageFilter.GaussianBlur(cfg["blur"]))
    yy, xx = np.mgrid[0:ph, 0:pw]
    dnorm = np.sqrt(((xx - pw / 2) / (pw / 2)) ** 2 + ((yy - ph / 2) / (ph / 2)) ** 2)
    k = np.clip((dnorm - 0.60) / 0.55, 0, 1) ** 1.4 * cfg["edge_k"]
    a = np.asarray(Image.composite(blur, img, Image.fromarray((k * 255).astype(np.uint8), "L"))
                   ).astype(np.float32) / 255.0
    a *= (1.0 - np.clip((dnorm - 0.25) / 0.95, 0, 1) ** 1.6 * cfg["vig"])[..., None]

    # 与卡面融合: 顶部/底部渐次过渡到模板底色
    yn = yy / ph
    tt = np.clip((cfg["fade_top"] - yn) / max(cfg["fade_top"], 1e-6), 0, 1) ** 1.2 * 0.20
    tb = np.clip((yn - (1.0 - cfg["fade_bottom"])) / max(cfg["fade_bottom"], 1e-6), 0, 1) ** 2.2 * 0.94
    fade = np.clip(tt + tb, 0, 1)
    a = a * (1.0 - fade[..., None]) + cfg["fade_to"] * fade[..., None]
    a += np.random.default_rng(6).normal(0, cfg["grain"], a.shape)
    # 浅色模板: 顶部轻微压暗(像受光渐晕), 让白色标题在浅色墙面上也读得清
    if tpl in ("celebration", "soft", "pop"):
        ts = np.clip((120.0 - yy) / 120.0, 0, 1) ** 1.2 * 0.30
        a = a * (1.0 - ts[..., None])
    photo = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "RGB")

    # 蒙版
    mask = Image.new("L", (pw, ph), 0)
    md = ImageDraw.Draw(mask)
    if mask_kind == "round_bottom":
        md.rounded_rectangle([0, -160, pw - 1, ph - 1], radius=132, fill=255)
    elif mask_kind == "diagonal":
        md.polygon([(0, 0), (pw, 0), (pw, ph - 96), (0, ph)], fill=255)
    else:  # band / full
        md.rectangle([0, 0, pw - 1, ph - 1], fill=255)
    m = np.asarray(mask).astype(np.float32) / 255.0
    fside = np.clip(np.minimum(xx, pw - 1 - xx) /
                    (110.0 if tpl == "diorama" else (10.0 if tpl == "night" else 46.0)), 0, 1)
    ftop = 1.0 if mask_kind != "band" else np.clip(yy / 150.0, 0, 1)
    fbot = (1.0 if mask_kind == "round_bottom"
            else np.clip((ph - 1 - yy) / (ph * cfg["fade_bottom"]) / 0.9, 0, 1))
    m = np.minimum(np.minimum(m, fside), np.minimum(ftop, np.clip(fbot, 0, 1)))
    m = (m * m * (3 - 2 * m))
    mask = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(5))

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if tpl == "diorama":
        # 浮雕投影: 照片下缘一层柔和投影, 让照片像"立"在卡面上
        sm = mask.filter(ImageFilter.GaussianBlur(24)).point(lambda v: int(v * 0.55))
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sh.paste(Image.new("RGBA", (pw, ph), (0, 0, 0, 215)), (l, t + 24), sm)
        canvas.alpha_composite(sh)
    canvas.paste(photo, (l, t), mask)
    if tpl == "night":
        # 照片像"印进纸里": 上缘一道内侧阴影 + 下缘 AO, 四周不做硬框
        inset = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        idr = ImageDraw.Draw(inset)
        for i in range(30):
            a = int(34 * (1 - i / 30.0) ** 1.7)
            idr.line([(0, t + i), (W, t + i)], fill=(4, 7, 14, a))
        canvas.alpha_composite(inset.filter(ImageFilter.GaussianBlur(9)))
        ao = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ad = ImageDraw.Draw(ao)
        for i in range(64):
            a = int(48 * (1 - i / 64.0) ** 1.8)
            ad.line([(0, b - i), (W, b - i)], fill=(6, 9, 18, a))
        canvas.alpha_composite(ao.filter(ImageFilter.GaussianBlur(10)))
    if tpl == "diorama":
        # 顶缘反光(纸张/相纸受光的一条细亮边)
        rim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rectangle([l + 6, t, r - 7, t + 3], fill=(232, 201, 138, 46))
        canvas.alpha_composite(rim.filter(ImageFilter.GaussianBlur(2.2)))
    return canvas


def _cutout_place(sub, bw, bh, cy):
    """透明主体模式: contain 缩放 + 柔和投影 + 底边溶解, 保留原透明(不铺照片带)。"""
    iw, ih = sub.size
    scale = min(bw / iw, bh / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    sub = sub.resize((nw, nh), Image.Resampling.LANCZOS)
    x, y = (W - nw) // 2, cy - nh // 2
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mask = sub.getchannel("A")
    # 底边溶解: 抠图常见的"齐边"在这里化开, 像被光吃掉
    arr = np.asarray(mask).astype(np.float32)
    yy = np.arange(nh, dtype=np.float32)[:, None]
    start = nh * 0.86
    fade = np.clip((nh - yy) / max(nh - start, 1.0), 0, 1) ** 1.3
    arr = arr * np.clip(fade, 0, 1)
    mask = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "L")
    out = sub.copy()
    out.putalpha(mask)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", (nw, nh), (0, 0, 0, 190)), (x + 10, y + 24),
             mask.filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.65)))
    canvas.alpha_composite(sh)
    canvas.paste(out, (x, y), mask)
    return canvas


# ---------------------------------------------------------------- 背景
def background(tpl):
    p = PALETTE[tpl]
    im = Image.new("RGBA", (W, H), p["bg"] + (255,))
    if tpl == "celebration":
        for (cx, cy, r, col, al, bl) in [(180, 150, 430, p["b"], 70, 150),
                                         (900, 1180, 420, p["a"], 44, 150),
                                         (880, 380, 220, p["d"], 40, 120),
                                         (240, 1320, 300, p["c"], 36, 140)]:
            _glow(im, cx, cy, r, col, al, bl)
        _bands(im, p, [(0, 0, W, 8)])
    elif tpl == "soft":
        for (cx, cy, r, col, al, bl) in [(200, 240, 460, p["a"], 52, 170),
                                         (860, 1240, 480, p["b"], 60, 180),
                                         (520, 760, 380, p["c"], 26, 170)]:
            _glow(im, cx, cy, r, col, al, bl)
    elif tpl == "pop":
        d = ImageDraw.Draw(im)
        d.rectangle([0, 1180, W, H], fill=p["a"] + (255,))              # 蓝色块
        d.polygon([(0, 1120), (W, 1010), (W, 1080), (0, 1190)], fill=p["soft"] + (255,))
        d.rectangle([640, 0, W, 74], fill=p["b"] + (255,))              # 黄色条
        d.rectangle([0, 74, 210, 92], fill=p["c"] + (255,))
        d.ellipse([820, 1210, 980, 1370], fill=p["d"] + (255,))
        for i in range(9):                                              # 半调点阵(移到左下空白处)
            for j in range(4):
                x, y = 350 + i * 24, 1412 + j * 24
                r = 4.8 - j * 0.8
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 170))
    elif tpl == "night":
        # 高级款底色: 深蓝黑纸基 + 左上暖光 + 右下冷补光, 再做纸张质感
        d = ImageDraw.Draw(im)
        for y in range(H):
            t = y / H
            d.line([(0, y), (W, y)],
                   fill=(int(11 + 9 * t), int(15 + 13 * t), int(26 + 18 * t)) + (255,))
        im = im.convert("RGB").convert("RGBA")
        for (cx, cy, r, col, al, bl) in [(190, 150, 470, (156, 124, 66), 40, 150),
                                         (880, 1330, 500, (36, 58, 92), 30, 160)]:
            _glow(im, cx, cy, r, col, al, bl)
        im = paper_grain(im, fine=10.0, fibers=300, mottle=0.06)
        # 纸边压深: 让卡牌有一点点"实体边"的暗示
        edge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ed = ImageDraw.Draw(edge)
        for i in range(14):
            a = int(16 * (1 - i / 14.0) ** 1.6)
            ed.rectangle([i, i, W - 1 - i, H - 1 - i], outline=(0, 0, 0, a), width=1)
        im.alpha_composite(edge)
    else:  # diorama 立体画框: 深底 + 光轴 + 主体后方暖光
        d = ImageDraw.Draw(im)
        for y in range(H):
            t = y / H
            d.line([(0, y), (W, y)], fill=(int(8 + 10 * t), int(11 + 15 * t), int(20 + 26 * t)) + (255,))
        im = im.convert("RGB").convert("RGBA")
        _glow(im, 512, 600, 470, (150, 96, 40), 58, 170)
        _glow(im, 150, 200, 340, (196, 82, 63), 30, 150)
        _glow(im, 900, 1340, 420, (120, 96, 52), 34, 160)
        shaft = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shaft).polygon([(300, 0), (520, 0), (720, H), (520, H)],
                                      fill=(232, 201, 138, 16))
        im.alpha_composite(shaft.filter(ImageFilter.GaussianBlur(90)))
        ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([512 - 372, 690 - 372, 512 + 372, 690 + 372],
                                     outline=(232, 201, 138, 20), width=1)
        im.alpha_composite(ring.filter(ImageFilter.GaussianBlur(0.6)))
    if tpl != "night":
        _metal_hair(im, tpl)
    arr = np.asarray(im.convert("RGB")).astype(np.float32) + \
        np.random.default_rng(9).normal(0, 2.0, (H, W, 3))
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    if tpl in ("night", "pop", "celebration", "diorama"):
        yy, xx = np.mgrid[0:H, 0:W]
        dd = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        vig = 1.0 - np.clip((dd - 0.45) / 0.95, 0, 1) ** 1.5 * (0.45 if tpl in ("night", "diorama") else 0.14)
        arr = np.asarray(im.convert("RGB")).astype(np.float32) * vig[..., None]
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    return im


def _glow(im, cx, cy, r, col, al, bl):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (al,))
    im.alpha_composite(layer.filter(ImageFilter.GaussianBlur(bl)))


def _metal_hair(im, tpl):
    hair = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hair)
    col = (30, 30, 30) if tpl == "pop" else ((200, 170, 120) if tpl == "diorama" else (150, 150, 150))
    for _ in range(180):
        y = random.randint(0, H - 1)
        hd.line([(random.randint(0, W - 300), y), (random.randint(0, W), y)],
                fill=col + (random.randint(3, 7),), width=1)
    im.alpha_composite(hair)


def paper_grain(im, fine=9.0, fibers=220, mottle=0.045, seed=17):
    """纸张/印刷质感: 细颗粒 + 纸纤维 + 低频云斑。仅用于静态高级感(非发光特效)。"""
    rng = np.random.default_rng(seed)
    arr = np.asarray(im.convert("RGB")).astype(np.float32)
    # 1) 细颗粒(印刷网点感)
    arr += rng.normal(0, fine, arr.shape).astype(np.float32)
    # 2) 纸纤维(极低对比的横向短纹)
    fib = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(fib)
    for _ in range(fibers):
        y = random.randint(0, H - 1)
        x0 = random.randint(0, W - 1)
        fd.line([(x0, y), (x0 + random.randint(20, 150), y)], fill=random.randint(6, 16), width=1)
    arr += (np.asarray(fib.filter(ImageFilter.GaussianBlur(0.6))).astype(np.float32)[..., None] - 3.0)
    # 3) 低频云斑(纸浆不匀)
    low = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("L")
    low = low.resize((max(2, W // 24), max(2, H // 24)), Image.Resampling.BILINEAR)
    low = low.resize((W, H), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(6))
    lo = np.asarray(low).astype(np.float32) - float(np.asarray(low).mean())
    arr += (lo[..., None] * mottle)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def _bands(im, p, rects):
    d = ImageDraw.Draw(im)
    for (x0, y0, x1, y1) in rects:
        d.rectangle([x0, y0, x1, y1], fill=p["a"] + (255,))


# ---------------------------------------------------------------- 线稿(照片区极细刻线)
def lineart(tpl):
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    col = (54, 54, 54)
    if tpl == "celebration":
        d.arc([120, 300, 640, 820], start=200, end=340, fill=col, width=2)
        d.line([(150, 880), (400, 880)], fill=(70, 70, 70), width=2)
    elif tpl == "soft":
        d.line([(120, 420), (904, 420)], fill=(96, 96, 96), width=1)
        d.arc([300, 200, 720, 620], start=30, end=150, fill=col, width=1)
    elif tpl == "pop":
        d.line([(120, 300), (120, 900)], fill=(30, 30, 30), width=2)
        d.line([(160, 300), (160, 700)], fill=(60, 60, 60), width=2)
        d.arc([560, 560, 900, 900], start=180, end=300, fill=col, width=2)
    elif tpl == "diorama":
        d.arc([180, 380, 700, 900], start=205, end=335, fill=(58, 58, 58), width=2)
        d.arc([300, 500, 900, 1100], start=25, end=150, fill=(66, 66, 66), width=2)
        d.line([(140, 980), (420, 980)], fill=(60, 60, 60), width=1)
    else:
        for r, a in ((330, 46), (300, 34)):
            d.ellipse([512 - r, 660 - r, 512 + r, 660 + r], outline=(a, a, a), width=1)
        d.line([(150, 300), (330, 480)], fill=col, width=2)
    return im


# ---------------------------------------------------------------- 装饰层(前景, 视差最大)
def effects(tpl):
    p = PALETTE[tpl]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def ok(x, y, rx=240, ry=300, cy=640, leak=0.16):
        return math.hypot((x - 512) / rx, (y - cy) / ry) > 1.0 or random.random() < leak

    pal = [p["a"], p["b"], p["c"], p["d"]]
    if tpl == "celebration":
        for _ in range(34):
            x, y = random.randint(30, W - 30), random.randint(30, H - 30)
            if not ok(x, y):
                continue
            c = random.choice(pal)
            k = random.random()
            if k < 0.4:
                r = random.uniform(5, 16)
                ImageDraw.Draw(im).ellipse([x - r, y - r, x + r, y + r], fill=c + (random.randint(90, 165),))
            elif k < 0.7:
                ImageDraw.Draw(im).polygon(rot_rect(x, y, random.uniform(5, 9), random.uniform(9, 15),
                                                    random.uniform(0, 180)), fill=c + (130,))
            else:
                star4(ImageDraw.Draw(im), x, y, random.uniform(6, 12), c + (170,), ratio=0.3)
        for (box, a0, a1) in [((-40, 120, 420, 580), 20, 130), ((640, 900, 1100, 1360), 200, 320)]:
            arc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(arc).arc(box, start=a0, end=a1, fill=p["d"] + (72,), width=2)
            im.alpha_composite(arc.filter(ImageFilter.GaussianBlur(0.8)))
    elif tpl == "soft":
        for _ in range(3):
            x, y = random.randint(120, W - 120), random.randint(150, 900)
            r = random.uniform(70, 130)
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(lay).ellipse([x - r, y - r, x + r, y + r], fill=p["a"] + (34,))
            im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(16)))
        for _ in range(9):
            x, y = random.randint(60, W - 60), random.randint(120, 1150)
            if not ok(x, y, 260, 320, 660, 0.25):
                continue
            r = random.uniform(7, 13)
            pet = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(pet).polygon(rot_rect(x, y, r * 1.5, r * 0.75, random.uniform(0, 180)),
                                        fill=p["a"] + (150,))
            im.alpha_composite(pet.filter(ImageFilter.GaussianBlur(1.2)))
        star4(ImageDraw.Draw(im), 512, 1060, 7, p["c"] + (150,))
    elif tpl == "pop":
        d = ImageDraw.Draw(im)
        for _ in range(10):
            x, y = random.randint(40, W - 40), random.randint(40, H - 40)
            if not ok(x, y, 250, 300, 620, 0.2):
                continue
            c = random.choice(pal)
            if random.random() < 0.5:
                d.rectangle([x - 14, y - 14, x + 14, y + 14], fill=c + (200,))
            else:
                star4(d, x, y, random.uniform(12, 22), p["ink"] + (215,), ratio=0.32)
        for i in range(6):
            d.line([(60 + i * 6, 1040), (60 + i * 6, 1090)], fill=p["b"] + (220,), width=3)
        d.arc([700, 1080, 1000, 1250], start=180, end=320, fill=p["ink"] + (200,), width=5)
    elif tpl == "diorama":
        def clear(x, y):
            if 1140 < y < 1450:          # 底部文字区不放任何粒子
                return False
            return math.hypot((x - 512) / 1.0, (y - 600) / 1.3) > 250 or random.random() < 0.14
        # 长笔触(暖金 + 余烬色双描边): 夹在主体与文字之间的图形层
        strokes = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(strokes)
        for i in range(9):
            x0, y0 = random.randint(60, W - 60), random.randint(120, H - 220)
            if not clear(x0, y0):
                continue
            ang = random.uniform(-0.9, 0.9) + (math.pi if i % 2 else 0)
            ln = random.uniform(240, 460)
            c, s = math.cos(ang), math.sin(ang)
            pts = []
            for k in range(26):
                u = k / 25
                bend = math.sin(u * math.pi) * random.uniform(10, 42)
                pts.append((x0 + c * ln * u - s * bend, y0 + s * ln * u + c * bend))
            for k in range(25):
                wd = max(1, int(9 * (1 - k / 25) ** 1.4))
                a = int(130 * (1 - k / 25) ** 0.9)
                sd.line([pts[k], pts[k + 1]], fill=(232, 201, 138, a), width=wd)
                sd.line([(pts[k][0] + 3, pts[k][1] + 2), (pts[k + 1][0] + 3, pts[k + 1][1] + 2)],
                        fill=(196, 82, 63, int(a * 0.55)), width=max(1, wd - 2))
        im.alpha_composite(strokes.filter(ImageFilter.GaussianBlur(0.8)))
        # 箔片碎屑
        for _ in range(16):
            x, y = random.randint(40, W - 40), random.randint(60, H - 200)
            if not clear(x, y):
                continue
            c = random.choice([(232, 201, 138), (196, 82, 63), (242, 232, 213), (217, 140, 122)])
            ImageDraw.Draw(im).polygon(
                rot_rect(x, y, random.uniform(4, 7), random.uniform(14, 26), random.uniform(0, 180)),
                fill=c + (random.randint(120, 200),))
        # 细星点 + 十字星芒
        far = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fd = ImageDraw.Draw(far)
        for _ in range(34):
            x, y = random.randint(20, W - 20), random.randint(20, H - 20)
            if not clear(x, y):
                continue
            r = random.uniform(1.2, 3.2)
            fd.ellipse([x - r, y - r, x + r, y + r], fill=(255, 244, 220, random.randint(70, 140)))
        im.alpha_composite(far.filter(ImageFilter.GaussianBlur(0.5)))
        for _ in range(9):
            x, y = random.randint(70, W - 70), random.randint(70, H - 180)
            if not clear(x, y):
                continue
            g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(g)
            r = random.uniform(9, 18)
            a = random.randint(170, 225)
            star4(gd, x, y, r, (232, 201, 138, a), ratio=0.17)
            star4(gd, x, y, r * 0.4, (255, 250, 235, min(255, a + 30)), ratio=0.5)
            im.alpha_composite(g.filter(ImageFilter.GaussianBlur(0.6)))
        for _ in range(4):
            x, y = random.randint(60, W - 60), random.randint(60, H - 240)
            r = random.uniform(20, 34)
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(lay).ellipse([x - r, y - r, x + r, y + r], fill=(255, 226, 176, 26))
            im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(10)))
    else:  # night: 极克制的手工装饰 —— 不铺星尘, 只在纸面信息区做几处点缀
        for (x, y, r, a) in [(104, 1164, 6.0, 195), (890, 1452, 6.0, 175), (512, 1500, 5.0, 150)]:
            g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(g)
            star4(gd, x, y, r, p["gold"] + (a,), ratio=0.2)
            star4(gd, x, y, r * 0.4, (255, 250, 235, min(255, a + 25)), ratio=0.5)
            im.alpha_composite(g.filter(ImageFilter.GaussianBlur(0.5)))
        dd = ImageDraw.Draw(im)
        for (x, y, r, a) in [(68, 1206, 2.6, 130), (956, 1206, 2.6, 130)]:
            dd.ellipse([x - r, y - r, x + r, y + r], fill=p["gold"] + (a,))
        arc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(arc).arc([560, 1386, 984, 1584], start=192, end=318,
                                fill=p["gold"] + (56,), width=1)
        im.alpha_composite(arc.filter(ImageFilter.GaussianBlur(0.7)))
        bokeh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(bokeh).ellipse([660, 1210, 960, 1460], fill=(255, 228, 178, 26))
        im.alpha_composite(bokeh.filter(ImageFilter.GaussianBlur(40)))
    return im


# ---------------------------------------------------------------- 排版 + 卡框(最前层)
def text_layer(tpl, cfg):
    """文案完全数据驱动: 未提供的字段一律不绘制(不虚构、不占位)。
    subtitle=小标题 · title=主标题 · tagline=短句 · technique=日期 · edition=编号 · age=年龄 · name=名字。"""
    p = PALETTE[tpl]
    HB = str(cfg.get("subtitle") or "").strip()
    MAIN = str(cfg.get("title") or "").strip()
    TAG = str(cfg.get("tagline") or "").strip()
    DATE = str(cfg.get("technique") or "").strip()
    NO = str(cfg.get("edition") or "").strip()
    NAME = str(cfg.get("name") or "").strip()
    AGE = str(cfg.get("age") or "").strip()
    WISH = str(cfg.get("wish") or "").strip()
    YEAR = (DATE.split(".")[0] if DATE else "")
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    if tpl == "celebration":
        d.rectangle([26, 26, W - 27, H - 27], outline=p["ink"] + (205,), width=2)
        for (x, y, sx, sy) in [(26, 26, 1, 1), (W - 27, 26, -1, 1), (26, H - 27, 1, -1), (W - 27, H - 27, -1, -1)]:
            d.line([(x, y), (x + sx * 56, y)], fill=p["ink"] + (165,), width=1)
            d.line([(x, y), (x, y + sy * 56)], fill=p["ink"] + (165,), width=1)
        star4(d, 96, 96, 8, p["a"] + (215,))
        star4(d, W - 96, H - 96, 8, p["b"] + (235,))
        tracked(d, (W / 2, 122), HB, font(SANS_SB, 25), (255, 255, 255, 246), 11.5, True,
                shadow=(1, 2, (40, 34, 28, 120)))
        if NAME:
            tracked(d, (W / 2, 172), f"FOR {NAME.upper()}", font(SANS, 15), (255, 255, 255, 220), 5.0, True,
                    shadow=(1, 1, (40, 34, 28, 110)))
        if AGE:
            f = font(SANS_BLACK, 232)
            d.text((96 + 4, 1252 + 4), AGE, font=f, fill=p["b"] + (255,), anchor="ls")
            d.text((96, 1252), AGE, font=f, fill=p["a"] + (255,), anchor="ls")
            aw = d.textlength(AGE, font=f)
            d.text((96 + aw + 10, 1252 - 128), "TH", font=font(SANS_SB, 48), fill=p["c"] + (255,), anchor="ls")
            tracked(d, (100, 1316), MAIN, font(SERIF, 54), p["ink"] + (250,), 4.0)
        elif MAIN:                      # 未提供年龄 → 用主标题当 hero; 两者都没有就留白
            tracked(d, (96, 1252), MAIN, font(SERIF, 118), p["ink"] + (250,), 2.0)
        elif YEAR:
            tracked(d, (96, 1252), YEAR, font(SANS_BLACK, 132), p["c"] + (255,), 3.0)
        if TAG:
            tracked(d, (104, 1364), TAG, font(SANS, 14), p["ink"] + (200,), 5.0)
        xr = W - 108
        if DATE:
            tracked(d, (xr - tw(d, DATE, font(SANS, 25), 2.0), 1300), DATE, font(SANS, 25), p["ink"] + (235,), 2.0)
        tracked(d, (xr - tw(d, NO, font(SANS, 18), 1.4), 1338), NO, font(SANS, 18), p["ink"] + (215,), 1.4)
        d.ellipse([xr - 96, 1382, xr - 60, 1418], fill=p["b"] + (255,))
        d.ellipse([xr - 52, 1390, xr - 24, 1418], fill=p["d"] + (255,))
        d.ellipse([xr - 18, 1382, xr + 10, 1410], fill=p["a"] + (255,))

    elif tpl == "soft":
        d.rectangle([34, 34, W - 35, H - 35], outline=p["gold"] + (200,), width=2)
        d.rectangle([48, 48, W - 49, H - 49], outline=p["gold"] + (120,), width=1)
        for (x, y) in [(34, 34), (W - 35, 34), (34, H - 35), (W - 35, H - 35)]:
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=p["gold"] + (220,))
        tracked(d, (W / 2, 148), HB, font(SANS, 22), (255, 253, 250, 245), 10.0, True,
                shadow=(1, 1, (90, 80, 70, 110)))
        if NAME:
            tracked(d, (W / 2, 190), f"FOR {NAME.upper()}", font(SANS, 13), (255, 253, 250, 225), 4.5, True,
                    shadow=(1, 1, (90, 80, 70, 100)))
        cx, cy, r = 178, 1252, 76
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=p["gold"] + (190,), width=1)
        if AGE:
            d.text((cx, cy + 30), AGE, font=font(SERIF, 84), fill=p["gold"] + (250,), anchor="ms")
            tracked(d, (cx, cy + 52), "YEARS", font(SANS, 11), p["gold"] + (190,), 3.0, True)
        d.line([(296, 1150), (296, 1420)], fill=p["gold"] + (150,), width=1)
        tracked(d, (340, 1236), MAIN, font(SERIF, 66), p["ink"] + (250,), 2.0)
        if TAG:
            tracked(d, (344, 1284), TAG, font(SANS, 13), p["ink"] + (185,), 5.0)
        if DATE:
            tracked(d, (344, 1336), DATE, font(SANS, 22), p["ink"] + (220,), 2.0)
        tracked(d, (344, 1374), NO, font(SANS, 17), p["ink"] + (200,), 1.4)
        star4(d, W - 120, 1252, 8, p["gold"] + (170,))

    elif tpl == "pop":
        d.rectangle([20, 20, W - 21, H - 21], outline=p["ink"] + (235,), width=3)
        tracked(d, (72, 132), HB, font(SANS_BLACK, 30), p["ink"] + (255,), 10.0)
        if AGE:
            f = font(SANS_BLACK, 296)
            d.text((76 + 7, 1240 + 7), AGE, font=f, fill=p["b"] + (255,), anchor="ls")
            d.text((76, 1240), AGE, font=f, fill=p["ink"] + (255,), anchor="ls")
            aw = d.textlength(AGE, font=f)
            d.text((76 + aw + 8, 1240 - 168), "TH", font=font(SANS_BLACK, 62), fill=p["c"] + (255,), anchor="ls")
            tracked(d, (82, 1300), MAIN, font(SANS_BLACK, 38), p["ink"] + (255,), 6.0)
        elif MAIN:                      # 无年龄: 主标题当字标; 只有日期就显示年份
            tracked(d, (76, 1240), MAIN, font(SANS_BLACK, 116), p["ink"] + (255,), 2.0)
            if YEAR:
                tracked(d, (80, 1300), YEAR, font(SANS_BLACK, 54), p["c"] + (255,), 4.0)
        elif YEAR:
            tracked(d, (76, 1240), YEAR, font(SANS_BLACK, 116), p["ink"] + (255,), 2.0)
        if NAME:
            tracked(d, (84, 1352), f"FOR {NAME.upper()}", font(SANS_SB, 20), p["ink"] + (235,), 3.0)
        xr = W - 80
        pill_w = tw(d, NO, font(SANS_BLACK, 18), 1.2) + 40
        d.rounded_rectangle([xr - pill_w, 1412, xr, 1456], radius=22, fill=p["ink"] + (255,))
        tracked(d, (xr - pill_w + 20, 1430), NO, font(SANS_BLACK, 18), (255, 255, 255, 255), 1.2)
        if DATE:
            tracked(d, (xr - tw(d, DATE, font(SANS_BLACK, 22), 1.6), 1382), DATE,
                    font(SANS_BLACK, 22), p["ink"] + (255,), 1.6)

    elif tpl == "diorama":
        # 双线暖金框 + 四角星芒
        d.rectangle([30, 30, W - 31, H - 31], outline=p["gold"] + (215,), width=2)
        d.rectangle([46, 46, W - 47, H - 47], outline=p["a"] + (165,), width=1)
        for (x, y, sx, sy) in [(30, 30, 1, 1), (W - 31, 30, -1, 1), (30, H - 31, 1, -1), (W - 31, H - 31, -1, -1)]:
            d.line([(x, y), (x + sx * 64, y)], fill=p["gold"] + (185,), width=1)
            d.line([(x, y), (x, y + sy * 64)], fill=p["gold"] + (185,), width=1)
            star4(d, x + sx * 82, y + sy * 82, 7, p["gold"] + (200,))
        tracked(d, (W / 2, 152), HB, font(SANS_SB, 26), (242, 232, 213, 240), 11.5, True)
        star4(d, W / 2, 184, 6, p["gold"] + (215,))
        d.line([(W / 2 - 152, 184), (W / 2 - 32, 184)], fill=p["gold"] + (130,), width=1)
        d.line([(W / 2 + 32, 184), (W / 2 + 152, 184)], fill=p["gold"] + (130,), width=1)
        if NAME:
            tracked(d, (W / 2, 216), f"FOR {NAME.upper()}", font(SANS, 13), p["gold"] + (195,), 5.0, True)
        y = 1210
        for i in range(816):
            al = int(min(1.0, min(i, 815 - i) / 60.0) * 62)
            d.point((104 + i, y), fill=p["gold"] + (al,))
        xl, xr = 104, W - 104
        if AGE:
            f = font(SERIF, 196)
            d.text((xl + 4, 1310 + 4), AGE, font=f, fill=p["b"] + (150,), anchor="ls")
            d.text((xl, 1310), AGE, font=f, fill=(240, 220, 178, 255), anchor="ls")
            aw = d.textlength(AGE, font=f)
            star4(d, xl + aw + 32, 1196, 7.5, p["gold"] + (205,))
            tracked(d, (xl + 4, 1364), MAIN, font(SERIF, 48), (242, 232, 213, 248), 6.5)
            if TAG:
                tracked(d, (xl + 6, 1400), TAG, font(SANS, 16), p["gold"] + (155,), 5.0)
        else:
            tracked(d, (xl, 1332), MAIN, font(SERIF, 100), (242, 232, 213, 255), 1.5)
            if TAG:
                tracked(d, (xl + 4, 1372), TAG, font(SANS, 16), p["gold"] + (155,), 6.0)
        if DATE:
            tracked(d, (xr - tw(d, DATE, font(SANS, 26), 2.0), 1250), DATE, font(SANS, 26), p["gold"] + (232,), 2.0)
        tracked(d, (xr - tw(d, NO, font(SANS, 19), 1.4), 1290), NO, font(SANS, 19), (206, 186, 146, 235), 1.4)
    else:  # night: 高级款排版 —— 上方标题带 / 中部照片带 / 下方信息区, 不含 TCG 式文案
        xl, xr = 104, W - 104
        # 卡框: 外细线 + 内细线 + 四角短线 + 极小星芒(发丝级, 无霓虹)
        d.rectangle([30, 30, W - 31, H - 31], outline=p["gold"] + (208,), width=2)
        d.rectangle([44, 44, W - 45, H - 45], outline=p["a"] + (118,), width=1)
        for (x, y, sx, sy) in [(30, 30, 1, 1), (W - 31, 30, -1, 1), (30, H - 31, 1, -1), (W - 31, H - 31, -1, -1)]:
            d.line([(x, y), (x + sx * 58, y)], fill=p["gold"] + (182,), width=1)
            d.line([(x, y), (x, y + sy * 58)], fill=p["gold"] + (182,), width=1)
            star4(d, x + sx * 74, y + sy * 74, 5.0, p["gold"] + (170,))
        # —— 上方标题带 ——
        if NAME:
            tracked(d, (W / 2, 62), f"FOR {NAME.upper()}", font(SANS, 12), p["gold"] + (180,), 5.0, True)
        if HB:
            tracked(d, (W / 2, 104), HB, font(SANS_SB, 25), (236, 222, 188, 242), 11.0, True)
        d.line([(xl, 136), (xr, 136)], fill=p["gold"] + (88,), width=1)
        star4(d, W / 2, 136, 4.2, p["gold"] + (168,))
        # —— 照片上缘登记线(把这行当作"印刷起点") ——
        d.line([(0, 150), (W, 150)], fill=p["gold"] + (72,), width=1)
        # —— 下方信息区: 大数字与右侧信息同处一个视觉带 ——
        d.line([(xl, 1206), (xr, 1206)], fill=p["gold"] + (76,), width=1)
        if DATE:
            tracked(d, (xr - tw(d, DATE, font(SANS, 25), 2.2), 1290), DATE,
                    font(SANS, 25), p["gold"] + (226,), 2.2)
        if NO:
            tracked(d, (xr - tw(d, NO, font(SANS, 18), 1.6), 1330), NO,
                    font(SANS, 18), (178, 162, 130, 225), 1.6)
        if AGE:
            f = font(SERIF, 176)
            d.text((xl + 3, 1384 + 3), AGE, font=f, fill=(8, 11, 20, 155), anchor="ls")   # 压印感阴影
            d.text((xl, 1384), AGE, font=f, fill=(241, 231, 205, 255), anchor="ls")
        if WISH:
            tracked(d, (xl + 4, 1432), WISH, font(SANS, 15), (214, 200, 170, 205), 4.5)
    return im


# ---------------------------------------------------------------- 每套模板的构图定义
def photo_box(tpl):
    return {
        "celebration": ((0, 0, 1024, 966), "round_bottom"),
        "soft": ((0, 0, 1024, 1004), "band"),
        "pop": ((0, 0, 1024, 1092), "diagonal"),
        "night": ((0, 150, 1024, 1150), "band"),
        "diorama": ((0, 96, 1024, 1180), "band"),
    }[tpl]


def main():
    photo = sys.argv[1]
    proj = Path(sys.argv[2])
    tpl = sys.argv[3] if len(sys.argv) > 3 else "night"
    if tpl not in TEMPLATES:
        raise SystemExit("模板必须是: " + ", ".join(TEMPLATES))
    out = proj / "assets"
    out.mkdir(parents=True, exist_ok=True)
    cfg = {}
    cp = proj / "card-config.json"
    if cp.exists():
        cfg = json.loads(cp.read_text(encoding="utf8"))

    ImageOps.exif_transpose(Image.open(photo)).convert("RGB").save(out / "source.png")
    box, kind = photo_box(tpl)
    photo_layer(photo, tpl, box, kind).save(out / "subject.png")
    background(tpl).save(out / "background.png")
    lineart(tpl).save(out / "lineart.png")
    text_layer(tpl, cfg).save(out / "text.png")
    effects(tpl).save(out / "effects.png")
    log(f"{tpl} 五层已生成 → {out}")


if __name__ == "__main__":
    main()
