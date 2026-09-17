# -*- coding: utf-8 -*-
"""
小程序渲染 vs 工作台参照渲染 —— 到底差多少
==========================================
参照: card-studio/render_previews.py 的 compose_front()
      —— 项目自带的离线渲染器, 用的是**与网页版 shader 同一套公式**
我的: 小程序里实际的做法(holo-card 组件)
      —— 分层 2D 视差 + 整卡材质覆盖层(CSS 的 mix-blend-mode 近似)

目的: 不用开微信开发者工具, 也能看见"小程序渲染出来像不像工作台的卡",
      并把差异量化(不是靠感觉)。

用法:
  python tools/compare_render.py                 # 默认 CARD-0001
  python tools/compare_render.py CARD-0002
产出:
  mockups/render-compare.png                     # 三档倾角的对比图(参照 / 小程序 / 差异)
"""
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "exports"
OUT = ROOT / "mockups"

sys.path.insert(0, str(ROOT / "card-studio"))
import render_previews as R          # noqa: E402  项目的参照渲染器


# ---------------------------------------------------------------- 参照

def prepare_workspace(pkg, max_w=None):
    """参照渲染器要的是 <tpl>/assets/*.png; 把导出包的分层摆成它要的样子。
    max_w: 缩到指定宽度(标定参数时用小图, 快很多; 几何与公式与尺寸无关)。"""
    src = EXPORTS / pkg / "layers"
    work = Path(tempfile.mkdtemp(prefix="cmp-render-"))
    assets = work / "card" / "assets"
    assets.mkdir(parents=True)
    for name in ("background", "subject", "effects", "text", "lineart"):
        f = src / f"{name}.png"
        if not f.exists():
            continue
        im = Image.open(f).convert("RGBA")
        if max_w and im.width > max_w:
            im = im.resize((max_w, int(round(im.height * max_w / im.width))), Image.LANCZOS)
        im.save(assets / f"{name}.png")
    return work


def reference_image(cfg, rx, ry):
    """项目的公式: 返回 0~1 的 RGB float 数组。"""
    return R.compose_front("card", cfg, rx, ry, None)


# ------------------------------------------------- 小程序的做法(CSS 近似)

def css_linear_gradient(w, h, deg, stops):
    """
    CSS linear-gradient(deg, ...) 的栅格化。
    stops: [(位置0~1, (r,g,b), alpha0~1), ...]
    返回 (rgb float [h,w,3] 0~1, alpha [h,w] 0~1)
    """
    ang = math.radians(deg)
    # CSS: 0deg 指向上, 顺时针增加; 渐变方向向量
    dx, dy = math.sin(ang), -math.cos(ang)
    line = abs(w * dx) + abs(h * dy)          # 渐变线长度
    ys, xs = np.mgrid[0:h, 0:w]
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    # 每个像素在渐变方向上的投影 → 0~1
    t = ((xs - cx) * dx + (ys - cy) * dy) / line + 0.5
    t = np.clip(t, 0, 1)

    pos = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=np.float64)
    alphas = np.array([s[2] for s in stops], dtype=np.float64)

    rgb = np.zeros((h, w, 3), dtype=np.float64)
    a = np.zeros((h, w), dtype=np.float64)
    for ch in range(3):
        rgb[..., ch] = np.interp(t, pos, cols[:, ch])
    a = np.interp(t, pos, alphas)
    return rgb, a


def css_radial_gradient(w, h, cx_pct, cy_pct, rx_pct, ry_pct, color, alpha, stop):
    """CSS radial-gradient(椭圆 at cx% cy%, color, transparent stop%) 的栅格化。"""
    ys, xs = np.mgrid[0:h, 0:w]
    cx, cy = cx_pct / 100.0 * (w - 1), cy_pct / 100.0 * (h - 1)
    rx, ry = rx_pct / 100.0 * w, ry_pct / 100.0 * h
    d = np.sqrt(((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2)
    t = np.clip(d / stop, 0, 1)
    rgb = np.ones((h, w, 3), dtype=np.float64) * np.array(color, dtype=np.float64)
    a = alpha * (1.0 - t)
    return rgb, a


def blend_soft_light(cb, cs):
    """W3C soft-light"""
    d = np.where(cb <= 0.25, ((16 * cb - 12) * cb + 4) * cb, np.sqrt(np.clip(cb, 0, 1)))
    return np.where(cs <= 0.5,
                    cb - (1 - 2 * cs) * cb * (1 - cb),
                    cb + (2 * cs - 1) * (d - cb))


def blend_screen(cb, cs):
    return cb + cs - cb * cs


def compose_miniprogram(cfg, rx, ry, k_grad=1.0, k_film=0.0, k_rim=0.0):
    """
    照 holo-card 组件的层叠方式重算一遍:
      背景(位移 + 放大盖边) → 主体 → 光点 → [材质层] → 文字(不动)

    材质层有三个可调项(CSS 能做的近似):
      k_grad: 静态材质渐变(soft-light / overlay) —— **当前线上做法就是 k_grad=1**
      k_film: 随视角平移的彩虹薄膜(screen) —— 参照里有, 但 CSS 整层叠加容易过头
      k_rim : 边框内发光 —— 参照里边框区域会明显亮起来, 这圈内发光是用来逼近它的
    """
    assets = Path(R.SET) / "card" / "assets"
    bg = np.asarray(Image.open(assets / "background.png").convert("RGBA")).astype(np.float32)
    sub = np.asarray(Image.open(assets / "subject.png").convert("RGBA")).astype(np.float32)
    fx = np.asarray(Image.open(assets / "effects.png").convert("RGBA")).astype(np.float32)
    tx = np.asarray(Image.open(assets / "text.png").convert("RGBA")).astype(np.float32)
    h, w = bg.shape[:2]

    p = cfg["parameters"]
    view = R.view_vector(rx, ry)
    gate_raw = float(np.clip((np.hypot(view[0], view[1]) - 0.12) * 3.2, 0, 1))
    foil = float(p.get("foil", 0.55))
    amount = foil * (0.15 + 0.85 * gate_raw)

    def shift(depth):
        return R.parallax_shift(view, depth)

    # 1) 背景: 先放大(我的"盖住位移露边"规则), 再位移
    dx_uv, dy_uv = shift(p.get("backgroundDepth", -0.30))
    shrink = 1.0 + 2 * (abs(dx_uv)) + 2 * (abs(dy_uv))          # uv 单位, 与像素规则等价
    if shrink > 1.2:
        shrink = 1.2
    if shrink > 1.0001:
        nw, nh = int(round(w / shrink)), int(round(h / shrink))
        small = Image.fromarray(bg.astype(np.uint8), "RGBA").resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(small, ((w - nw) // 2, (h - nh) // 2))
        bg = np.asarray(canvas).astype(np.float32)
    col = R.sample(bg, dx_uv, dy_uv)[..., :3] / 255.0

    # 2) 主体
    s = R.sample(sub, *shift(p.get("subjectDepth", 0.34)), clip_alpha=True)
    sa = s[..., 3:4] / 255.0
    col = col * (1 - sa) + (s[..., :3] / 255.0) * sa

    # 3) 光点
    e = R.sample(fx, *shift(p.get("effectsDepth", 0.64)), clip_alpha=True)
    ea = e[..., 3:4] / 255.0
    col = col * (1 - ea) + (e[..., :3] / 255.0) * ea

    # 4) 材质层(夹在光点与文字之间)
    finish = str((cfg.get("appearance") or {}).get("finish") or "pearl").lower()
    if finish != "original":
        ys, xs = np.mgrid[0:h, 0:w]
        u = xs / (w - 1)
        v = ys / (h - 1)

        # 4a) 静态材质渐变(当前线上做法; 也是网页版 CSS-3D 路径的做法)
        if k_grad > 0:
            if finish == "gold":
                stops = [(0.0, (230, 180, 80), 0.55), (0.45, (201, 162, 74), 0.18),
                         (0.70, (255, 244, 210), 0.12), (1.0, (255, 244, 210), 0.12)]
                use_overlay = True
            elif finish == "silver":
                stops = [(0.0, (210, 214, 220), 0.50), (0.45, (180, 186, 192), 0.16),
                         (0.70, (245, 248, 252), 0.14), (1.0, (245, 248, 252), 0.14)]
                use_overlay = False
            else:
                stops = [(0.0, (255, 255, 255), 0.40), (0.50, (200, 205, 215), 0.12),
                         (0.75, (255, 255, 255), 0.30), (1.0, (255, 255, 255), 0.30)]
                use_overlay = False
            grgb, ga = css_linear_gradient(w, h, 118, stops)
            grgb = grgb / 255.0
            ag = (ga * np.clip(amount * k_grad, 0, 1))[..., None]
            if use_overlay:
                blended = np.where(col <= 0.5, 2 * col * grgb,
                                   1 - 2 * (1 - col) * (1 - grgb))
            else:
                blended = blend_soft_light(col, grgb)
            col = col * (1 - ag) + blended * ag

        # 4b) 彩虹薄膜(相位随视角平移, 照 shader 的 phase 公式)
        if k_film > 0:
            phase = (u * 0.85 + v * 0.55 + view[0] * 1.5 - view[1] * 0.9)
            film = 0.74 + 0.17 * np.cos(6.28318 * (phase[..., None] + np.array([0.0, 0.33, 0.67])))
            af = np.clip(amount * k_film, 0, 1)
            col = col * (1 - af) + blend_screen(col, np.clip(film, 0, 1)) * af

        # 4c) 边框内发光
        if k_rim > 0:
            edge = 1.0 - R.smoothstep(0.015, 0.06,
                                      np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v)))
            ar = np.clip(amount * k_rim, 0, 1)
            rim = np.clip(edge, 0, 1)[..., None] * np.array([0.76, 0.78, 0.82])
            col = col * (1 - ar) + blend_screen(col, rim) * ar

    # 5) 文字(固定不动, 且不上材质)
    t = R.sample(tx, *R.parallax_shift(view, p.get("textDepth", 0.0)), clip_alpha=True)
    ta = t[..., 3:4] / 255.0
    col = col * (1 - ta) + (t[..., :3] / 255.0) * ta
    return np.clip(col, 0, 1)


# ---------------------------------------------------------------- 对比

def diff_metrics(ref, mine):
    d = np.abs(ref - mine) * 255.0
    gray = d.mean(axis=2)
    return {
        "mean": float(gray.mean()),
        "p95": float(np.percentile(gray, 95)),
        "over12": float((gray > 12).mean() * 100),
        "max": float(gray.max()),
    }


def calibrate(pkgs, angles=None):
    """
    标定 CSS 的三个近似项(k_grad / k_film / k_rim), 并和"当前线上做法"公平对比:
      基线 = k_grad=1, k_film=0, k_rim=0   (小程序现在就是这么做的)
    只在第一张卡上粗标, 再在其余卡上验证 —— 不逐卡过拟合。
    """
    angles = angles or [(0.06, 0.16), (0.12, 0.28), (0.20, 0.42)]
    fit_pkg = pkgs[0]
    work = prepare_workspace(fit_pkg, max_w=320)
    R.SET = work
    cfg = json.loads((EXPORTS / fit_pkg / "showcase" / "card-config.json").read_text(encoding="utf8"))
    refs = [(a, reference_image(cfg, *a)) for a in angles]

    def score(k_grad, k_film, k_rim):
        total = 0.0
        for (a, ref) in refs:
            mine = compose_miniprogram(cfg, a[0], a[1], k_grad, k_film, k_rim)
            total += abs(ref - mine).mean() * 255
        return total / len(refs)

    base = score(1.0, 0.0, 0.0)
    best = (base, 1.0, 0.0, 0.0)
    for k_grad in (0.0, 0.5, 1.0):
        for k_film in (0.0, 0.1, 0.25):
            for k_rim in (0.0, 0.3, 0.6, 1.0):
                v = score(k_grad, k_film, k_rim)
                if v < best[0] - 1e-9:
                    best = (v, k_grad, k_film, k_rim)
    shutil.rmtree(work, ignore_errors=True)
    print(f"当前线上做法(静态渐变, 无边框处理)在 {fit_pkg} 上: {base:.2f}/255")
    print(f"CSS 能做到的最好: {best[0]:.2f}/255  "
          f"(k_grad={best[1]}, k_film={best[2]}, k_rim={best[3]})")
    print(f"→ CSS 能补掉 {(1 - best[0] / base) * 100:.0f}% 的差距")
    if best[2] == 0:
        print("  注意: 优化器把「彩虹薄膜」关掉了 —— 用 CSS 整层叠加去近似 "
              "shader 的逐像素薄膜会过头, 反而更差")

    print("\n在各卡上验证(小图):")
    for pkg in pkgs:
        work = prepare_workspace(pkg, max_w=320)
        R.SET = work
        cfg = json.loads((EXPORTS / pkg / "showcase" / "card-config.json").read_text(encoding="utf8"))
        b = t = 0.0
        for a in angles:
            ref = reference_image(cfg, *a)
            b += abs(ref - compose_miniprogram(cfg, a[0], a[1], 1.0, 0.0, 0.0)).mean() * 255
            t += abs(ref - compose_miniprogram(cfg, a[0], a[1], best[1], best[2], best[3])).mean() * 255
        n = len(angles)
        print(f"  {pkg:<12} 线上 {b / n:6.2f} → 调优后 {t / n:6.2f}   (降 {100 * (1 - t / max(b, 1e-6)):.0f}%)")
        shutil.rmtree(work, ignore_errors=True)
    return best


def main():
    if "--calibrate" in sys.argv:
        pkgs = [p.name for p in sorted(EXPORTS.iterdir())
                if p.is_dir() and (p / "showcase" / "card-config.json").exists()]
        calibrate(pkgs)
        return 0

    pkg = sys.argv[1] if len(sys.argv) > 1 else "CARD-0001"
    if not (EXPORTS / pkg).exists():
        raise SystemExit(f"找不到 exports/{pkg}")

    work = prepare_workspace(pkg)
    R.SET = work
    cfg = json.loads((EXPORTS / pkg / "showcase" / "card-config.json").read_text(encoding="utf8"))

    angles = [("静止", 0.0, 0.0), ("轻倾斜", 0.06, 0.16), ("大倾斜", 0.20, 0.42)]
    panels, captions = [], []
    print(f"\n{pkg}  ——  参照(工作台 shader 公式) vs 小程序(CSS 近似)")
    print(f"  {'状态':<8}{'平均差异':>10}{'p95':>9}{'>12 的像素占比':>16}{'最大差异':>10}")
    for label, rx, ry in angles:
        ref = reference_image(cfg, rx, ry)
        mine = compose_miniprogram(cfg, rx, ry, 1.0, 0.0, 0.0)
        m = diff_metrics(ref, mine)
        print(f"  {label:<8}{m['mean']:>9.2f} {m['p95']:>8.1f} {m['over12']:>14.1f}% "
              f"{m['max']:>9.1f}")
        panels.append(Image.fromarray((ref * 255).astype(np.uint8), "RGB"))
        captions.append(f"{label} · 工作台参照")
        panels.append(Image.fromarray((mine * 255).astype(np.uint8), "RGB"))
        captions.append(f"{label} · 小程序")
        d = np.abs(ref - mine).mean(axis=2)
        heat = np.clip(d * 255 * 3, 0, 255).astype(np.uint8)
        panels.append(Image.fromarray(np.stack([heat, heat // 3, heat // 3], -1), "RGB"))
        captions.append(f"{label} · 差异(放大3倍)")

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "render-compare.png"
    R.sheet(panels, captions, f"{pkg} · 小程序 vs 工作台渲染", cols=3).save(out)
    print(f"\n对比图: {out.relative_to(ROOT)}")
    shutil.rmtree(work, ignore_errors=True)
    print("说明: 参照图用的是项目自带渲染器(与网页 shader 同公式);")
    print("      小程序这边是实际组件里的做法(2D 视差 + 整卡材质覆盖层)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
