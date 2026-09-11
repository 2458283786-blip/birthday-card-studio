# -*- coding: utf-8 -*-
"""
Birthday 系列 · 效果图离线渲染
===============================
用与网页 shader 完全相同的数学, 在本地把四套模板渲染成 PNG 效果图:
  * 层间视差: uv' = uv + view.xy / max(|view.z|,.4) * depth * .20
  * 视角门控: amount = foil * mix(.15, 1, clamp((|view.xy| - .12) * 3.2, 0, 1))
  * 虹彩: .74 + .17*cos(...); 条纹 sweep pow(...,10); 边缘高光; sparkle step(.9975)
  * 文字层最后叠加(不参与 Holo, 与网页一致)
每个模板输出 4 态: 正面静止 / 轻微倾斜 / 大角度 Holo / 背面设计
再合成: 每套 1x4 联图 + 四套 4x4 总图 + 预览页 index.html

用法: python card-studio/render_previews.py
"""
import json, math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SET = ROOT / "birthday-set"
OUT = SET / "previews"
TEMPLATES = ["celebration", "soft", "pop", "night", "diorama"]
STATES = [("front", "正面静止", -0.035, -0.15, None),
          ("tilt", "轻微倾斜", -0.105, -0.52, None),
          ("holo", "大角度 Holo", -0.42, -1.02, 0.82)]
FONTS = r"C:\Windows\Fonts"
SERIF = FONTS + r"\pala.ttf"
SANS = FONTS + r"\segoeui.ttf"
SANS_SB = FONTS + r"\seguisb.ttf"
BLACK = FONTS + r"\bahnschrift.ttf"
CJK = FONTS + r"\msyh.ttc"

BACK_STYLE = {
    "celebration": dict(bg1=(251, 246, 236), bg2=(246, 236, 218), ink=(58, 52, 44),
                        gold=(196, 150, 74), a1=(232, 121, 106), a2=(246, 210, 122), frame="thin"),
    "soft": dict(bg1=(247, 242, 234), bg2=(239, 231, 218), ink=(91, 82, 72),
                 gold=(216, 195, 160), a1=(232, 210, 206), a2=(216, 195, 160), frame="double"),
    "pop": dict(bg1=(255, 253, 246), bg2=(255, 248, 230), ink=(20, 20, 20),
                gold=(255, 212, 0), a1=(43, 76, 255), a2=(255, 75, 62), frame="bold"),
    "night": dict(bg1=(14, 21, 38), bg2=(7, 10, 18), ink=(240, 232, 214),
                  gold=(222, 201, 160), a1=(168, 135, 79), a2=(217, 166, 160), frame="double"),
    "diorama": dict(bg1=(12, 20, 36), bg2=(5, 7, 13), ink=(242, 232, 213),
                    gold=(232, 201, 138), a1=(168, 118, 58), a2=(196, 82, 63), frame="double"),
}


def f(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype(SANS, size)


def tracked(d, xy, text, fnt, fill, tracking=0.0, center=False):
    text = str(text)
    ws = [d.textlength(ch, font=fnt) for ch in text]
    total = sum(ws) + tracking * max(0, len(text) - 1)
    x = xy[0] - total / 2 if center else xy[0]
    for ch, w in zip(text, ws):
        d.text((x, xy[1]), ch, font=fnt, fill=fill)
        x += w + tracking


def tw(d, text, fnt, tracking=0.0):
    text = str(text)
    return sum(d.textlength(ch, font=fnt) for ch in text) + tracking * max(0, len(text) - 1)


# ---------------------------------------------------------------- shader 数学
def view_vector(rx, ry):
    """与查看器一致: 相机位置变换到卡牌局部空间后归一化。"""
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    v = np.array([-cx * sy, sx, cx * cy], dtype=np.float64)
    return v / np.linalg.norm(v)


def parallax_shift(view, depth):
    return (view[0] / max(abs(view[2]), 0.4) * depth * 0.20,
            view[1] / max(abs(view[2]), 0.4) * depth * 0.20)


def sample(arr, dx, dy, clip_alpha=False):
    """uv' = uv + (dx,dy); 内容在画面上反向移动。clip_alpha=True 时越界处 alpha 置 0。"""
    h, w = arr.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    sx = xs + dx * w
    sy = ys + dy * h
    if clip_alpha:
        valid = (sx >= 0) & (sx <= w - 1) & (sy >= 0) & (sy <= h - 1)
        sxc = np.clip(sx, 0, w - 1).astype(np.int32)
        syc = np.clip(sy, 0, h - 1).astype(np.int32)
        out = arr[syc, sxc].copy().astype(np.float32)
        out[..., 3] *= valid
        return out
    sxc = np.clip(sx, 0, w - 1).astype(np.int32)
    syc = np.clip(sy, 0, h - 1).astype(np.int32)
    return arr[syc, sxc].astype(np.float32)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def hash2(x, y):
    v = np.sin(x * 127.1 + y * 311.7) * 43758.5453
    return v - np.floor(v)


# ---------------------------------------------------------------- 材质系统(与 shader 同步)
MAT_INDEX = {"matte": 0, "pearl": 1, "foil": 2, "gloss": 3}


def material_setup(cfg):
    """返回 (types[frame,text,subject,bg], amounts[...], holoOn) —— 与 app.js 推导逻辑一致。"""
    p = cfg.get("parameters", {}) or {}
    mat = cfg.get("material", {}) or {}
    finish = str((cfg.get("appearance") or {}).get("finish") or "").lower()
    holo_on = mat.get("holoEnabled", True) is not False and finish != "original"
    regions = mat.get("regions", {}) or {}
    amounts = mat.get("amounts", {}) or {}
    foil_base = float(p.get("foil", 0.52))

    def t_of(k, d):
        return MAT_INDEX.get(str(regions.get(k) or d).lower(), MAT_INDEX[d])

    def a_of(k, d):
        return float(amounts[k]) if (k in amounts and amounts[k] is not None) else (0.0 if d == "text" else foil_base)

    types = [t_of("frame", "pearl"), t_of("text", "matte"), t_of("subject", "pearl"), t_of("background", "pearl")]
    amts = [a_of("frame", "frame"), a_of("text", "text"), a_of("subject", "subject"), a_of("background", "background")]
    if not holo_on:
        amts = [0.0, 0.0, 0.0, 0.0]
    return types, amts, holo_on


def pearl_film(u, v, view):
    phase = u * 0.85 + v * 0.55 + view[0] * 1.5 - view[1] * 0.9
    return 0.74 + 0.17 * np.cos(6.28318 * (phase[..., None] + np.array([0.0, 0.33, 0.67])))


def foil_film(u, v, view):
    phase = u * 0.62 + v * 0.38 + view[0] * 2.2 - view[1] * 1.3
    hi = 0.5 + 0.5 * np.sin(phase * 6.28318 * 1.6)
    return np.array([0.62, 0.46, 0.22]) * (1 - hi[..., None]) + np.array([1.0, 0.94, 0.72]) * hi[..., None]


def gloss_film(u, v, view):
    phase = u * 0.35 + v * 1.15 + view[1] * 1.4
    s = np.power(0.5 + 0.5 * np.sin(phase * 6.28318), 1.6)
    return np.array([0.84, 0.87, 0.90]) * (1 - s[..., None]) + 1.0 * s[..., None]


def style_film(u, v, view, mtype):
    if mtype > 2.5:
        return gloss_film(u, v, view)
    if mtype > 1.5:
        return foil_film(u, v, view)
    return pearl_film(u, v, view)


def apply_mat(col, u, v, view, mtype, amount, band, boost):
    if amount <= 0.001:
        return col
    f = style_film(u, v, view, mtype)
    lum = col[..., 0] * 0.2126 + col[..., 1] * 0.7152 + col[..., 2] * 0.0722
    col = col * (1.0 - amount * 0.11 * (1.0 - f) * (0.2 + band[..., None] * 0.8))
    col = col + f * (amount * band * boost * (0.028 + 0.06 * (1.0 - lum)))[..., None]
    return col


def compose_front(tpl, cfg, rx, ry, foil_override):
    """复刻 frontFragment 的合成顺序。"""
    A = SET / tpl / "assets"
    bg = np.asarray(Image.open(A / "background.png").convert("RGBA")).astype(np.float32)
    sub = np.asarray(Image.open(A / "subject.png").convert("RGBA")).astype(np.float32)
    fx = np.asarray(Image.open(A / "effects.png").convert("RGBA")).astype(np.float32)
    tx = np.asarray(Image.open(A / "text.png").convert("RGBA")).astype(np.float32)
    ln = np.asarray(Image.open(A / "lineart.png").convert("RGB")).astype(np.float32)
    h, w = bg.shape[:2]

    p = cfg["parameters"]
    view = view_vector(rx, ry)
    foil = float(foil_override if foil_override is not None else p.get("foil", 0.5))
    gate = float(np.clip((np.hypot(view[0], view[1]) - 0.12) * 3.2, 0, 1))
    amount = foil * (0.15 + 0.85 * gate)

    # 背景(EXTEND) -> 照片(CLIP, 按 alpha 混合) -> 前景装饰(CLIP)
    col = sample(bg, *parallax_shift(view, p.get("backgroundDepth", -0.25)))[..., :3] / 255.0
    s = sample(sub, *parallax_shift(view, p.get("subjectDepth", 0.32)), clip_alpha=True)
    sa = (s[..., 3:4] / 255.0)
    col = col * (1 - sa) + (s[..., :3] / 255.0) * sa
    e = sample(fx, *parallax_shift(view, p.get("effectsDepth", 0.6)), clip_alpha=True)
    ea = e[..., 3:4] / 255.0
    col = col * (1 - ea) + (e[..., :3] / 255.0) * ea

    # ---- 分区材质(边框 / 文字 / 主体 / 底纹), 与 app.js 的 shader 同步 ----
    ys, xs = np.mgrid[0:h, 0:w]
    u = xs / (w - 1)
    v = ys / (h - 1)
    types, amts, holo_on = material_setup(cfg)
    if foil_override is not None and holo_on:            # 预览用的临时提亮
        amts = [float(foil_override) if a > 0 else 0.0 for a in amts]
    gate = float(np.clip((np.hypot(view[0], view[1]) - 0.12) * 3.2, 0, 1))
    gate = 0.15 + 0.85 * gate
    band = np.power(0.5 + 0.5 * np.sin((u * 0.72 + v * 0.45 + view[0] * 1.2 + view[1] * 0.6) * 6.283), 10.0)
    edge = 1.0 - smoothstep(0.015, 0.06, np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v)))
    # 文字层: 按自己的景深采样(textDepth=0 即固定在最前)
    t = sample(tx, *parallax_shift(view, p.get("textDepth", 0.0)), clip_alpha=True)
    ta = t[..., 3:4] / 255.0
    boost = 1.7 if str((cfg.get("appearance") or {}).get("finish", "")).lower() == "gold" else 1.0
    w_frame = np.clip(edge, 0, 1)
    w_text = np.clip(ta[..., 0], 0, 1) * (1 - w_frame)
    w_sub = np.clip(sa[..., 0], 0, 1) * (1 - w_frame) * (1 - w_text)
    w_bg = np.clip(1 - w_frame - w_text - w_sub, 0, 1)
    c_sub = apply_mat(col, u, v, view, types[2], amts[2] * gate, band, boost)
    c_bg = apply_mat(col, u, v, view, types[3], amts[3] * gate, band, boost)
    col = (c_sub * w_sub[..., None] + c_bg * w_bg[..., None]
           + col * (w_frame + w_text)[..., None])
    a_frame = min(max(amts[0], 0.0), 1.0) * gate
    f_frame = style_film(u, v, view, types[0])
    col = col * (1 - (w_frame * a_frame)[..., None]) + (f_frame * 0.75 + 0.21) * (w_frame * a_frame)[..., None]
    spark = max(amts) * gate
    cell = np.floor(np.stack([u * 480.0, v * 720.0], axis=-1))
    fl = (hash2(cell[..., 0], cell[..., 1]) > 0.9975) * np.power(
        0.5 + 0.5 * np.sin(hash2(cell[..., 0] + 8, cell[..., 1]) * 30 + view[0] * 20), 10.0)
    col = col + style_film(u, v, view, types[0]) * (fl * spark)[..., None] * 0.08

    # 线稿辉光(以主体 UV 采样, 与 shader 一致)
    ls = sample(ln[..., :1] / 255.0, *parallax_shift(view, p.get("subjectDepth", 0.32)), clip_alpha=False)
    line = (1.0 - smoothstep(0.06, 0.25, ls[..., 0]))
    col = col + (line * sa[..., 0] * band * spark * 0.035)[..., None]

    # 文字: 只要有文字就合成; 材质强度为 0 时 apply_mat 原样返回(等同哑光)
    if w_text.max() > 0.001:
        c_text = apply_mat(t[..., :3] / 255.0, u, v, view, types[1], amts[1] * gate, band, boost)
        col = col * (1 - w_text[..., None]) + c_text * w_text[..., None]
    return np.clip(col, 0, 1)


# ---------------------------------------------------------------- 背面
def render_back(tpl, cfg):
    S = BACK_STYLE[cfg.get("backStyle", tpl)]
    style = cfg.get("backStyle", tpl)
    w, h = 1024, 1536
    g = np.linspace(0, 1, h)[:, None]
    bg = np.zeros((h, w, 3), np.float32)
    for i in range(3):
        bg[..., i] = (S["bg1"][i] / 255.0) * (1 - g) + (S["bg2"][i] / 255.0) * g
    im = Image.fromarray((bg * 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)
    if style == "pop":
        d.rectangle([0, 1330, w, h], fill=S["a1"] + (255,))
        d.rectangle([0, 0, w, 46], fill=S["gold"] + (255,))
        d.rectangle([740, 46, w, 64], fill=S["a2"] + (255,))
    elif style == "celebration":
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(lay).ellipse([-240, -210, 620, 650], fill=S["a2"] + (120,))
        lay = lay.filter(ImageFilter.GaussianBlur(150))
        im.alpha_composite(lay)
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(lay).ellipse([450, 820, 1300, 1670], fill=S["a1"] + (95,))
        im.alpha_composite(lay.filter(ImageFilter.GaussianBlur(150)))
    elif style in ("night", "diorama"):
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        rng = np.random.default_rng(3)
        for i in range(150):
            y = int(rng.random() * h)
            x0 = int(rng.random() * 600)
            ld.line([(x0, y), (x0 + int(rng.random() * 400) + 40, y)],
                    fill=(143, 162, 196, 14) if i % 2 else (201, 177, 132, 14), width=1)
        im.alpha_composite(lay)
        d.ellipse([512 - 300, 760 - 300, 512 + 300, 760 + 300], outline=S["gold"] + (18,), width=1)
    # 边框
    if S["frame"] == "bold":
        d.rectangle([26, 26, w - 27, h - 27], outline=S["ink"] + (255,), width=4)
    elif S["frame"] == "thin":
        d.rectangle([30, 30, w - 31, h - 31], outline=(58, 52, 44, 215), width=2)
        _star(d, 62, 62, 8, S["a1"] + (230,)); _star(d, w - 62, h - 62, 8, S["a2"] + (240,))
    else:
        d.rectangle([38, 38, w - 39, h - 39], outline=S["gold"] + (205,), width=2)
        d.rectangle([56, 56, w - 57, h - 57], outline=S["gold"] + (130,), width=1)
        for (x, y) in [(86, 86), (w - 86, 86), (86, h - 86), (w - 86, h - 86)]:
            _star(d, x, y, 7, S["gold"] + (200,))
    ink, gold = S["ink"] + (255,), S["gold"] + (255,)
    fam = BLACK if style == "pop" else SERIF
    # 背面 = 卡牌身份证: 只放 CARD # 与日期(可选 Created/Owned/QR), 不放主题文案
    tracked(d, (512, 312), cfg.get("edition") or "", f(SANS, 20), gold, 2.4, True)
    d.line([(432, 348), (592, 348)], fill=S["ink"] + (80,), width=1)
    age = str(cfg.get("age") or "").strip()
    if age:
        wm = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        col = {"night": (222, 201, 160, 22), "diorama": (232, 201, 138, 24),
               "pop": (20, 20, 20, 18),
               "celebration": (232, 121, 106, 30), "soft": (216, 195, 160, 56)}[style]
        ImageDraw.Draw(wm).text((512, 880), age, font=f(fam, 320 if style != "pop" else 300),
                                fill=col, anchor="ms")
        im.alpha_composite(wm)
    d = ImageDraw.Draw(im)
    tracked(d, (512, 900), cfg.get("title") or "",
            f(fam, 86 if style == "pop" else (84 if style == "celebration" else 92)), ink, 2, True)
    _star(d, 512, 940, 5, S["ink"] + (140,))
    d.line([(392, 940), (486, 940)], fill=S["ink"] + (70,), width=1)
    d.line([(538, 940), (632, 940)], fill=S["ink"] + (70,), width=1)
    if cfg.get("tagline"):
        tracked(d, (512, 982), cfg["tagline"], f(SANS, 16), S["ink"] + (160,), 5.5, True)
    # 收藏凭证区: Card ID 已在顶部; 其余字段有数据才显示(不留占位)
    d.line([(372, 1104), (652, 1104)], fill=S["ink"] + (60,), width=1)
    if cfg.get("name"):
        tracked(d, (512, 1150), "FOR " + str(cfg["name"]).upper(), f(SANS, 16), ink, 4.0, True)
    if cfg.get("technique"):
        tracked(d, (512, 1206), cfg["technique"], f(SANS, 22), gold, 2.0, True)
    if cfg.get("wish"):
        tracked(d, (512, 1258), cfg["wish"], f(SERIF, 21), S["ink"] + (190,), 0.6, True)

    def field(label, y, value):
        if not value:
            return
        tracked(d, (512, y), label, f(SANS, 12), S["ink"] + (150,), 3.2, True)
        tracked(d, (512, y + 30), value, f(SANS, 17), ink, 1.0, True)

    field("CREATED BY", 1330, cfg.get("createdBy") or "")
    field("OWNED BY", 1396, cfg.get("ownedBy") or "")
    return im.convert("RGB")


def _star(d, cx, cy, r, fill, ratio=0.22):
    d.polygon([(cx, cy - r), (cx + r * ratio, cy - r * ratio), (cx + r, cy),
               (cx + r * ratio, cy + r * ratio), (cx, cy + r),
               (cx - r * ratio, cy + r * ratio), (cx - r, cy), (cx - r * ratio, cy - r * ratio)], fill=fill)


# ---------------------------------------------------------------- 展示排版
def present(card_rgb, ry, bg=(10, 14, 22), shadow=True):
    """把卡面放进展示板, 倾斜态做横向透视压缩 + 柔和投影。"""
    W, H = 1240, 1720
    canvas = Image.new("RGB", (W, H), bg)
    card = card_rgb.convert("RGBA")
    target_h = 1480
    scale = target_h / card.height
    card = card.resize((int(card.width * scale), target_h), Image.Resampling.LANCZOS)
    if ry:
        squeeze = max(0.45, math.cos(abs(ry)))
        card = card.resize((max(1, int(card.width * squeeze)), target_h), Image.Resampling.LANCZOS)
    x = (W - card.width) // 2
    y = (H - card.height) // 2 - 10
    if shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rectangle([x + 16, y + 26, x + card.width + 16, y + card.height + 26],
                                     fill=(0, 0, 0, 170))
        canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), sh.filter(ImageFilter.GaussianBlur(34))).convert("RGB"), (0, 0))
    canvas.paste(card, (x, y), card)
    return canvas


def sheet(images, captions, title, cols=4, pad=26, caption_h=54):
    cw = max(i.width for i in images)
    ch = max(i.height for i in images)
    W = pad + cols * (cw + pad)
    rows = math.ceil(len(images) / cols)
    H = pad + 74 + rows * (ch + caption_h + pad)
    canvas = Image.new("RGB", (W, H), (8, 11, 18))
    d = ImageDraw.Draw(canvas)
    d.text((pad + 6, 22), title, font=f(SERIF, 34), fill=(240, 232, 214))
    for i, (img, cap) in enumerate(zip(images, captions)):
        r, c = divmod(i, cols)
        x = pad + c * (cw + pad)
        y = 74 + r * (ch + caption_h + pad)
        canvas.paste(img, (x, y))
        d.text((x + cw / 2, y + ch + 16), cap, font=f(CJK, 24), fill=(203, 185, 143), anchor="ma")
    return canvas


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    per_template = {}
    for tpl in TEMPLATES:
        cfg = json.loads((SET / tpl / "card-config.json").read_text(encoding="utf8"))
        panels, caps = [], []
        for key, label, rx, ry, foil in STATES:
            f_use = foil
            if key == "holo":
                # 立体画框款: 大角度用暖金箔的强光扫, 接近演示视频的观感
                f_use = 0.95 if tpl == "diorama" else foil
            front = compose_front(tpl, cfg, rx, ry, f_use)
            img = present(Image.fromarray((front * 255).astype(np.uint8), "RGB"),
                          ry if key != "front" else 0)
            img.save(OUT / f"{tpl}-{key}.png")
            panels.append(img)
            caps.append(label)
        back = present(render_back(tpl, cfg), 0)
        back.save(OUT / f"{tpl}-back.png")
        panels.append(back)
        caps.append("背面设计")
        per_template[tpl] = (panels, caps)
        sheet(panels, caps, f"Birthday / {tpl.title()}").save(OUT / f"sheet-{tpl}.png")
        print("rendered:", tpl, flush=True)

    # 四套总图 4x4
    all_imgs, all_caps = [], []
    for tpl in TEMPLATES:
        p, c = per_template[tpl]
        all_imgs += p
        all_caps += [f"{tpl.title()} · {x}" for x in c]
    sheet(all_imgs, all_caps, "Birthday Collection · 4 Templates x 4 States").save(OUT / "sheet-all.png")

    cards = "\n".join(
        f'<section><h2>Birthday / {t.title()}</h2>'
        f'<a href="./sheet-{t}.png"><img src="./sheet-{t}.png" alt="{t}" /></a>'
        f'<p>' + " · ".join(f'<a href="./{t}-{k}.png">{lab}</a>'
                            for k, lab, _, _, _ in STATES) + f' · <a href="./{t}-back.png">背面</a></p></section>'
        for t in TEMPLATES)
    (OUT / "index.html").write_text(f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" />
<title>Birthday 系列 · 效果图</title>
<style>body{{margin:0;background:#070a12;color:#f0e8d6;font-family:"Segoe UI","Microsoft YaHei",sans-serif}}
header{{padding:34px 4vw 8px}}h1{{font-family:Georgia,serif;font-weight:400;margin:0;letter-spacing:2px}}
.sub{{color:#8b8474;font-size:13px;letter-spacing:2px;margin-top:8px}}
main{{padding:18px 4vw 60px}}section{{margin-bottom:38px}}
h2{{font-family:Georgia,serif;font-weight:400;color:#dec9a0;font-size:20px;letter-spacing:1px}}
img{{width:100%;border:1px solid #1c2436;border-radius:10px}}
a{{color:#cbb98f}}p{{font-size:13px}}</style></head><body>
<header><h1>Birthday Collection · 效果图</h1>
<div class="sub">同一张照片 × 四套设计 · 正面静止 / 轻微倾斜 / 大角度 Holo / 背面</div></header>
<main><section><h2>四套总图</h2><a href="./sheet-all.png"><img src="./sheet-all.png" /></a></section>
{cards}</main></body></html>""", encoding="utf8")
    print("done →", OUT)


if __name__ == "__main__":
    main()
