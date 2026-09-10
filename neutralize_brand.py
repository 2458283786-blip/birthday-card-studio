# -*- coding: utf-8 -*-
"""Neutralize the example-brand chrome inside the generated web/index.html."""
p = "demo-koi/web/index.html"
s = open(p, encoding="utf8").read()
repl = [
    ("白相 · White Atelier", "锦鲤 · 全息闪卡"),
    ('<span class="wordmark-cn">白相', '<span class="wordmark-cn">闪卡'),
    ("WHITE ATELIER", "HOLO CARD"),
    ("PERSONAL ART COLLECTION", "PERSONAL HOLO COLLECTION"),
    ('<p class="dialog-mark">白相</p>', '<p class="dialog-mark">锦鲤</p>'),
    ("<h2 id=\"about-title\">共生 / BOND</h2>", "<h2 id=\"about-title\">锦鲤 · 鸿运当头</h2>"),
    ("<dd>用户提供的参考作品</dd>", "<dd>程序化水墨分层创作</dd>"),
    ("<dd>个人艺术卡片习作</dd>", "<dd>全息闪卡演示习作</dd>"),
]
for a, b in repl:
    s = s.replace(a, b)
open(p, "w", encoding="utf8").write(s)
import json
cfg = json.load(open("demo-koi/web/card-config.json", encoding="utf8"))
print("config title:", cfg["title"], "| assets:", list(cfg["assets"]))
print("branding neutralized")
