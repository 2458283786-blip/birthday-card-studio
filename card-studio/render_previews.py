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
HAND = FONTS + r"\segoesc.ttf"     # 背面手写签名(Segoe Script 连笔)
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



def safe_open(path, tries=5, wait=0.3):
    """安全读图: 碰到写了一半的 PNG 就等一会重试(与 make_static_card 一致)。"""
    import time
    last = None
    for i in range(tries):
        try:
            im = Image.open(path)
            im.load()
            return im
        except Exception as e:
            last = e
            time.sleep(wait * (i + 1))
    raise RuntimeError(f"读图失败: {path} — {last}")

def f(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype(SANS, size)


def has_cjk(text):
    return any("\u3400" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef" for ch in str(text or ""))


def ftext(text, size, kind="sans"):
    """含中文自动切到雅黑/宋体, 避免空框。"""
    if has_cjk(text):
        path = {"sans": FONTS + r"\msyh.ttc", "sansb": FONTS + r"\msyhbd.ttc",
                "serif": FONTS + r"\simsun.ttc"}[kind]
        return f(path, size)
    return f({"sans": SANS, "sansb": SANS_SB, "serif": SERIF}[kind], size)


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
    is_gloss = 1.0 if mtype > 2.5 else 0.0
    is_foil = 1.0 if (mtype > 1.5 and mtype <= 2.5) else 0.0
    gain = 1.0 + is_gloss * 1.6 + is_foil * 0.5
    bnd = band ** 1.45 if is_gloss else band
    col = col * (1.0 - amount * 0.11 * (1.0 - f) * (0.2 + bnd[..., None] * 0.8))
    col = col + f * (amount * bnd * gain * boost * (0.028 + 0.06 * (1.0 - lum)))[..., None]
    col = col + f * (amount * is_gloss * 0.045 * (1.0 - lum))[..., None]
    spec = np.clip(bnd, 0, 1) ** 1.15
    graze = float(np.clip((np.hypot(view[0], view[1]) - 0.12) * 3.2, 0.0, 1.0))
    col = col + (is_gloss * (0.09 + 0.52 * graze ** 1.5) * amount)
    col = col + f * (is_foil * (0.03 + 0.20 * graze ** 1.4) * amount)
    col = col + spec[..., None] * (is_gloss * amount * 0.22)
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
    """背面 = 统一 Card Identity(V2 规范 §6)。
    近黑底 · 单细内框 · 居中: CARD# / 日期 / 手写签名 / 双栏归属 / 二维码
    只画有数据的字段; 缺字段则整块不出现, 不留空白占位。
    """
    S = BACK_STYLE.get(cfg.get("backStyle", tpl), next(iter(BACK_STYLE.values())))
    w, h = 1024, 1536
    gold = tuple(S.get("gold", (222, 201, 160)))
    ink_c = tuple(S.get("ink", (236, 232, 224)))
    base_rgb = tuple(S.get("bg2", (12, 13, 17)))

    # —— 底: 近黑 + 极轻的模板色偏移 + 柔和暗角 + 细颗粒(印刷感) ——
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    dark = tuple(max(6, min(34, int(c * 0.16 + 8))) for c in base_rgb)
    for y in range(h):
        t = y / h
        f_ = 1.0 - 0.22 * abs(t - 0.45) * 2
        d.line([(0, y), (w, y)], fill=tuple(int(c * f_) for c in dark) + (255,))
    try:
        import numpy as np
        arr = np.asarray(im.convert("RGB"), dtype=np.float32)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
        arr *= np.clip(1.06 - 0.30 * np.clip(r - 0.35, 0, 2) ** 1.5, 0.55, 1.06)[..., None]
        rng = np.random.default_rng(7)
        arr += rng.normal(0, 1.6, arr.shape).astype(np.float32)
        im = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGB").convert("RGBA")
        d = ImageDraw.Draw(im)
    except Exception:
        pass

    # —— 单细内框 + 四角短线(克制) ——
    m = 34
    d.rectangle([m, m, w - 1 - m, h - 1 - m], outline=gold + (58,), width=1)
    for (x, y, sx, sy) in [(m, m, 1, 1), (w - 1 - m, m, -1, 1),
                           (m, h - 1 - m, 1, -1), (w - 1 - m, h - 1 - m, -1, -1)]:
        d.line([(x, y), (x + sx * 34, y)], fill=gold + (96,), width=1)
        d.line([(x, y), (x, y + sy * 34)], fill=gold + (96,), width=1)

    # —— 工具: 自适应字号 + 超宽截断 ——
    def fit(text, kind, size, max_w, tracking=0.0, min_size=12):
        t = str(text)
        sz = size
        while sz > min_size:
            fnt = ftext(t, sz, kind)
            if d.textlength(t, font=fnt) + tracking * max(0, len(t) - 1) <= max_w:
                return fnt, t
            sz -= 1
        fnt = ftext(t, min_size, kind)
        while len(t) > 3 and d.textlength(t + "\u2026", font=fnt) + tracking * len(t) > max_w:
            t = t[:-1]
        return fnt, (t + "\u2026" if t != str(text) else t)

    # —— 上半: CARD # + 细线 + 日期(居中) ——
    y = int(h * 0.175)
    if cfg.get("edition"):
        fnt, t = fit(cfg["edition"], "serif", 38, 620, 3.4)
        tracked(d, (w / 2, y), t, fnt, gold + (246,), 3.4, True)
    y += 46
    d.line([(w / 2 - 92, y), (w / 2 + 92, y)], fill=gold + (70,), width=1)
    if cfg.get("technique"):
        fnt, t = fit(cfg["technique"], "sans", 21, 560, 2.6)
        tracked(d, (w / 2, y + 34), t, fnt, ink_c + (196,), 2.6, True)

    # —— 中部: 手写签名(系列名/固定语) ——
    script = str(cfg.get("collection") or "Digital Collectible Card").strip()
    if script.isupper():
        script = " ".join(w.capitalize() for w in script.split())
    if script:
        hf = HAND if Path(HAND).exists() else SERIF
        sz = 74 if len(script) <= 24 else 58
        fnt = f(hf, sz)
        while d.textlength(script, font=fnt) > 660 and sz > 30:
            sz -= 2
            fnt = f(hf, sz)
        d.text((w / 2 + 2, h * 0.50 + 2), script, font=fnt, fill=(0, 0, 0, 130), anchor="mm")
        d.text((w / 2, h * 0.50), script, font=fnt, fill=gold + (222,), anchor="mm")

    # —— 细线 + 左右双栏归属 ——
    d.line([(w / 2 - 150, h * 0.625), (w / 2 + 150, h * 0.625)], fill=gold + (52,), width=1)
    created = str(cfg.get("createdBy") or "").strip().lstrip("@")
    owned = str(cfg.get("ownedBy") or "").strip().lstrip("@")
    if created or owned:
        col_w = 340
        if created:
            fnt, t = fit("Created by @" + created, "sans", 16, col_w, 2.2)
            tracked(d, (w * 0.28, h * 0.665), t, fnt, ink_c + (176,), 2.2, True)
        if owned:
            fnt, t = fit("Owned by @" + owned, "sans", 16, col_w, 2.2)
            tracked(d, (w * 0.72, h * 0.665), t, fnt, ink_c + (176,), 2.2, True)

    # —— 底部: 居中二维码(可选) ——
    qr = cfg.get("qr") or {}
    if qr.get("enabled") and qr.get("matrix"):
        mat = qr["matrix"]
        n = len(mat)
        side, pad = 164, 12
        x0, y0 = int(w / 2 - side / 2), int(h * 0.735)
        d.rounded_rectangle([x0 - pad, y0 - pad, x0 + side + pad, y0 + side + pad], radius=10,
                            fill=(255, 255, 255, 238))
        cell = side / float(n)
        for r_i, row in enumerate(mat):
            for c_i, v in enumerate(row):
                if v:
                    d.rectangle([x0 + c_i * cell, y0 + r_i * cell,
                                 x0 + (c_i + 1) * cell, y0 + (r_i + 1) * cell],
                                fill=(12, 12, 14, 255))
    return im
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
