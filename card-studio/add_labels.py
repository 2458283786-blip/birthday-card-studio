# -*- coding: utf-8 -*-
"""给卡片预览页的四个工具按钮下方加中文功能说明。"""
WEBS = [
    "RuiC-card-skill-main/assets/web-template",
    "demo-koi/web",
    "card-studio/projects/card-mtss5ijz/web",
]
icon_to_label = {
    "play": "自动",
    "rotate-3d": "翻转",
    "rotate-ccw": "重置",
    "sliders-horizontal": "调整",
}
CSS_EXTRA = """
/* 卡片工坊: 工具栏按钮追加中文功能说明 */
.tools .icon-button{width:auto;height:auto;padding:3px 9px 4px;display:flex;flex-direction:column;align-items:center;gap:2px;border-radius:999px;}
.tools .icon-button .btn-label{font-size:10px;line-height:1;color:var(--ink);opacity:.72;letter-spacing:1px;pointer-events:none;}
"""

for w in WEBS:
    hp = w + "/index.html"
    s = open(hp, encoding="utf8").read()
    if "btn-label" not in s:
        for icon, label in icon_to_label.items():
            needle = f'<i data-lucide="{icon}"></i>'
            s = s.replace(needle, needle + f'<span class="btn-label">{label}</span>')
        open(hp, "w", encoding="utf8").write(s)
    sp = w + "/style.css"
    css = open(sp, encoding="utf8").read()
    if ".btn-label" not in css:
        open(sp, "a", encoding="utf8").write(CSS_EXTRA)
    print("updated:", w, "| btn-label =", s.count("btn-label") if "index" else "", flush=True)
