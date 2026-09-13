# -*- coding: utf-8 -*-
"""
材质强度补丁 v2: 给镜面/箔加"会过曝的明确高光"
============================================
v1 只放大了按亮度加权的加法项 → 在已经发亮的白字/金线上几乎看不出来。
v2 增加一项**与底色亮度无关**的镜面反射(可以过曝成白), 于是倾斜时
大数字与卡框会"扫过一道白光" —— 这才是清漆/箔的观感。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

S_OLD = "  col += f*amount*isGloss*.045*(1.-lum);                // 清漆的\"湿感\"宽高光"
S_NEW = ("  col += f*amount*isGloss*.045*(1.-lum);                // 清漆的\"湿感\"宽高光\n"
         "  col += vec3(1.0) * (isGloss*specB(bnd)*amount*0.45);   // 镜面: 与底色亮度无关, 可过曝\n"
         "  col += f * (isFoil*specB(bnd)*amount*0.24);            // 箔: 稍弱的定向高光")
S_HELPER_OLD = """vec3 applyMat(vec3 col, vec2 uv, float type, float amount, float band, float boost) {"""
S_HELPER_NEW = """float specB(float b) { return pow(clamp(b,0.,1.), 1.15); }
vec3 applyMat(vec3 col, vec2 uv, float type, float amount, float band, float boost) {"""

P_OLD = """    col = col + f * (amount * is_gloss * 0.045 * (1.0 - lum))[..., None]
    return col"""
P_NEW = """    col = col + f * (amount * is_gloss * 0.045 * (1.0 - lum))[..., None]
    spec = np.clip(bnd, 0, 1) ** 1.15
    col = col + spec[..., None] * (is_gloss * amount * 0.45)
    col = col + f * (is_foil * spec * amount * 0.24)[..., None]
    return col"""

APP_REPL = [(S_HELPER_OLD, S_HELPER_NEW, "float specB(float b)", "镜面高光函数"),
            (S_OLD, S_NEW, "isGloss*specB(bnd)*amount*0.45", "镜面/箔 过曝高光")]
PREV_REPL = [(P_OLD, P_NEW, "spec = np.clip(bnd, 0, 1) ** 1.15", "离线 镜面高光")]


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
