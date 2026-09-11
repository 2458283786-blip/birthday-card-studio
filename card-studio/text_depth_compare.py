# -*- coding: utf-8 -*-
"""验证文字层景深: 同一张卡在倾斜姿态下, textDepth=0 与 textDepth=0.55 的差别。"""
import copy
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "card-studio"))
import render_previews as rp  # noqa: E402

cfg0 = json.loads((rp.SET / "night" / "card-config.json").read_text(encoding="utf8"))
panels, caps = [], []
for td, label in [(0.0, "textDepth = 0(文字固定最前)"), (0.55, "textDepth = 0.55(文字自带景深)")]:
    cfg = copy.deepcopy(cfg0)
    cfg.setdefault("parameters", {})["textDepth"] = td
    cfg["parameters"]["foil"] = 0.55          # 打开一点点光泽, 便于观察层次
    cfg["material"] = {"holoEnabled": True,
                       "regions": {"frame": "pearl", "text": "matte", "subject": "pearl", "background": "pearl"},
                       "amounts": {"frame": 0.5, "subject": 0.35, "background": 0.35}}
    front = rp.compose_front("night", cfg, -0.30, -0.70, None)
    panels.append(rp.present(Image.fromarray((front * 255).astype("uint8"), "RGB"), -0.70))
    caps.append(label)
    print("rendered:", label, flush=True)

rp.sheet(panels, caps, "文字层景深对比(大角度倾斜)", cols=2).save(rp.OUT / "text-depth-compare.png")
print("done →", rp.OUT / "text-depth-compare.png")
