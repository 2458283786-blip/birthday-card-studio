# -*- coding: utf-8 -*-
"""
材质强度补丁 v3: 镜面改为"掠射角反射"(越斜越亮)
==============================================
v2 依赖窄高光带(一条移动细条), 采样角度常扫不到 → 看不出效果。
真实清漆的行为是: 正面接近无反射, 越接近掠射角反光越强。
改动: 在 applyMat 内按 uView 计算掠射强度, 直接给镜面/箔叠加白反射。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

S_OLD = ("  col += vec3(1.0) * (isGloss*specB(bnd)*amount*0.45);   // 镜面: 与底色亮度无关, 可过曝\n"
         "  col += f * (isFoil*specB(bnd)*amount*0.24);            // 箔: 稍弱的定向高光")
S_NEW = ("  // 掠射角反射: 越斜越亮(清漆/箔的真实行为), 与底色亮度无关\n"
         "  float graze = clamp((length(uView.xy) - 0.12) * 3.2, 0.0, 1.0);\n"
         "  float sheen = isGloss * (0.05 + 0.34*pow(graze, 1.5)) * amount;\n"
         "  col += vec3(1.0) * sheen;\n"
         "  col += (f*0.6 + vec3(0.4)) * (isFoil * (0.03 + 0.20*pow(graze, 1.4)) * amount);\n"
         "  col += vec3(1.0) * (isGloss*specB(bnd)*amount*0.22);   // 叠加一条窄闪光")

P_OLD = """    spec = np.clip(bnd, 0, 1) ** 1.15
    col = col + spec[..., None] * (is_gloss * amount * 0.45)
    col = col + f * (is_foil * spec * amount * 0.24)[..., None]
    return col"""
P_NEW = """    spec = np.clip(bnd, 0, 1) ** 1.15
    graze = float(np.clip((np.hypot(view[0], view[1]) - 0.12) * 3.2, 0.0, 1.0))
    col = col + (is_gloss * (0.05 + 0.34 * graze ** 1.5) * amount)
    col = col + f * (is_foil * (0.03 + 0.20 * graze ** 1.4) * amount)[..., None]
    col = col + spec[..., None] * (is_gloss * amount * 0.22)
    return col"""

APP_REPL = [(S_OLD, S_NEW, "float graze = clamp((length(uView.xy)", "镜面 掠射角反射")]
PREV_REPL = [(P_OLD, P_NEW, "graze = float(np.clip((np.hypot", "离线 掠射角反射")]


def patch(p, repls):
    s = p.read_text(encoding="utf8")
    out = []
    for old, new, marker, label in repls:
        if marker in s:
            out.append(f"{label}:已存在")
            continue
        n = s.count(old)
        if n != 1:
            out.append(f"{label}:锚点{n}跳过")
            continue
        s = s.replace(old, new)
        out.append(f"{label}:OK")
    p.write_text(s, encoding="utf8")
    return out


def web_dirs():
    out = [ROOT / "RuiC-card-skill-main" / "assets" / "web-template"]
    for d in ("demo-koi", "demo-birthday"):
        w = ROOT / d / "web"
        if w.is_dir():
            out.append(w)
    for sub in (ROOT / "birthday-set").glob("*"):
        if (sub / "app.js").exists():
            out.append(sub)
    for d in ("birthday-build", "card-studio/projects"):
        for sub in (ROOT / d).glob("*"):
            if (sub / "web").is_dir():
                out.append(sub / "web")
    return out


def main():
    for w in web_dirs():
        app = w / "app.js"
        if app.exists():
            print(f"{w.relative_to(ROOT)}  " + "  ".join(patch(app, APP_REPL)))
    rp = ROOT / "card-studio" / "render_previews.py"
    print("render_previews.py  " + "  ".join(patch(rp, PREV_REPL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
