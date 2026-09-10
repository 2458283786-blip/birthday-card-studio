# -*- coding: utf-8 -*-
import json, urllib.request
from pathlib import Path
import numpy as np
from PIL import Image

B = "http://127.0.0.1:4185"
print("/", urllib.request.urlopen(B + "/", timeout=8).status)
for t in ["celebration", "soft", "pop", "night"]:
    ok = [urllib.request.urlopen(B + f"/{t}/", timeout=8).status,
          urllib.request.urlopen(B + f"/{t}/showcase.html", timeout=8).status,
          urllib.request.urlopen(B + f"/{t}/assets/card.glb", timeout=8).status,
          urllib.request.urlopen(B + f"/{t}/pose.js", timeout=8).status]
    cfg = json.loads(urllib.request.urlopen(B + f"/{t}/card-config.json", timeout=8).read().decode("utf8"))
    print(t, ok, "backStyle=", cfg.get("backStyle"), "age=", cfg.get("age"),
          "foil=", cfg["parameters"]["foil"], "finish=", cfg["appearance"]["finish"])
    d = Path("birthday-set") / t / "assets"
    s = np.asarray(Image.open(d / "subject.png").convert("RGBA").split()[3])
    rows = np.where(s.max(axis=1) > 40)[0]
    txt = np.asarray(Image.open(d / "text.png").convert("RGBA").split()[3])
    fx = np.asarray(Image.open(d / "effects.png").convert("RGBA").split()[3])
    ln = np.asarray(Image.open(d / "lineart.png").convert("L"))
    print(f"   照片行范围 {rows[0]}~{rows[-1]} 覆盖 {(s>40).mean():.3f} | 框字 {(txt>40).mean():.4f}"
          f" | 装饰 {(fx>20).mean():.4f} | 线稿 {(ln<110).mean():.4f}")
    js = urllib.request.urlopen(B + f"/{t}/app.bundle.js", timeout=8).read().decode("utf8")
    print("   背板: 四风格=", "config.backStyle" in js, "| 视差.20=", "* depth * .20;" in js,
          "| 虹彩降饱和=", ".74 + .17 * cos" in js)
