# -*- coding: utf-8 -*-
import urllib.request
from pathlib import Path
import numpy as np
from PIL import Image

OUT = Path("birthday-set/previews")
for tpl in ["celebration", "soft", "pop", "night"]:
    imgs = {}
    for st in ["front", "tilt", "holo", "back"]:
        p = OUT / f"{tpl}-{st}.png"
        a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
        imgs[st] = a
        print(f"{tpl:12s} {st:5s} {a.shape[1]}x{a.shape[0]} mean={a.mean():6.1f} std={a.std():5.1f}")
    d1 = np.abs(imgs["front"] - imgs["holo"]).mean()
    d2 = np.abs(imgs["front"] - imgs["tilt"]).mean()
    d3 = np.abs(imgs["front"] - imgs["back"]).mean()
    print(f"            差异: tilt vs front={d2:5.1f}  holo vs front={d1:5.1f}  back vs front={d3:5.1f}")

for name in ["sheet-celebration.png", "sheet-soft.png", "sheet-pop.png", "sheet-night.png", "sheet-all.png"]:
    p = OUT / name
    im = Image.open(p)
    print("联图", name, im.size, f"{p.stat().st_size/1e6:.2f} MB")

B = "http://127.0.0.1:4185"
for u in ["/previews/index.html", "/previews/sheet-all.png", "/previews/celebration-holo.png"]:
    print(u, urllib.request.urlopen(B + u, timeout=10).status)
