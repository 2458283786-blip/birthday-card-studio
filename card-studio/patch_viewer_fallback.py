# -*- coding: utf-8 -*-
"""
查看器 fallback 补丁(文档 §16)
=============================
规则:
  * 缺少 3D 模型(GLB)      → 走 CSS-3D / 2D 回退
  * 缺少分层(subject/background/text) → 用 front.png 当完整卡面
  * CSS-3D 回退里: 有 back.png 就显示真背面, 否则显示卡名
  * 无分层素材且无 front.png → 明确报错(不白屏)
同步改写 app.js 与 app.bundle.js(两者字符串一致), 并对所有已生成项目的 web 目录生效。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

R1_OLD = '  document.title = config.title + " · 白相";'
R1_NEW = ('  document.title = config.title + " · 白相";\n'
          '  // §16 缺少 3D 模型 → 2D/CSS-3D 回退\n'
          '  if (!(config.assets && config.assets.model)) {\n'
          '    fallback3D(new Error("缺少 3D 模型, 使用 2D 回退"));\n'
          '    return;\n'
          '  }')

R2_OLD = """  const textureLoader = new THREE.TextureLoader();
  const textures = await Promise.all(
    ["subject", "background", "text"].map((name) =>
      textureLoader.loadAsync(config.assets[name]),
    ),
  );"""
R2_NEW = """  const textureLoader = new THREE.TextureLoader();
  const A = config.assets || {};
  const blankTex = () => {
    const t = new THREE.DataTexture(new Uint8Array([0, 0, 0, 0]), 1, 1);
    t.needsUpdate = true;
    return t;
  };
  // §16 缺少分层素材时回退到整张 front.png; 连 front.png 都没有才报错
  const hasLayers = !!(A.subject && A.background && A.text);
  let textures;
  if (hasLayers) {
    textures = await Promise.all(
      ["subject", "background", "text"].map((name) => textureLoader.loadAsync(A[name])),
    );
  } else if (A.front) {
    const frontOnly = await textureLoader.loadAsync(A.front);
    textures = [blankTex(), frontOnly, blankTex()];
    console.warn("[holo-card] 缺少分层素材, 已回退到 front.png");
  } else {
    throw Error("缺少卡面素材: 需要分层图或 front.png");
  }"""

R3_OLD = """  const back = document.createElement("div");
  back.className = "face3d back3d";
  const backMark = document.createElement("span");
  backMark.className = "back-mark";
  backMark.textContent = "白相";
  back.append(backMark);"""
R3_NEW = """  const back = document.createElement("div");
  back.className = "face3d back3d";
  if (config?.assets?.back) {
    const bimg = document.createElement("img");
    bimg.src = config.assets.back;
    bimg.alt = "卡片背面";
    bimg.loading = "eager";
    bimg.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;";
    back.append(bimg);
  } else {
    const backMark = document.createElement("span");
    backMark.className = "back-mark";
    backMark.textContent = config.title || "CARD";
    back.append(backMark);
  }"""

R4_OLD = """  const foil = document.createElement("div");
  foil.className = "foil3d";"""
R4_NEW = """  // §16 没有分层但有 front.png 时, 整张正片作为唯一图层
  if (!layers.size && config?.assets?.front) {
    const layer = document.createElement("div");
    layer.className = "layer3d";
    const img = document.createElement("img");
    img.src = config.assets.front;
    img.alt = config.title || "卡片";
    img.loading = "eager";
    layer.append(img);
    front.append(layer);
    layers.set("front", { el: layer, z: -48 });
  }
  const foil = document.createElement("div");
  foil.className = "foil3d";"""

R2B_OLD = ('  const textures = await Promise.all(["subject", "background", "text"]'
           '.map((name) => textureLoader.loadAsync(config.assets[name])));')
R2B_NEW = """  const A = config.assets || {};
  const blankTex = () => { const t = new DataTexture(new Uint8Array([0, 0, 0, 0]), 1, 1); t.needsUpdate = true; return t; };
  const hasLayers = !!(A.subject && A.background && A.text);
  let textures;
  if (hasLayers) {
    textures = await Promise.all(["subject", "background", "text"].map((name) => textureLoader.loadAsync(A[name])));
  } else if (A.front) {
    const frontOnly = await textureLoader.loadAsync(A.front);
    textures = [blankTex(), frontOnly, blankTex()];
    console.warn("[holo-card] 缺少分层素材, 已回退到 front.png");
  } else {
    throw Error("缺少卡面素材: 需要分层图或 front.png");
  }"""

# (old, new, 幂等标记, 说明)
REPL = [
    (R1_OLD, R1_NEW, "缺少 3D 模型 → 2D/CSS-3D 回退", "R1 缺模型回退"),
    (R2_OLD, R2_NEW, "已回退到 front.png", "R2 缺分层回退(源码版)"),
    (R2B_OLD, R2B_NEW, "已回退到 front.png", "R2 缺分层回退(打包版)"),
    (R3_OLD, R3_NEW, "config?.assets?.back", "R3 CSS-3D 真背面"),
    (R4_OLD, R4_NEW, "整张正片作为唯一图层", "R4 CSS-3D 单图层"),
]


def _insert_bodies():
    """插入式补丁的"插入体"(不含锚点行), 用于折叠历史重复。"""
    bodies = []
    for old, new in ((R1_OLD, R1_NEW), (R4_OLD, R4_NEW)):
        if new.endswith(old):                 # 锚点在尾部(R4 形态)
            body = new[: -len(old)]
        elif old + "\n" in new:               # 锚点在开头(R1 形态)
            body = new.replace(old + "\n", "", 1)
        else:
            body = new.replace(old, "")
        bodies.append(body.strip("\n"))
    return bodies


def dedupe(s):
    for body in _insert_bodies():
        dup = body + "\n" + body
        while dup in s:
            s = s.replace(dup, body)
    return s


def patch_file(p):
    s = dedupe(p.read_text(encoding="utf8"))
    done = []
    for old, new, marker, label in REPL:
        if marker in s:                      # 标记优先 → 真正的幂等
            done.append(f"{label}:已存在")
            continue
        n = s.count(old)
        if n != 1:
            done.append(f"{label}:锚点{n}跳过")
            continue
        s = s.replace(old, new)
        done.append(f"{label}:OK")
    s = dedupe(s)
    p.write_text(s, encoding="utf8")
    return done


def targets():
    tpl = ROOT / "RuiC-card-skill-main" / "assets" / "web-template"
    out = [tpl / "app.js", tpl / "app.bundle.js"]
    for base in (ROOT / "demo-koi", ROOT / "demo-birthday"):
        for n in ("app.js", "app.bundle.js"):
            f = base / "web" / n
            if f.exists():
                out.append(f)
    for d in ("birthday-set", "birthday-build", "card-studio/projects"):
        for sub in (ROOT / d).glob("*"):
            for n in ("app.js", "app.bundle.js"):
                f = sub / "web" / n
                if f.exists():
                    out.append(f)
    return out


def main():
    files = targets()
    for f in files:
        res = patch_file(f)
        print(f"{f.relative_to(ROOT)}  " + "  ".join(res))
    print(f"共处理 {len(files)} 个查看器文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
