# -*- coding: utf-8 -*-
"""
Material System 补丁(文档 §4 / §19)
===================================
四种材质 × 四个区域:
  材质 0 哑光 Matte / 1 珠光 Pearl / 2 金属箔 Foil / 3 亮面 Gloss
  区域 x 边框 Frame / y 文字 Text / z 主体 Subject / w 底纹 Background
配置来源: card-config.json → material.{regions, amounts, holoEnabled}
未配置时的默认值 = 现有观感(边框/主体/底纹 用珍珠光泽, 文字不反光)。

只改 app.js(单一来源), 随后由 rebuild_bundles.py 重建 app.bundle.js。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------- GLSL ----------
A1_OLD = "uniform vec2 uFit, uSafeOffset;"
A1_NEW = ("uniform vec2 uFit, uSafeOffset;\n"
          "// 分区材质: 0 哑光 / 1 珠光 / 2 金属箔 / 3 亮面\n"
          "uniform vec4 uMatType, uMatAmt;")

A2_OLD = """float sweep(vec2 uv) {
  return pow(.5+.5*sin((uv.x*.72+uv.y*.45+uView.x*1.2+uView.y*.6)*6.283),10.);
}"""
A2_NEW = A2_OLD + """
vec3 pearlFilm(vec2 uv) {
  float phase = uv.x*.85 + uv.y*.55 + uView.x*1.5 - uView.y*.9;
  return .74 + .17*cos(6.28318*(phase + vec3(0.,.33,.67)));
}
vec3 foilFilm(vec2 uv) {
  float phase = uv.x*.62 + uv.y*.38 + uView.x*2.2 - uView.y*1.3;
  float hi = .5+.5*sin(phase*6.28318*1.6);
  return mix(vec3(.62,.46,.22), vec3(1.,.94,.72), hi);
}
vec3 glossFilm(vec2 uv) {
  float phase = uv.x*.35 + uv.y*1.15 + uView.y*1.4;
  float s = pow(.5+.5*sin(phase*6.28318), 1.6);
  return mix(vec3(.84,.87,.90), vec3(1.), s);
}
vec3 styleFilm(vec2 uv, float type) {
  if (type > 2.5) return glossFilm(uv);
  if (type > 1.5) return foilFilm(uv);
  return pearlFilm(uv);
}
// 单个区域施加材质(amount=0 即哑光, 原样返回)
vec3 applyMat(vec3 col, vec2 uv, float type, float amount, float band, float boost) {
  if (amount <= 0.001) return col;
  vec3 f = styleFilm(uv, type);
  float lum = dot(col, vec3(.2126,.7152,.0722));
  col *= 1. - amount*.11*(1.-f)*(.2+band*.8);
  col += f*amount*band*boost*(.028+.06*(1.-lum));
  return col;
}"""

A3_OLD = """  vec3 foil = film(uv);
  float tilt = clamp((length(uView.xy) - 0.12) * 3.2, 0.0, 1.0);
  float amount = strength() * mix(0.15, 1.0, tilt);
  float luminance = dot(col,vec3(.2126,.7152,.0722));
  float band = sweep(uv);
  // Laminate changes with the card-local viewing direction; black print stays readable.
  float goldBoost = uFinish > 2.5 ? 1.7 : 1.0;
  col *= 1. - amount * .11 * (1.-foil) * (.2 + band*.8);
  col += foil * amount * band * goldBoost * (.028 + .06*(1.-luminance));
  float edge = 1.-smoothstep(.015,.06,min(min(uv.x,1.-uv.x),min(uv.y,1.-uv.y)));
  col = mix(col,foil*.75+.21,edge*amount*(uFinish > 2.5 ? .22 : .16));
  vec2 cell = floor(uv*vec2(480.,720.));
  float flake = step(.9975,hash(cell))*pow(.5+.5*sin(hash(cell+8.)*30.+uView.x*20.+uTime*.6),10.);
  col += foil*flake*amount*.08;
  float line = (1.-smoothstep(.06,.25,texture2D(tLine,clamp(su,0.,1.)).r))*uHasLine;
  col += line*inside(su)*subject.a*band*amount*.035;
  vec4 text = texture2D(tText,uv);
  col = mix(col,text.rgb,text.a*(1.-uRelief));"""
A3_NEW = """  // ---- 分区材质(边框 / 文字 / 主体 / 底纹) ----
  float tilt = clamp((length(uView.xy) - 0.12) * 3.2, 0.0, 1.0);
  float gate = mix(0.15, 1.0, tilt);
  float band = sweep(uv);
  float goldBoost = uFinish > 2.5 ? 1.7 : 1.0;
  float edge = 1.-smoothstep(.015,.06,min(min(uv.x,1.-uv.x),min(uv.y,1.-uv.y)));
  vec4 text = texture2D(tText,uv);
  float wFrame = clamp(edge,0.,1.);
  float wText = clamp(text.a*(1.-uRelief),0.,1.)*(1.-wFrame);
  float wSub = clamp(subject.a,0.,1.)*(1.-wFrame)*(1.-wText);
  float wBg = clamp(1.-wFrame-wText-wSub,0.,1.);
  // 主体 / 底纹: 先按各自材质处理表面色
  vec3 cSub = applyMat(col, uv, uMatType.z, uMatAmt.z*gate, band, goldBoost);
  vec3 cBg = applyMat(col, uv, uMatType.w, uMatAmt.w*gate, band, goldBoost);
  col = cSub*wSub + cBg*wBg + col*(wFrame+wText);
  // 边框: 材质 + 边缘高光
  float aFrame = clamp(uMatAmt.x,0.,1.)*gate;
  vec3 fFrame = styleFilm(uv, uMatType.x);
  col = mix(col, fFrame*.75+.21, wFrame*aFrame*(uFinish > 2.5 ? .34 : .26));
  // sparkle / 线稿辉光: 用各区域里的最大强度
  float sparkAmt = max(max(uMatAmt.x,uMatAmt.y), max(uMatAmt.z,uMatAmt.w))*gate;
  vec2 cell = floor(uv*vec2(480.,720.));
  float flake = step(.9975,hash(cell))*pow(.5+.5*sin(hash(cell+8.)*30.+uView.x*20.+uTime*.6),10.);
  col += styleFilm(uv,uMatType.x)*flake*sparkAmt*.08;
  float line = (1.-smoothstep(.06,.25,texture2D(tLine,clamp(su,0.,1.)).r))*uHasLine;
  col += line*inside(su)*subject.a*band*sparkAmt*.035;
  // 文字: 自己的材质(可做烫金字)
  if (wText > 0.001) {
    vec3 cText = applyMat(text.rgb, uv, uMatType.y, uMatAmt.y*gate, band, goldBoost);
    col = mix(col, cText, wText);
  }"""

A4_OLD = "  vec3 col = mix(vec3(.66,.69,.67),film(vUv)*.6+.35,strength()*.7);"
A4_NEW = "  vec3 col = mix(vec3(.66,.69,.67),styleFilm(vUv,uMatType.x)*.6+.35,clamp(uMatAmt.x,0.,1.)*.7);"

# ---------- JS ----------
A5_OLD = """  const p = config.parameters || {};
  const imageAspect = textures[0].image.width / textures[0].image.height;"""
A5_NEW = """  const p = config.parameters || {};
  // 材质系统: 四区域(边框/文字/主体/底纹) × 四种材质
  const MAT_INDEX = { matte: 0, pearl: 1, foil: 2, gloss: 3 };
  const matCfg = config.material || {};
  const holoOn = matCfg.holoEnabled !== false &&
    String((config.appearance || {}).finish || "").toLowerCase() !== "original";
  const matRegion = matCfg.regions || {};
  const matAmount = matCfg.amounts || {};
  const foilBase = p.foil ?? 0.52;
  const matTypeOf = (k, d) => MAT_INDEX[String(matRegion[k] || d).toLowerCase()] ?? MAT_INDEX[d];
  const matAmtOf = (k, d) => (holoOn ? (matAmount[k] ?? (d === "text" ? 0 : foilBase)) : 0);
  const matType = [matTypeOf("frame", "pearl"), matTypeOf("text", "matte"),
                   matTypeOf("subject", "pearl"), matTypeOf("background", "pearl")];
  const matAmt = [matAmtOf("frame", "frame"), matAmtOf("text", "text"),
                  matAmtOf("subject", "subject"), matAmtOf("background", "background")];
  const imageAspect = textures[0].image.width / textures[0].image.height;"""

A6_OLD = "    uFoil: { value: p.foil ?? 0.52 },"
A6_NEW = (A6_OLD + "\n"
          "    uMatType: { value: new THREE.Vector4(matType[0], matType[1], matType[2], matType[3]) },\n"
          "    uMatAmt: { value: new THREE.Vector4(matAmt[0], matAmt[1], matAmt[2], matAmt[3]) },")

REPL = [
    (A1_OLD, A1_NEW, "uMatType, uMatAmt", "GLSL uniforms"),
    (A2_OLD, A2_NEW, "vec3 styleFilm(vec2 uv, float type)", "GLSL 材质函数"),
    (A3_OLD, A3_NEW, "分区材质(边框 / 文字 / 主体 / 底纹)", "GLSL 分区渲染"),
    (A4_OLD, A4_NEW, "styleFilm(vUv,uMatType.x)", "GLSL 卡边材质"),
    (A5_OLD, A5_NEW, "const MAT_INDEX", "JS 材质推导"),
    (A6_OLD, A6_NEW, "uMatType: { value: new THREE.Vector4", "JS uniforms"),
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
    files = targets()
    for f in files:
        print(f"{f.relative_to(ROOT)}  " + "  ".join(patch_file(f)))
    print(f"共处理 {len(files)} 个 app.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
