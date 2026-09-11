# -*- coding: utf-8 -*-
"""
导出 Card Package(文档 §13 / §16 / §17)
=======================================
用法:
  python card-studio/export_package.py <项目目录> [--out 输出目录] [--card-id CARD-0001]
                                      [--theme birthday] [--template night]
产出:
  CARD-0001/
    card.json                # §14 结构
    front.png                # 正片(分层合成, 不含 Holo)
    back.png                 # 背面(读取 backStyle 重新渲染)
    preview/front.jpg        # 预览小图
    preview/back.jpg
    layers/                  # 只放实际存在的分层
    showcase/showcase.html   # 客户交付页: 无滑块/无工具栏/无 Debug
    showcase/(assets...)     # 查看器与素材
  CARD-0001.zip

Showcase 规则(§16): 卡牌是唯一视觉中心; 不出现参数滑块、工具栏、文件名、Shader 参数。
"""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

try:                       # 控制台可能是 GBK, 打印 ✅ 等符号会崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from card_schema import build_card_json, next_card_id  # noqa: E402

CLEAN_CSS = """
/* ===== 交付用 Showcase: 只留卡牌本身(无工具栏/滑块/Debug) ===== */
.masthead,.artwork-bar,.footer,.tools,.parameter-panel,.stage-note,#about,#notice{display:none !important;}
main{padding:0 !important;margin:0 !important;}
.gallery{height:100svh !important;min-height:0 !important;max-height:none !important;}
.stage{bottom:0 !important;}
body{background:var(--paper,#080c16);}
"""

CLEAN_JS = """// 交付用 Showcase: 不显示任何工作台元素, 仅在 URL 带 ?pose= 时固定姿态
const qs = new URLSearchParams(location.search);
document.documentElement.setAttribute('data-showcase', '1');
"""


def flatten_front(project):
    """按 shader 的合成顺序把分层压成一张正片(天然光线, 不含 Holo)。"""
    a = project / "assets"
    bg = Image.open(a / "background.png").convert("RGBA")
    W, H = bg.size
    out = bg.convert("RGBA")
    for name in ("subject", "effects", "text"):
        p = a / f"{name}.png"
        if p.exists():
            out.alpha_composite(Image.open(p).convert("RGBA"))
    return out.convert("RGB")


def render_back(project):
    """复用效果图渲染器里的背板绘制(与网页 backTexture 同一套设计)。"""
    import render_previews as rp
    cfg = json.loads((project / "card-config.json").read_text(encoding="utf8"))
    style = cfg.get("backStyle", "night")
    return rp.render_back(style, cfg)


def copy_showcase(project, dst):
    web = project / "web"
    if not web.exists():
        raise FileNotFoundError(f"缺少 web 目录: {web}(先跑一次生成流水线)")
    shutil.copytree(web, dst, dirs_exist_ok=True)
    css = dst / "showcase-clean.css"
    css.write_text(CLEAN_CSS, encoding="utf8")
    (dst / "showcase-clean.js").write_text(CLEAN_JS, encoding="utf8")
    src = dst / "index.html"
    html = src.read_text(encoding="utf8")
    if "showcase-clean.css" not in html:
        html = html.replace("</head>",
                            '  <link rel="stylesheet" href="./showcase-clean.css" />\n</head>')
    if "showcase-clean.js" not in html:
        html = html.replace("</body>",
                            '  <script src="./showcase-clean.js"></script>\n</body>')
    (dst / "showcase.html").write_text(html, encoding="utf8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--out", default=str(ROOT / "exports"))
    ap.add_argument("--card-id")
    ap.add_argument("--theme", default="birthday")
    ap.add_argument("--template")
    ap.add_argument("--status", default="final")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    if not (project / "card-config.json").exists():
        print("找不到 card-config.json:", project)
        return 1
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    if args.card_id:
        folder = args.card_id.strip().replace("#", "").replace(" ", "-").upper()
        if not folder.startswith("CARD-"):
            folder = "CARD-" + folder
        card_id = folder
    else:
        card_id, folder = next_card_id(out_root / ".card-seq")
    pkg = out_root / folder
    if pkg.exists():
        shutil.rmtree(pkg)
    (pkg / "preview").mkdir(parents=True, exist_ok=True)
    (pkg / "layers").mkdir(parents=True, exist_ok=True)

    # 1) 正片 / 背面
    front = flatten_front(project)
    front.save(pkg / "front.png")
    try:
        back = render_back(project)
        has_back = True
    except Exception as e:
        print("背面渲染跳过:", repr(e)[:90])
        back, has_back = None, False
    if back is not None:
        back.save(pkg / "back.png")

    # 2) 预览图
    front.resize((800, 1200), Image.Resampling.LANCZOS).save(pkg / "preview" / "front.jpg", quality=88)
    if back is not None:
        back.resize((800, 1200), Image.Resampling.LANCZOS).save(pkg / "preview" / "back.jpg", quality=88)

    # 3) 分层(只放存在的)
    layers_map = {}
    for name in ("background", "subject", "effects", "text", "lineart"):
        src = project / "assets" / f"{name}.png"
        if src.exists():
            shutil.copy2(src, pkg / "layers" / f"{name}.png")
            layers_map[name] = f"layers/{name}.png"
        else:
            layers_map[name] = None

    # 4) card.json
    card = build_card_json(project, card_id, theme=args.theme, template=args.template,
                           layers=layers_map, has_back=has_back, status=args.status)
    (pkg / "card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf8")

    # 5) 交付用 Showcase(无工具栏/滑块)
    copy_showcase(project, pkg / "showcase")

    # 5b) 自包含单文件(双击即可打开, 不依赖 Node/网络)
    single = None
    try:
        import pack_singlefile
        single = pkg / f"{folder}-single.html"
        info = pack_singlefile.build(project, single, title=card_id)
        print(f"   单文件: {single.name}  {info['bytes'] / 1e6:.1f} MB "
              f"(内联 {info['inlined_assets']} 个资源, 残留外链={info['has_external']})")
    except Exception as e:
        print("   单文件生成跳过:", repr(e)[:90])

    # 6) 打包
    zip_path = out_root / f"{folder}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pkg.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out_root))
    size_mb = zip_path.stat().st_size / 1e6

    print(f"✅ {card_id} 导出完成")
    print(f"   目录: {pkg}")
    print(f"   压缩包: {zip_path}  ({size_mb:.1f} MB)")
    print(f"   card.json: theme={card['theme']} template={card['template']} "
          f"material={card['material']['type']} holo={card['material']['holoEnabled']} "
          f"layers={sum(1 for v in layers_map.values() if v)}/5 back={has_back}")
    print(f"   交付页: {pkg / 'showcase' / 'showcase.html'}(无滑块/工具栏)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
