# -*- coding: utf-8 -*-
"""
V2 建卡器: 按选定的 Design Language 把订单做成卡
=============================================
用法: python card-studio/dl2/build_card.py <项目目录> --lang portrait [--viewer-from <模板项目>]

做四件事:
  1. 用 design.build() 渲染正面(有分层就输出到 web/assets, 供 WebGL 3D)
  2. 出静态正片 / 预览图
  3. 出统一背面(render_previews.render_back)
  4. 更新 card-config.json(assets 指向分层、designLanguage、深度参数), 并准备好查看器文件
"""
import argparse
import json
import shutil
import sys

from PIL import Image
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import design  # noqa: E402
import render_previews as rp  # noqa: E402
import qr_util  # noqa: E402


def find_photo(project):
    for pat in ("_upload.*", "assets/source.png", "source.png"):
        hits = sorted(project.glob(pat))
        if hits:
            return hits[0]
    raise FileNotFoundError("项目里没有原照片(_upload.* / source.png)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--lang", default="portrait")
    ap.add_argument("--viewer-from", default=None, help="从这里复制查看器文件与 card.glb")
    a = ap.parse_args()

    proj = Path(a.project).resolve()
    photo = find_photo(proj)
    cfg_path = proj / "card-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf8")) if cfg_path.exists() else {}
    info = {"name": cfg.get("name", ""), "title": cfg.get("title", ""),
            "subtitle": cfg.get("subtitle") or "Personal Style",
            "edition": cfg.get("edition") or "", "technique": cfg.get("technique") or cfg.get("date") or ""}

    web_assets = proj / "web" / "assets"
    web_assets.mkdir(parents=True, exist_ok=True)
    out_dir = proj / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 正面(有分层就输出分层)
    front, spec = design.build(str(photo), info, lang=a.lang, out_dir=str(out_dir),
                               layers_dir=str(out_dir))     # 分层 PNG 放项目 assets/(供导出/印刷)
    front = Path(front)
    shutil.copy2(front, out_dir / "front.png")
    shutil.copy2(front, web_assets / "front.png")
    print(f"[建卡] 正面 = {a.lang} | 放大 {spec.get('upscale')}× {spec.get('quality_warning') or ''}")

    # 2) 静态正片 + 预览
    shutil.copy2(front, proj / "static.png")
    shutil.copy2(front, proj / "static-preview.png")

    # 3) 背面(统一 Identity)
    rp.render_back(cfg.get("backStyle", "night"), cfg).convert("RGB").save(proj / "static-back.png")

    # 4) 配置: assets + 语言 + 深度
    def webpize(name, quality=82):
        """从项目 assets/<name>.png 生成 web/assets/<name>.webp(首屏体积约 1/4)。"""
        src = out_dir / f"{name}.png"
        if not src.exists():
            src = web_assets / f"{name}.png"
        if not src.exists():
            return None
        dst = web_assets / f"{name}.webp"
        try:
            Image.open(src).save(dst, "WEBP", quality=quality, method=5)
            return f"assets/{name}.webp"
        except Exception as e:
            print(f"[建卡] {name} webp 失败({type(e).__name__}), 回退 png")
            if (web_assets / f"{name}.png").exists():
                return f"assets/{name}.png"
            return None

    layers = {}
    for n in ("background", "subject", "effects", "text"):
        u = webpize(n)
        if u:
            layers[n] = u
    assets = {"model": "assets/card.glb", "front": webpize("front", 88) or "assets/front.png"}
    assets.update(layers)
    cfg["assets"] = assets
    cfg["designLanguage"] = a.lang
    p = cfg.setdefault("parameters", {})
    if a.lang == "portrait":
        p.update({"subjectDepth": 0.10, "backgroundDepth": -0.22, "effectsDepth": 0.78, "textDepth": 0.46})
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf8")

    # 5) 查看器文件(缺什么补什么); --viewer-from 支持绝对路径或"卡目录名"
    src = None
    if a.viewer_from:
        cand = [Path(a.viewer_from), ROOT / a.viewer_from, ROOT / "card-studio" / "projects" / a.viewer_from]
        src = next((c for c in cand if (c / "web").exists()), None)
        if src is None:
            print("[建卡] 警告: 找不到查看器模板", a.viewer_from, "→ 3D 页面可能不可用")
    if src and (src / "web").exists():
        for n in ("index.html", "style.css", "app.bundle.js"):
            s = src / "web" / n
            if s.exists():
                shutil.copy2(s, proj / "web" / n)
        g = src / "web" / "assets" / "card.glb"
        if g.exists():
            shutil.copy2(g, web_assets / "card.glb")
    (proj / "web" / "card-config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf8")

    meta = {"title": cfg.get("name") or cfg.get("title") or "未命名", "edition": cfg.get("edition", ""),
            "technique": cfg.get("technique", ""), "template": a.lang,
            "designLanguage": a.lang, "note": cfg.get("note", "")}
    (proj / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf8")
    print("[建卡] 分层:", ", ".join(layers) or "(无, 走平面兜底)")
    print("[建卡] 完成 →", proj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
