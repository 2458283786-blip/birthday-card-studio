# -*- coding: utf-8 -*-
"""
自包含单文件 Showcase(文档 §16/§17)
==================================
把项目 web/ 打成一个 **单个 HTML**:CSS 内联、app.bundle.js 以 base64 内联并由
Blob URL 动态 import、card-config.json 通过 fetch 垫片注入、图片与 GLB 全部转 data URI。
→ 客户双击即可打开, 也可直接丢静态托管; 不依赖 Node/网络。

用法(通常由 export_package.py 调用):
  python card-studio/pack_singlefile.py <项目目录> <输出html路径>
"""
import base64
import json
import re
import sys
from pathlib import Path

CLEAN_CSS = """
/* ===== 交付用 Showcase: 只留卡牌本身 ===== */
.masthead,.artwork-bar,.footer,.tools,.parameter-panel,.stage-note,#about,#notice{display:none !important;}
main{padding:0 !important;margin:0 !important;}
.gallery{height:100svh !important;min-height:0 !important;max-height:none !important;}
.stage{bottom:0 !important;}
"""

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".glb": "model/gltf-binary", ".gif": "image/gif"}


def data_uri(path):
    mime = MIME.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def build(project, out_html, title=None):
    web = Path(project) / "web"
    html = (web / "index.html").read_text(encoding="utf8")
    css = (web / "style.css").read_text(encoding="utf8")
    bundle_bytes = (web / "app.bundle.js").read_bytes()      # 按字节读, 保证 base64 还原逐字节一致
    cfg = json.loads((web / "card-config.json").read_text(encoding="utf8"))

    inlined = 0
    for key, rel in list((cfg.get("assets") or {}).items()):
        if not rel or str(rel).startswith("data:"):
            continue
        p = web / str(rel).lstrip("./")
        if p.exists():
            cfg["assets"][key] = data_uri(p)
            inlined += 1

    # 样式内联 + 交付态样式
    html = re.sub(r'<link[^>]*href="\./style\.css"[^>]*>',
                  "<style>\n" + css + "\n" + CLEAN_CSS + "\n</style>", html)
    # 去掉外链脚本(数据源改为内联)
    html = html.replace('<script type="module" src="./app.bundle.js"></script>', "")
    html = re.sub(r'\s*<script type="module" src="\./pose\.js"></script>', "", html)
    if title:
        html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, flags=re.S)
    html = html.replace('<a class="wordmark" href="./"', '<a class="wordmark" href="#"')

    # fetch 垫片(必须在模块脚本之前执行)
    shim = ("<script>window.__CARD_CONFIG__=" + json.dumps(cfg, ensure_ascii=False) + ";"
            "(function(){var _f=window.fetch;window.fetch=function(u,o){var s=String(u);"
            "if(s.indexOf('card-config.json')>=0){return Promise.resolve(new Response("
            "JSON.stringify(window.__CARD_CONFIG__),{status:200,headers:{'Content-Type':'application/json'}}));}"
            "return _f.apply(this,arguments);};})();</script>")
    html = html.replace("</head>", shim + "\n</head>")

    # 应用代码: base64 → Blob URL → 动态 import(避免 </script> 与转义问题)
    b64 = base64.b64encode(bundle_bytes).decode()
    loader = ("<script>window.__APP_B64__=\"" + b64 + "\";</script>\n"
              "<script type=\"module\">const _c=new TextDecoder().decode("
              "Uint8Array.from(atob(window.__APP_B64__),function(c){return c.charCodeAt(0);}));"
              "const _u=URL.createObjectURL(new Blob([_c],{type:'text/javascript'}));"
              "import(_u);</script>")
    html = html.replace("</body>", loader + "\n</body>")

    out = Path(out_html)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf8")
    return {"bytes": out.stat().st_size, "inlined_assets": inlined,
            "has_external": bool(re.search(r'(src|href)="\./(assets|app\.bundle\.js|style\.css|card-config\.json)',
                                           html))}


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else "demo-birthday"
    dest = sys.argv[2] if len(sys.argv) > 2 else "exports/single.html"
    info = build(proj, dest)
    print(f"单文件已生成: {dest}  ({info['bytes'] / 1e6:.1f} MB, 内联资源 {info['inlined_assets']} 个, "
          f"残留外链: {info['has_external']})")
