# -*- coding: utf-8 -*-
"""
生成「静态卡面」PNG(验收用:关掉 Holo/3D 也能看)
=============================================
把项目的分层素材按 shader 的合成顺序压成一张静态正片, 并可选出一张展示图。
  static.png          1024×1536 纯卡面(不含 Holo)
  static-preview.png  深底展示板 + 柔和投影(产品图观感)

用法: python card-studio/make_static_card.py <项目目录> [--board]
"""
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))


def flatten(project):
    a = Path(project) / "assets"
    out = Image.open(a / "background.png").convert("RGBA")
    for name in ("subject", "effects", "text"):
        p = a / f"{name}.png"
        if p.exists():
            out.alpha_composite(Image.open(p).convert("RGBA"))
    return out.convert("RGB")


def main():
    project = Path(sys.argv[1])
    png = project / "static.png"
    flatten(project).save(png)
    print("静态卡面:", png, Image.open(png).size, f"{png.stat().st_size/1e6:.2f} MB")
    # 背面(读 backStyle, 与网页同一套设计)
    try:
        import render_previews as rp
        import json as _json
        cfg = _json.loads((project / "card-config.json").read_text(encoding="utf8"))
        back = rp.render_back(cfg.get("backStyle", "night"), cfg)
        bp = project / "static-back.png"
        back.save(bp)
        print("静态背面:", bp, back.size)
        board = rp.present(flatten(project), 0)
        out = project / "static-preview.png"
        board.save(out)
        print("展示图:", out, board.size)
        bboard = rp.present(back.convert("RGB"), 0)
        bout = project / "static-back-preview.png"
        bboard.save(bout)
        print("背面展示图:", bout, bboard.size)
    except Exception as e:
        print("背面渲染跳过:", repr(e)[:80])


if __name__ == "__main__":
    main()
