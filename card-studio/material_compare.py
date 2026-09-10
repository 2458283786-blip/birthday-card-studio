# -*- coding: utf-8 -*-
"""
材质系统对比图: 同一张卡 × 四种材质预设 × 两个姿态
================================================
预设:
  1 哑光印刷    全部哑光(不反光)
  2 珠光全卡    边框/主体/底纹 = 珠光
  3 烫金边框+字 边框与文字 = 金属箔, 主体/底纹 = 哑光
  4 亮面清漆    边框/文字/主体 = 亮面, 底纹 = 哑光

用法: python card-studio/material_compare.py [模板] [--out 文件名]
"""
import copy
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_previews as rp  # noqa: E402

PRESETS = [
    ("哑光印刷", {"regions": {"frame": "matte", "text": "matte", "subject": "matte", "background": "matte"},
                "amounts": {"frame": 0, "text": 0, "subject": 0, "background": 0}}),
    ("珠光全卡", {"regions": {"frame": "pearl", "text": "matte", "subject": "pearl", "background": "pearl"},
                "amounts": {"frame": 0.6, "text": 0, "subject": 0.55, "background": 0.45}}),
    ("烫金边框+烫金字", {"regions": {"frame": "foil", "text": "foil", "subject": "matte", "background": "matte"},
                    "amounts": {"frame": 0.95, "text": 0.75, "subject": 0, "background": 0}}),
    ("亮面清漆", {"regions": {"frame": "gloss", "text": "gloss", "subject": "gloss", "background": "matte"},
                "amounts": {"frame": 0.6, "text": 0.45, "subject": 0.35, "background": 0.2}}),
]
POSES = [("正面静止", -0.035, -0.15), ("大角度倾斜", -0.34, -0.86)]


def main():
    tpl = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "night"
    out = "material-compare.png"
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    cfg0 = json.loads((rp.SET / tpl / "card-config.json").read_text(encoding="utf8"))

    panels, caps = [], []
    for pose_label, rx, ry in POSES:
        for name, mat in PRESETS:
            cfg = copy.deepcopy(cfg0)
            cfg["material"] = dict(mat)
            cfg["material"]["holoEnabled"] = name != "哑光印刷"
            front = rp.compose_front(tpl, cfg, rx, ry, None)
            img = rp.present(Image.fromarray((front * 255).astype("uint8"), "RGB"), ry)
            panels.append(img)
            caps.append(f"{pose_label} · {name}")
            print("rendered:", pose_label, name, flush=True)

    rp.sheet(panels, caps, f"材质系统对比 · {tpl}", cols=4).save(rp.OUT / out)
    print("done →", rp.OUT / out)


if __name__ == "__main__":
    main()
