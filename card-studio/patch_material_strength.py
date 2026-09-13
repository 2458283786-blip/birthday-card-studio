# -*- coding: utf-8 -*-
"""
材质强度补丁: 让"镜面(gloss)/箔(foil)"真正看得出光泽
====================================================
现状: 所有材质的加法项幅度都按"克制"调, 镜面看起来几乎无变化。
改动(只动幅度与高光锐度, 不动结构):
  * gloss: 增益 ×2.6, 高光带更锐(band^1.45), 追加一层宽高光("湿感")
  * foil : 增益 ×1.5, 高光带略锐(band^1.15)
  * 卡框混合系数: gloss .42 / foil .34 / 其他 .26
同时镜像到离线渲染器(render_previews), 保证静态图与网页一致。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------- app.js / bundle: applyMat ----------------
A_OLD = """vec3 applyMat(vec3 col, vec2 uv, float type, float amount, float band, float boost) {
  if (amount <= 0.001) return col;
  vec3 f = styleFilm(uv, type);
  float lum = dot(col, vec3(.2126,.7152,.0722));
  col *= 1. - amount*.11*(1.-f)*(.2+band*.8);
  col += f*amount*band*boost*(.028+.06*(1.-lum));
  return col;
}"""
A_NEW = """vec3 applyMat(vec3 col, vec2 uv, float type, float amount, float band, float boost) {
  if (amount <= 0.001) return col;
  vec3 f = styleFilm(uv, type);
  float lum = dot(col, vec3(.2126,.7152,.0722));
  float isGloss = step(2.5, type);
  float isFoil = step(1.5, type) * (1.0 - isGloss);
  float gain = 1.0 + isGloss*1.6 + isFoil*0.5;          // 镜面/箔更亮
  float bnd = mix(band, pow(band, 1.45), isGloss);      // 镜面高光更锐
  col *= 1. - amount*.11*(1.-f)*(.2+bnd*.8);
  col += f*amount*bnd*gain*boost*(.028+.06*(1.-lum));
  col += f*amount*isGloss*.045*(1.-lum);                // 清漆的"湿感"宽高光
  return col;
}"""

# ---------------- 卡框混合系数 ----------------
B_OLD = """  col = mix(col, fFrame*.75+.21, wFrame*aFrame*(uFinish > 2.5 ? .34 : .26));"""
B_NEW = """  float frameK = uMatType.x > 2.5 ? .42 : (uMatType.x > 1.5 ? .34 : .26);
  col = mix(col, fFrame*.75+.21, wFrame*aFrame*frameK);"""

APP_REPL = [(A_OLD, A_NEW, "float isGloss = step(2.5, type);", "applyMat 强度"),
            (B_OLD, B_NEW, "float frameK = uMatType.x", "卡框混合系数")]

# ---------------- render_previews(离线一致) ----------------
P_OLD = """def apply_mat(col, u, v, view, mtype, amount, band, boost):
    if amount <= 0.001:
        return col
    f = style_film(u, v, view, mtype)
    lum = col[..., 0] * 0.2126 + col[..., 1] * 0.7152 + col[..., 2] * 0.0722
    col = col * (1.0 - amount * 0.11 * (1.0 - f) * (0.2 + band[..., None] * 0.8))
    col = col + f * (amount * band * boost * (0.028 + 0.06 * (1.0 - lum)))[..., None]
    return col"""
P_NEW = """def apply_mat(col, u, v, view, mtype, amount, band, boost):
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
    return col"""
PREV_REPL = [(P_OLD, P_NEW, "is_gloss = 1.0 if mtype > 2.5", "离线 apply_mat")]


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
