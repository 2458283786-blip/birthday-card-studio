# -*- coding: utf-8 -*-
"""
应用材质预设 + 输出多角度对照(验证 3D 视角下的光泽)
==================================================
预设: B-gloss = 哑光底 + 镜面(边框/文字) ; A-foil = 全底色烫金 ; current = 现状
用法: python card-studio/dl2/apply_material.py <项目> [--preset B-gloss] [--sweep]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import render_previews as rp  # noqa: E402

PRESETS = {
    # 哑光底 + 镜面点缀(用户选定)
    "B-gloss": {"holoEnabled": True,
                "regions": {"frame": "gloss", "text": "gloss", "subject": "matte", "background": "matte"},
                "amounts": {"frame": 0.92, "text": 0.72, "subject": 0.0, "background": 0.0}},
    "B-foil": {"holoEnabled": True,
               "regions": {"frame": "foil", "text": "foil", "subject": "matte", "background": "matte"},
               "amounts": {"frame": 0.95, "text": 0.70, "subject": 0.0, "background": 0.0}},
    "A-foil": {"holoEnabled": True,
               "regions": {"frame": "foil", "text": "foil", "subject": "foil", "background": "foil"},
               "amounts": {"frame": 0.95, "text": 0.75, "subject": 0.45, "background": 0.55}},
    "current": {"holoEnabled": True,
                "regions": {"frame": "pearl", "text": "matte", "subject": "pearl", "background": "pearl"},
                "amounts": {"frame": 0.5, "subject": 0.35, "background": 0.35}},
}

POSES = [("静止", -0.03, -0.10), ("轻倾", -0.08, -0.26),
         ("中倾", -0.14, -0.48), ("较大倾", -0.20, -0.70)]


def apply_preset(project, preset):
    """改项目里两份配置(根目录 + web)的 material 段; 返回备份路径。"""
    project = Path(project)
    for rel in ("card-config.json", "web/card-config.json"):
        p = project / rel
        if not p.exists():
            continue
        bak = p.with_suffix(".json.bak-mat")
        if not bak.exists():
            shutil.copy2(p, bak)
        cfg = json.loads(p.read_text(encoding="utf8"))
        cfg["material"] = dict(PRESETS[preset])
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf8")
    return preset


def stage_assets(project, name="_matdemo"):
    """把项目的图层复制成一个 render_previews 能读的临时模板目录。"""
    dst = rp.SET / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "assets").mkdir(parents=True)
    for n in ("background", "subject", "effects", "text", "lineart"):
        src = Path(project) / "assets" / f"{n}.png"
        if src.exists():
            shutil.copy2(src, dst / "assets" / f"{n}.png")
    shutil.copy2(Path(project) / "card-config.json", dst / "card-config.json")
    return name


def sweep(project, out_name, cols_hint=4):
    cfg = json.loads((Path(project) / "card-config.json").read_text(encoding="utf8"))
    tpl = stage_assets(project)
    panels, caps = [], []
    for label, rx, ry in POSES:
        front = rp.compose_front(tpl, cfg, rx, ry, None)
        panels.append(rp.present(Image.fromarray((front * 255).astype("uint8"), "RGB"), ry))
        caps.append(label)
    out = rp.OUT / out_name
    rp.sheet(panels, caps, f"材质 {cfg['material']['regions']} · amounts {cfg['material']['amounts']}", cols=4).save(out)
    print("  角度对照:", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--preset", default="B-gloss", choices=list(PRESETS))
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    apply_preset(a.project, a.preset)
    print(f"已应用材质预设: {a.preset} → {a.project}")
    if a.sweep:
        sweep(a.project, f"material-{a.preset}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
