# -*- coding: utf-8 -*-
"""
DL2 · PhotoDNA(纯程序化, 零 AI 依赖)
====================================
把一张照片变成可被设计引擎使用的结构化数据:
  方向 → 色彩 → 明暗 → 主体 → 负空间(可排版区) → 地平线 → 纹理 → 情绪代理
并把可选的 AI 语义判读合并进来, 且**逐条校验**(AI 说"这里能放字", 程序必须验过才采纳)。

输出: <照片目录>/_photodna.json   (键 = 文件名)
用法: python card-studio/dl2/photodna.py <照片或目录> [--force]
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import orient  # noqa: E402

EXTS = {".jpg", ".jpeg", ".png", ".webp"}
CACHE = "_photodna.json"
_GRID = (3, 4)          # 3 列 × 4 行 = 12 个候选版位


# ---------------------------------------------------------------- 基础
def _bgr(im):
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def _dominant(bgr, k=5):
    small = cv2.resize(bgr, (160, 160), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _ret, labels, centers = cv2.kmeans(lab, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    rgb = cv2.cvtColor(centers.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_LAB2RGB).reshape(-1, 3)
    w = np.bincount(labels.flatten(), minlength=k).astype(np.float32) / labels.size
    order = np.argsort(-w)
    return [{"rgb": [int(v) for v in rgb[i]], "weight": round(float(w[i]), 3)} for i in order]


def _edge_colors(im, band=0.04):
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    bh, bw = max(2, int(h * band)), max(2, int(w * band))
    strips = {"top": a[:bh], "bottom": a[-bh:], "left": a[:, :bw], "right": a[:, -bw:]}
    out = {}
    for name, s in strips.items():
        med = np.median(s.reshape(-1, 3), axis=0)
        out[name] = [int(v) for v in med]
    return out


def _tone(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    g = gray.astype(np.float32) / 255.0
    lo, mid, hi = np.percentile(g, 15), np.percentile(g, 55), np.percentile(g, 92)
    def mean_rgb(mask):
        px = bgr[mask]
        if px.size == 0:
            return [0, 0, 0]
        return [int(v) for v in cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_BGR2RGB).reshape(-1, 3).mean(0)]
    return {
        "brightness": round(float(g.mean()), 3),
        "contrast": round(float(g.std()), 3),
        "clipping": {"lo": round(float((g < 0.03).mean()), 4), "hi": round(float((g > 0.97).mean()), 4)},
        "shadow": mean_rgb(g <= lo), "midtone": mean_rgb((g > lo) & (g < hi)), "highlight": mean_rgb(g >= hi),
    }


def _temp_sat(bgr):
    b, g, r = [bgr[..., i].astype(np.float32) for i in range(3)]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return {
        "warmth": round(float((r.mean() - b.mean()) / 255.0), 3),      # >0 偏暖, <0 偏冷
        "saturation": round(float(hsv[..., 1].mean() / 255.0), 3),
        "value": round(float(hsv[..., 2].mean() / 255.0), 3),
    }


# ---------------------------------------------------------------- 主体
def _faces(bgr):
    gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    h, w = gray.shape[:2]
    ms = (int(min(h, w) * 0.05),) * 2
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    prof = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    got = list(casc.detectMultiScale(gray, 1.12, 5, minSize=ms))
    got += list(prof.detectMultiScale(gray, 1.12, 5, minSize=ms))
    return [[int(v) for v in f] for f in got]      # x, y, w, h


def _energy_box(bgr, quantile=0.55):
    """无脸时的兜底: 用细节能量(梯度)重心与范围估计主体位置。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    e = np.hypot(gx, gy)
    e = cv2.GaussianBlur(e, (0, 0), 9)
    thr = np.quantile(e, quantile)
    ys, xs = np.where(e >= thr)
    if len(xs) < 50:
        return None, [0.5, 0.5]
    box = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min()), int(ys.max() - ys.min())]
    cx, cy = float(xs.mean() / bgr.shape[1]), float(ys.mean() / bgr.shape[0])
    return box, [round(cx, 3), round(cy, 3)]


def _subject(bgr, faces):
    h, w = bgr.shape[:2]
    if faces:
        x0 = min(f[0] for f in faces); y0 = min(f[1] for f in faces)
        x1 = max(f[0] + f[2] for f in faces); y1 = max(f[1] + f[3] for f in faces)
        fw, fh = x1 - x0, y1 - y0
        # 近景自拍时人脸本身就很大, 扩张必须收敛, 否则主体框会吃掉整张卡
        ex, ey_up, ey_dn = fw * 0.45, fh * 0.60, fh * 1.60
        if fh / float(h) > 0.22:                     # 脸占比大 → 缩小扩张
            ex, ey_up, ey_dn = fw * 0.25, fh * 0.30, fh * 0.70
        box = [max(0, int(x0 - ex)), max(0, int(y0 - ey_up)),
               min(w, int(x1 + ex)), min(h, int(y1 + ey_dn))]
        if (box[2] - box[0]) * (box[3] - box[1]) > 0.68 * w * h:   # 面积上限, 超了就退回人脸并集
            box = [max(0, x0), max(0, y0), min(w, x1), min(h, y1)]
        src = "face"
    else:
        b, c = _energy_box(bgr)
        box, src = (b, "energy") if b else (None, "none")
    if not box:
        return {"box": None, "source": "none", "area_ratio": 0.0, "faces": [], "center": [0.5, 0.5]}
    x0, y0, x1, y1 = box
    return {
        "box": [x0, y0, x1 - x0, y1 - y0],
        "source": src,
        "area_ratio": round(((x1 - x0) * (y1 - y0)) / float(w * h), 3),
        "faces": faces,
        "center": [round((x0 + x1) / 2 / w, 3), round((y0 + y1) / 2 / h, 3)],
    }


# ---------------------------------------------------------------- 负空间(可排版区)
def _clean_regions(bgr, subject):
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160).astype(np.float32) / 255.0
    sub = subject.get("box")
    faces = subject.get("faces") or []
    cols, rows = _GRID
    out = []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = int(w * c / cols), int(h * r / rows)
            x1, y1 = int(w * (c + 1) / cols), int(h * (r + 1) / rows)
            cell_e = edges[y0:y1, x0:x1].mean()
            cell_g = gray[y0:y1, x0:x1].astype(np.float32) / 255.0
            contrast = float(cell_g.std())
            bright = float(cell_g.mean())
            # 与主体/人脸的重叠
            def ov(b):
                if not b:
                    return 0.0
                bx, by, bw, bh = b
                ix = max(0, min(x1, bx + bw) - max(x0, bx)); iy = max(0, min(y1, by + bh) - max(y0, by))
                return (ix * iy) / float((x1 - x0) * (y1 - y0))
            sub_ov = ov(sub)
            face_ov = max([ov(f) for f in faces], default=0.0)
            # 打分: 边缘少 + 明暗均匀 + 不压主体/人脸
            score = (1 - min(1.0, cell_e / 0.18)) * 0.45 + (1 - min(1.0, contrast / 0.22)) * 0.25 \
                + (1 - sub_ov) * 0.22 + (1 - face_ov) * 0.08
            z = "top" if r == 0 else "bottom" if r == rows - 1 else "middle"
            zx = "left" if c == 0 else "right" if c == cols - 1 else "center"
            out.append({
                "name": f"{zx}-{z}", "box": [x0, y0, x1 - x0, y1 - y0],
                "score": round(float(score), 3),
                "edge_density": round(float(cell_e), 4),
                "local_contrast": round(contrast, 4),
                "brightness": round(bright, 3),
                "text_color": "dark" if bright > 0.6 else "light",
                "subject_overlap": round(sub_ov, 3), "face_overlap": round(face_ov, 3),
            })
    out.sort(key=lambda x: -x["score"])
    return out


def _horizon(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 120, minLineLength=int(bgr.shape[1] * 0.28),
                            maxLineGap=24)
    if lines is None:
        return {"y": None, "conf": 0.0}
    ys = []
    for x1, y1, x2, y2 in lines[:, 0]:
        ang = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if ang < 8 or ang > 172:
            ys.append((y1 + y2) / 2 / bgr.shape[0])
    if not ys:
        return {"y": None, "conf": 0.0}
    return {"y": round(float(np.median(ys)), 3), "conf": round(min(1.0, len(ys) / 12.0), 2)}


def _texture(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160).astype(np.float32) / 255.0
    lap = cv2.Laplacian(gray, cv2.CV_64F).var()
    # 平坦区的高频能量 ≈ 颗粒感
    flat = cv2.GaussianBlur(gray, (0, 0), 3).astype(np.float32)
    hp = gray.astype(np.float32) - flat
    mask = cv2.GaussianBlur(cv2.Canny(gray, 40, 120), (0, 0), 5) < 10
    grain = float(hp[mask].std()) if mask.sum() > 200 else float(hp.std())
    return {"edge_density": round(float(edges.mean()), 4), "sharpness": round(float(lap), 1),
            "grain_sigma": round(grain, 2)}


def _mood(temp_sat, tone):
    warm = temp_sat["warmth"]
    key_t = "warm" if warm > 0.03 else "cool" if warm < -0.03 else "neutral"
    key_c = "highcontrast" if tone["contrast"] > 0.22 else "lowcontrast" if tone["contrast"] < 0.14 else "midcontrast"
    key_s = "vivid" if temp_sat["saturation"] > 0.42 else "muted" if temp_sat["saturation"] < 0.22 else "normal"
    return {"key": f"{key_t}_{key_c}_{key_s}", "heur": True}


# ---------------------------------------------------------------- AI 校验(QAGate 种子)
def _validate_ai(ai, regions):
    """AI 说"某区域干净", 程序按边缘密度/人脸重叠实测校验, 不通过就不采纳。"""
    if not ai:
        return None
    verdicts = []
    for area in ai.get("clean_areas", []) or []:
        name, score = area.get("name", ""), area.get("score", 0)
        # AI 的区域名(top/bottom/left/right/center)映射到我们的格子
        cand = [r for r in regions if name in r["name"]] or regions
        if not cand:
            continue
        best = cand[0]
        ok = (best["edge_density"] <= 0.10) and (best["face_overlap"] == 0)
        verdicts.append({
            "ai_name": name, "ai_score": score,
            "matched_cell": best["name"], "measured_score": best["score"],
            "edge_density": best["edge_density"], "face_overlap": best["face_overlap"],
            "accepted": bool(ok),
            "reason": "通过(低纹理且不压脸)" if ok else
                      ("边缘过密" if best["edge_density"] > 0.10 else "与人脸重叠"),
        })
    return verdicts


# ---------------------------------------------------------------- 主流程
def analyze(path, force=False, cache=None):
    path = Path(path)
    folder = path.parent
    cache = cache if cache is not None else _load(folder)
    if not force and path.name in cache:
        return cache[path.name], True

    deg, conf, detail = orient.detect(path)
    im = orient.load_upright(path)
    if deg:
        im = im.rotate(-deg, expand=True)
    bgr = _bgr(im)

    faces = _faces(bgr)
    subject = _subject(bgr, faces)
    regions = _clean_regions(bgr, subject)
    temp_sat, tone = _temp_sat(bgr), _tone(bgr)
    ai = (_load(folder, "_ai-analysis.json").get(path.name) or {}).get("analysis")
    if ai and ai.get("rotation_fix") in ("rotate90cw", "rotate90ccw", "rotate180") and not deg:
        detail += f" | AI 提示 {ai['rotation_fix']}(程序未确认, 未采用)"

    rec = {
        "file": path.name,
        "size": list(im.size),
        "orientation": {"applied_deg": deg, "confidence": conf, "detail": detail},
        "color": {"dominant": _dominant(bgr), "edges": _edge_colors(im), **temp_sat},
        "tone": tone,
        "subject": subject,
        "space": {"grid": list(_GRID), "regions": regions, "horizon": _horizon(bgr)},
        "texture": _texture(bgr),
        "mood": _mood(temp_sat, tone),
        "ai": ai,
        "ai_validation": _validate_ai(ai, regions),
    }
    cache[path.name] = rec
    (folder / CACHE).write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf8")
    return rec, False


def _load(folder, name=CACHE):
    p = Path(folder) / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf8"))
        except Exception:
            pass
    return {}


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "dl2/photos")
    force = "--force" in sys.argv
    files = sorted([p for p in target.glob("*") if p.suffix.lower() in EXTS]) if target.is_dir() else [target]
    for f in files:
        rec, cached = analyze(f, force)
        s, c = rec["subject"], rec["color"]
        top = rec["space"]["regions"][:3]
        print(f"\n=== {rec['file']} {'(缓存)' if cached else ''} ===")
        print(f"  方向: {rec['orientation']['applied_deg']}° (conf {rec['orientation']['confidence']}) {rec['orientation']['detail']}")
        print(f"  主色: " + ", ".join(f"#{c['dominant'][i]['rgb'][0]:02x}{c['dominant'][i]['rgb'][1]:02x}{c['dominant'][i]['rgb'][2]:02x}({c['dominant'][i]['weight']})" for i in range(min(3, len(c['dominant'])))))
        print(f"  色调: 亮度{rec['tone']['brightness']} 对比{rec['tone']['contrast']} 暖度{c['warmth']} 饱和{c['saturation']} | {rec['mood']['key']}")
        print(f"  主体: {s['source']} box={s['box']} 占卡面{s['area_ratio']} 人脸{len(s['faces'])}")
        print(f"  地平线: {rec['space']['horizon']} | 纹理: {rec['texture']}")
        print("  可排版区(前3): " + " | ".join(f"{r['name']} {r['score']}(边{r['edge_density']},脸叠{r['face_overlap']},{r['text_color']})" for r in top))
        if rec["ai_validation"]:
            acc = [v for v in rec["ai_validation"] if v["accepted"]]
            print(f"  AI 建议校验: {len(acc)}/{len(rec['ai_validation'])} 通过")
            for v in rec["ai_validation"]:
                print(f"     {'✓' if v['accepted'] else '✗'} AI:{v['ai_name']}({v['ai_score']}) → {v['matched_cell']} {v['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
