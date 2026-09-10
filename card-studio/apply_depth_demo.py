# -*- coding: utf-8 -*-
"""
把"层间纵深 + 克制全息"的改动应用到两个现有 Demo:
  A) demo-koi            (水墨锦鲤)
  B) card-studio/projects/card-mtss5ijz  (你自己那张卡)
做法: 生成前景 effects.png -> 调各层深度参数 -> 同步 patch 过的查看器文件。
不动项目架构, 不重跑 Blender(composite 模式只用到贴图与配置)。
"""
import json, shutil, subprocess, sys
from pathlib import Path

TPL = Path("RuiC-card-skill-main/assets/web-template")
PROJECTS = [
    ("demo-koi", {"subjectScale": 1.18, "subjectDepth": 0.34, "backgroundDepth": -0.30,
                  "effectsDepth": 0.62, "effectsScale": 1.04, "foil": 0.40}),
    ("card-studio/projects/card-mtss5ijz", {"subjectScale": 1.02, "subjectDepth": 0.34,
                                            "backgroundDepth": -0.28, "effectsDepth": 0.60,
                                            "effectsScale": 1.05, "foil": 0.42}),
]

for proj, params in PROJECTS:
    root = Path(proj)
    if not (root / "card-config.json").exists():
        print("skip (no config):", proj)
        continue
    # 1) 前景层
    eff = root / "assets" / "effects.png"
    subprocess.run([sys.executable, "-u", "card-studio/make_effects.py", str(eff)], check=True)
    shutil.copy2(eff, root / "web" / "assets" / "effects.png")

    # 2) 配置(根目录 + 网页目录)
    for cfg_path in (root / "card-config.json", root / "web" / "card-config.json"):
        cfg = json.loads(cfg_path.read_text(encoding="utf8"))
        cfg.setdefault("parameters", {}).update(params)
        cfg.setdefault("assets", {})["effects"] = "./assets/effects.png"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf8")

    # 3) 同步调优后的查看器
    for name in ("app.js", "app.bundle.js"):
        shutil.copy2(TPL / name, root / "web" / name)
    print("applied:", proj)

print("done")
