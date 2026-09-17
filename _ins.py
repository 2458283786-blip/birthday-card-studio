# -*- coding: utf-8 -*-
"""补插 V2 JS(用短锚点)"""
from pathlib import Path

P = Path("card-studio/public/index.html")
s = P.read_text(encoding="utf8")
JS = Path("_v2js.txt")
if not JS.exists():
    raise SystemExit("缺少 _v2js.txt")
js = JS.read_text(encoding="utf8")

anchor = "(async () => {                                   // 顶栏 AI 指示灯"
if "V2 工作流 ----------------" in s:
    print("已存在")
else:
    if anchor in s:
        s = s.replace(anchor, js + "\n" + anchor, 1)
        print("V2 JS: OK")
    else:
        raise SystemExit("锚点仍未命中")

if "setMode('v2')" not in s:
    s = s.replace("syncTemplate();\npoll();", "syncTemplate();\nsetMode('v2');\npoll();", 1)
    print("启动模式: OK")
P.write_text(s, encoding="utf8")
