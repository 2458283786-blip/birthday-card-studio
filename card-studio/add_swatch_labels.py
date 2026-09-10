# -*- coding: utf-8 -*-
"""给卡面质感四个圆点(珠光/银箔/烫金/原画)加文字标注。"""
import re

WEBS = [
    "RuiC-card-skill-main/assets/web-template",
    "demo-koi/web",
    "card-studio/projects/card-mtss5ijz/web",
]
FINISHES = [("pearl", "珠光"), ("silver", "银箔"), ("gold", "烫金"), ("original", "原画")]
CSS_EXTRA = """
/* 卡片工坊: 卡面质感圆点追加文字标注 */
.finish-control .swatches .swatch{position:relative;overflow:visible;}
.swatch .swatch-name{position:absolute;top:24px;left:50%;transform:translateX(-50%);font-size:9px;line-height:1;color:var(--ink);opacity:.66;white-space:nowrap;pointer-events:none;}
.finish-control .swatches{padding-bottom:12px;}
"""

for w in WEBS:
    hp = w + "/index.html"
    s = open(hp, encoding="utf8").read()
    for key, name in FINISHES:
        pat = re.compile(r'(<button\b[^>]*data-finish="' + key + r'"[^>]*>)\s*</button\s*>', re.DOTALL)
        m = pat.search(s)
        if m and "swatch-name" not in m.group(0):
            s = pat.sub(lambda g: g.group(1) + f'<span class="swatch-name">{name}</span></button>', s, count=1)
    open(hp, "w", encoding="utf8").write(s)
    sp = w + "/style.css"
    c = open(sp, encoding="utf8").read()
    if "swatch-name" not in c:
        open(sp, "a", encoding="utf8").write(CSS_EXTRA)
    print("updated:", w, flush=True)

# 校验
for w in WEBS:
    print(w, "swatch-name count =", open(w + "/index.html", encoding="utf8").read().count("swatch-name"))
