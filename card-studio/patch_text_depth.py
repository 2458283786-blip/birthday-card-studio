# -*- coding: utf-8 -*-
"""
文字层景深补丁
=============
给文字层加独立深度 `parameters.textDepth`:
  * 0(默认)= 现在的行为(文字固定在最前, 不参与视差)
  * >0      = 文字按自己的深度做视差(比主体更"浮", 形成真实景深)

改动(app.js, 单一来源; 之后由 rebuild_bundles.py 重建 bundle):
  1. common 增加 uniform float uTextDepth;
  2. frontFragment 里文字改为按 parallax(uv, uTextDepth) 采样, 越界处按 inside() 淡出(不拖影);
  3. 文字材质用同一个采样坐标;
  4. uniforms 增加 uTextDepth: p.textDepth ?? 0
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

R1_OLD = "uniform vec4 uMatType, uMatAmt;"
R1_NEW = "uniform vec4 uMatType, uMatAmt;\nuniform float uTextDepth;   // 文字层自己的景深(0=固定在最前)"

R2_OLD = "  vec4 text = texture2D(tText,uv);"
R2_NEW = ("  vec2 tu = parallax(uv, uTextDepth);\n"
          "  vec4 text = texture2D(tText, clamp(tu,0.,1.));\n"
          "  text.a *= inside(tu);")

R3_OLD = "    vec3 cText = applyMat(text.rgb, uv, uMatType.y, uMatAmt.y*gate, band, goldBoost);"
R3_NEW = "    vec3 cText = applyMat(text.rgb, tu, uMatType.y, uMatAmt.y*gate, band, goldBoost);"

R4_OLD = "    uMatType: { value: new THREE.Vector4(matType[0], matType[1], matType[2], matType[3]) },"
R4_NEW = (R4_OLD + "\n"
          "    uTextDepth: { value: p.textDepth ?? 0 },")

REPL = [
    (R1_OLD, R1_NEW, "uniform float uTextDepth", "GLSL uniform"),
    (R2_OLD, R2_NEW, "vec2 tu = parallax(uv, uTextDepth)", "GLSL 文字采样"),
    (R3_OLD, R3_NEW, "applyMat(text.rgb, tu,", "GLSL 文字材质坐标"),
    (R4_OLD, R4_NEW, "uTextDepth: { value: p.textDepth ?? 0 }", "JS uniform"),
]


def patch_file(p):
    s = p.read_text(encoding="utf8")
    out = []
    for old, new, marker, label in REPL:
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


def targets():
    out = [ROOT / "RuiC-card-skill-main" / "assets" / "web-template" / "app.js"]
    for d in ("demo-koi", "demo-birthday"):
        f = ROOT / d / "web" / "app.js"
        if f.exists():
            out.append(f)
    for sub in (ROOT / "birthday-set").glob("*"):
        if (sub / "app.js").exists():
            out.append(sub / "app.js")
    for d in ("birthday-build", "card-studio/projects"):
        for sub in (ROOT / d).glob("*"):
            f = sub / "web" / "app.js"
            if f.exists():
                out.append(f)
    return out


def main():
    for f in targets():
        print(f"{f.relative_to(ROOT)}  " + "  ".join(patch_file(f)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
