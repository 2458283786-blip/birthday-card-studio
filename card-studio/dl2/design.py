# -*- coding: utf-8 -*-
"""
DL2 · 设计模块(占用掩码 + 版式规划 + Editorial 渲染)
=====================================================
与旧的 birthday_system 完全隔离。三件事:
  1) occupancy(): 把"主体框"升级为**占用掩码**(肤色 + 细节能量 + 人脸), 用于真正的避让
  2) plan():      按语言生成**候选版式** → 用照片实测打分 → 择优; 全部不达标则用该语言的**兜底版式**
  3) render():    Editorial 渲染(大照片 / 大字体 / 非对称 / 大留白 / 极少装饰 / photo-driven palette)

用法: python card-studio/dl2/design.py <照片> [--lang editorial] [--age 20] [--out x.png]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import photodna  # noqa: E402

W, H = 1024, 1536
FONTS = r"C:\Windows\Fonts"
SERIF, SANS, SANS_SB = (FONTS + r"\pala.ttf", FONTS + r"\segoeui.ttf", FONTS + r"\seguisb.ttf")
CJK_SANS, CJK_SERIF = FONTS + r"\msyh.ttc", FONTS + r"\simsun.ttc"


# ---------------------------------------------------------------- 字体 / 基础
def has_cjk(t):
    return any("\u3400" <= c <= "\u9fff" for c in str(t or ""))


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype(SANS, size)


def fnt(text, size, kind="sans"):
    if has_cjk(text):
        return font(CJK_SERIF if kind == "serif" else CJK_SANS, size)
    return font({"sans": SANS, "sansb": SANS_SB, "serif": SERIF}[kind], size)


def tracked(d, xy, text, f, fill, tracking=0.0, center=False):
    text = str(text)
    ws = [d.textlength(ch, font=f) for ch in text]
    total = sum(ws) + tracking * max(0, len(text) - 1)
    x = xy[0] - total / 2 if center else xy[0]
    for ch, w in zip(text, ws):
        d.text((x, xy[1]), ch, font=f, fill=fill)
        x += w + tracking
    return total


def hexc(rgb, a=255):
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]), a)


def mix(c1, c2, t):
    return tuple(int(round(c1[i] * (1 - t) + c2[i] * t)) for i in range(3))


def luminance(rgb):
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


# ---------------------------------------------------------------- 1) 占用掩码
def occupancy(im, dna):
    """返回 0..1 的占用度图(1=被主体/人脸/高细节占据, 不适合放字)。"""
    bgr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    occ = np.zeros((h, w), np.float32)

    # a) 人脸(强占用)
    for (x, y, fw, fh) in dna["subject"]["faces"]:
        pad = int(max(fw, fh) * 0.35)
        cv2.rectangle(occ, (max(0, x - pad), max(0, y - pad)),
                      (min(w, x + fw + pad), min(h, y + fh + pad)), 1.0, -1)
    # b) 肤色(人像的肩颈/手臂)
    hsv = cv2.cvtColor(cv2.GaussianBlur(bgr, (7, 7), 0), cv2.COLOR_BGR2HSV)
    skin = (cv2.inRange(hsv, np.array([0, 40, 70]), np.array([25, 190, 255])) |
            cv2.inRange(hsv, np.array([160, 40, 70]), np.array([180, 190, 255])))
    skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    occ = np.maximum(occ, cv2.GaussianBlur(skin.astype(np.float32) / 255.0, (0, 0), 12) * 0.9)
    # c) 细节能量(纹理密集处也不适合放字)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    e = np.hypot(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    e = cv2.GaussianBlur(e, (0, 0), 14)
    e = np.clip(e / (np.quantile(e, 0.93) + 1e-6), 0, 1)
    occ = np.maximum(occ, e * 0.75)
    return np.clip(occ, 0, 1)


def occ_of(occ, box):
    x, y, w, h = box
    patch = occ[max(0, y):y + h, max(0, x):x + w]
    return float(patch.mean()) if patch.size else 1.0


def clean_bands(occ, bands=(0.0, 0.25, 0.5, 0.75), height=0.30):
    """按横向带评估"可压字"的干净程度。返回**归一化**坐标(0..1), 由渲染端映射到卡面。"""
    h, w = occ.shape
    out = []
    for b in bands:
        y0, y1 = int(h * b), min(h, int(h * (b + height)))
        seg = occ[y0:y1]
        out.append({"y0": round(b, 3), "y1": round(min(1.0, b + height), 3),
                    "occupancy": round(float(seg.mean()), 3),
                    "bottom_half": round(float(seg[int(seg.shape[0] / 2):].mean()), 3)})
    out.sort(key=lambda r: r["occupancy"])
    return out


# ---------------------------------------------------------------- 2) 版式规划
def palette(dna):
    dom = dna["color"]["dominant"]
    bright = max(dom, key=lambda d: luminance(d["rgb"]))
    dark = min(dom, key=lambda d: luminance(d["rgb"]))
    vivid = max(dom, key=lambda d: (max(d["rgb"]) - min(d["rgb"])))
    paper = mix(bright["rgb"], (250, 248, 243), 0.80)
    ink = mix(dark["rgb"], (26, 24, 22), 0.72)
    accent = mix(vivid["rgb"], (230, 120, 90), 0.25)
    if luminance(paper) - luminance(ink) < 0.45:          # 明暗对比不足时拉开
        paper = mix(paper, (252, 250, 246), 0.5)
        ink = mix(ink, (18, 17, 16), 0.4)
    return {"paper": paper, "ink": ink, "accent": accent,
            "photo_dark": dark["rgb"], "photo_bright": bright["rgb"]}


def subject_crop_box(im, dna, target_ratio, bias=0.42):
    """按主体位置做"防切脸"裁剪: 目标宽高比 target_ratio = w/h。"""
    iw, ih = im.size
    cx, cy = dna["subject"]["center"]
    if iw / ih > target_ratio:                 # 图更宽 → 裁两侧
        nw, nh = int(ih * target_ratio), ih
    else:                                      # 图更高 → 裁上下
        nw, nh = iw, int(iw / target_ratio)
    x = int(np.clip(cx * iw - nw / 2, 0, iw - nw))
    y = int(np.clip(cy * ih - nh * bias, 0, ih - nh))
    return (x, y, x + nw, y + nh)


def _faces_kept(im, dna, crop, margin=0.04):
    """裁剪后是否切到脸(防切脸硬约束)。"""
    x0, y0, x1, y1 = crop
    cw, ch = x1 - x0, y1 - y0
    if not dna["subject"]["faces"]:
        return True
    for (fx, fy, fw, fh) in dna["subject"]["faces"]:
        if fx < x0 - cw * margin or fy < y0 - ch * margin or \
           fx + fw > x1 + cw * margin or fy + fh > y1 + ch * margin:
            return False
    return True


def plan_editorial(im, dna, occ, info):
    """三套候选 + 打分; 按照片特征分流(近景→压字, 常规→上照片下文字), 都不达标可兜底。"""
    sub = dna["subject"]
    cx, cy = sub["center"]
    ratio = float(occ.mean())          # 用占用掩码的实际占比, 比主体框可靠
    iw, ih = dna["size"]
    bands = clean_bands(occ)
    best_band = bands[0]

    # 各版式的照片裁剪(用于防切脸硬约束)
    c1 = subject_crop_box(im, dna, W / (H * 0.62))
    c2 = subject_crop_box(im, dna, (W * 0.56) / H)
    c3 = subject_crop_box(im, dna, W / H)

    # E1 上照片下文字: Editorial 的默认性格; 近景(占用高)与主体偏下时不利
    e1 = 0.80 - 0.60 * max(0.0, ratio - 0.30) - 0.25 * max(0.0, cy - 0.62)
    if not _faces_kept(im, dna, c1):
        e1 -= 0.45
    # E2 左照片右文字: 需要主体明显偏离中心, 且竖构图才不被裁得难看
    e2 = 0.52 + abs(cx - 0.5) * 0.9 + (0.08 if ih / iw > 1.15 else -0.12)
    if not _faces_kept(im, dna, c2):
        e2 -= 0.45
    # E3 全幅压字: 近景/主体占满时的解法; 依赖 scrim 与干净带
    e3 = 0.46 + 0.70 * max(0.0, ratio - 0.28) + 0.22 * (1 - best_band["occupancy"])
    if best_band["occupancy"] > 0.32:
        e3 -= 0.30
    if not _faces_kept(im, dna, c3):
        e3 -= 0.6

    cands = [
        {"id": "E1", "name": "bleed-top", "photo": [0, 0, W, int(H * 0.62)],
         "text_zone": [92, int(H * 0.62) + 60, W - 184, int(H * 0.30)],
         "align": "left", "score": round(min(1.0, max(0.0, e1)), 3)},
        {"id": "E2", "name": "side-column", "photo": [0, 0, int(W * 0.56), H],
         "text_zone": [int(W * 0.60), int(H * 0.56), int(W * 0.34), int(H * 0.38)],
         "align": "left", "score": round(min(1.0, max(0.0, e2)), 3)},
        {"id": "E3", "name": "overlay-scrim", "photo": [0, 0, W, H],
         "band": best_band, "align": "left", "score": round(min(1.0, max(0.0, e3)), 3)},
    ]
    cands.sort(key=lambda c: -c["score"])
    chosen = dict(cands[0])
    if chosen["score"] < 0.40:                 # 兜底: 退回最保守的上下分区
        fb = next(c for c in cands if c["id"] == "E1")
        chosen = dict(fb, fallback=True)
    chosen["all_scores"] = {c["id"]: c["score"] for c in cands}
    chosen["lang"] = "editorial"
    chosen["palette"] = palette(dna)
    chosen["hero"] = str(info.get("age") or info.get("title") or info.get("year") or "").strip()
    chosen["meta"] = [str(info.get("technique") or "").strip(), str(info.get("edition") or "").strip()]
    chosen["name"] = str(info.get("name") or "").strip()
    return chosen


# ---------------------------------------------------------------- 3) 渲染
def _paper(w=W, h=H, color=(247, 245, 240), grain=3.0, seed=11):
    rng = np.random.default_rng(seed)
    arr = np.zeros((h, w, 3), np.float32) + np.array(color, np.float32)
    arr += rng.normal(0, grain, arr.shape)
    # 纸纤维
    fib = Image.new("L", (w, h), 0)
    fd = ImageDraw.Draw(fib)
    for _ in range(260):
        y = int(rng.integers(0, h)); x = int(rng.integers(0, w))
        fd.line([(x, y), (x + int(rng.integers(24, 160)), y)], fill=int(rng.integers(5, 14)))
    arr += (np.asarray(fib.filter(ImageFilter.GaussianBlur(0.6))).astype(np.float32)[..., None] - 3.0)
    # 低频云斑
    low = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("L")
    low = low.resize((max(2, w // 26), max(2, h // 26)), Image.Resampling.BILINEAR)
    low = low.resize((w, h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(7))
    lo = np.asarray(low).astype(np.float32) - float(np.asarray(low).mean())
    arr += lo[..., None] * 0.05
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def _photo_extend(photo, edge_col, into, direction="down", length=150):
    """Photo Extension: 用照片边缘色把照片"化"进纸面, 消除矩形边界感。"""
    w = photo.width
    strip = Image.new("RGBA", (w, length), hexc(edge_col, 255))
    arr = np.asarray(strip).astype(np.float32)
    t = np.linspace(0, 1, length)[:, None]
    target = np.array(into, np.float32)
    arr[..., :3] = arr[..., :3] * (1 - t[..., None]) + target * t[..., None]
    arr[..., 3] = 255 * (1 - t)
    grad = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    grad = grad.filter(ImageFilter.GaussianBlur(6))
    return grad


def render_editorial(photo, dna, occ, spec, out_path=None):
    pal = spec["palette"]
    canvas = _paper(color=pal["paper"])
    d = ImageDraw.Draw(canvas, "RGBA")
    ink = hexc(pal["ink"])
    accent = hexc(pal["accent"])
    px, py, pw, ph = spec["photo"]

    # ---- 照片: cover 裁剪 + 防切脸 ----
    crop = subject_crop_box(photo, dna, pw / ph)
    body = photo.crop(crop).resize((pw, ph), Image.Resampling.LANCZOS)
    # satin 质感: 轻微对比 + 极淡暗角
    a = np.asarray(body).astype(np.float32) / 255.0
    a = np.clip((a - 0.5) * 1.04 + 0.5, 0, 1)
    body = Image.fromarray((a * 255).astype(np.uint8), "RGB")
    canvas.alpha_composite(body.convert("RGBA"), (px, py))

    # ---- Photo Extension: 照片边缘延展 ----
    if spec["id"] == "E1":
        edge = np.asarray(body.convert("RGB"))[-1].mean(0)
        canvas.alpha_composite(_photo_extend(body, edge, pal["paper"], length=170), (px, py + ph - 4))
    elif spec["id"] == "E2":
        edge = np.asarray(body.convert("RGB"))[:, -1].mean(0)
        canvas.alpha_composite(_photo_extend(body.transpose(Image.Transpose.ROTATE_270),
                                             edge, pal["paper"], length=150).transpose(Image.Transpose.ROTATE_90),
                               (px + pw - 4, py))

    # ---- E3: scrim 与文字必须同处一区, 并按该区实测亮度决定 scrim/字色 ----
    band_y0 = band_y1 = None
    if spec["id"] == "E3":
        band = spec["band"]
        y0, y1 = int(band["y0"] * H), int(band["y1"] * H)      # 归一化 → 卡面坐标
        seg = np.asarray(body.convert("L"))[y0:y1].astype(np.float32) / 255.0
        band_lum = float(seg.mean())
        ycenter = int((y0 + y1) / 2)
        # 字幕板: 让文字落在一块**均匀**的底上(明暗混杂的近景也能保证可读)
        light = band_lum <= 0.52
        plate_col = pal["paper"] if light else pal["photo_dark"]
        ink = hexc(pal["ink"]) if light else hexc(mix(pal["paper"], (255, 255, 255), 0.6))
        top = max(0, ycenter - 178)
        bot = min(H, ycenter + 132)
        fade = 52
        plate = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(plate)
        for yy in range(top, bot):
            if yy < top + fade:
                a = int(236 * (yy - top) / fade)
            elif yy > bot - fade:
                a = int(236 * (bot - yy) / fade)
            else:
                a = 236
            pd.line([(0, yy), (W, yy)], fill=hexc(plate_col, a))
        canvas.alpha_composite(plate.filter(ImageFilter.GaussianBlur(9)))
        band_y0, band_y1 = top, bot
        ink = ink

    # ---- 文字: 大字体 / 强层级 / 左对齐 ----
    hero = spec["hero"]
    if spec["id"] == "E3":
        tx = 92
        base_y = int((band_y0 + band_y1) / 2) + 36
        rule_y = base_y - 96
        meta_y = base_y - 132
        name_y = base_y + 54
    else:                                                        # E1/E2: 文字块靠下, 与照片形成留白
        tx = spec["text_zone"][0]
        base_y = H - 236
        rule_y = base_y - 92
        meta_y = base_y - 128
        name_y = base_y + 52
    if hero:
        hf = fnt(hero, 188, "serif") if not has_cjk(hero) else fnt(hero, 132, "serif")
        d.text((tx + 3, base_y + 3), hero, font=hf, fill=hexc(pal["photo_dark"], 70), anchor="ls")
        d.text((tx, base_y), hero, font=hf, fill=ink, anchor="ls")
    # 细分割线(来自照片强调色, 唯一装饰)
    d.line([(tx, rule_y), (tx + 268, rule_y)], fill=hexc(mix(pal["accent"], pal["paper"], 0.15), 200), width=2)
    if spec["name"]:
        tracked(d, (tx, name_y), spec["name"].upper(), fnt(spec["name"], 20, "sansb"), hexc(pal["ink"], 235), 4.5)
    # 元信息(右对齐到同一页边)
    mx = W - 92
    for i, m in enumerate([m for m in spec["meta"] if m]):
        f = fnt(m, 27 if i == 0 else 21, "sans")
        w = d.textlength(m, font=f) + (2.2 if i == 0 else 1.6) * max(0, len(m) - 1)
        col = ink if spec["id"] == "E3" else hexc(pal["ink"], 232 if i == 0 else 190)
        tracked(d, (mx - w, meta_y + i * 40), m, f, col if spec["id"] == "E3" else col,
                2.2 if i == 0 else 1.6)
    # 极轻卡边(不是金框)
    d.rectangle([26, 26, W - 27, H - 27], outline=hexc(pal["ink"], 16), width=1)

    # ---- 纸张颗粒 ----
    arr = np.asarray(canvas.convert("RGB")).astype(np.float32)
    arr += np.random.default_rng(7).normal(0, 2.6, arr.shape)
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    if out_path:
        out.save(out_path)
    return out


# ---------------------------------------------------------------- CLI
def build(photo_path, info, lang="editorial", out_dir="dl2/out"):
    path = Path(photo_path)
    dna, _ = photodna.analyze(path)
    im = photodna.orient.load_upright(path)
    deg = dna["orientation"]["applied_deg"]
    if deg:
        im = im.rotate(-deg, expand=True)
    occ = occupancy(im, dna)
    spec = plan_editorial(im, dna, occ, info)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / f"{path.stem}-{lang}.png"
    render_editorial(im, dna, occ, spec, out)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / f"{path.stem}-{lang}.json").write_text(
        json.dumps({k: spec[k] for k in spec if k != "palette"} |
                   {"palette": {k: list(v) for k, v in spec["palette"].items()}},
                   ensure_ascii=False, indent=2), encoding="utf8")
    return out, spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("--lang", default="editorial")
    ap.add_argument("--age", default="20")
    ap.add_argument("--date", default="2026.09.11")
    ap.add_argument("--edition", default="CARD #0001")
    ap.add_argument("--name", default="")
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    info = {"age": a.age, "technique": a.date, "edition": a.edition, "name": a.name, "title": a.title}
    out, spec = build(a.photo, info, a.lang)
    print(f"{Path(a.photo).name}: 版式 {spec['id']}({spec['name']}) score={spec['score']} "
          f"候选={spec['all_scores']}{' [兜底]' if spec.get('fallback') else ''} → {out}")


if __name__ == "__main__":
    main()
