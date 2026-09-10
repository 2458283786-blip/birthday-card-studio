# -*- coding: utf-8 -*-
"""
一键刷新生日收藏卡
==================
改了 card-config.json(标题/年龄/日期/编号/祝福/归属)或换了照片后, 跑这一条即可:
  python card-studio/refresh_birthday.py [新照片路径]

做四件事:
  1. 用根目录 card-config.json 的文案重新生成六层素材
  2. 同步素材到 web/assets
  3. 把配置同步到 web/card-config.json(补上 age/createdBy/ownedBy/wish 等字段)
  4. 重新应用查看器定制(背板 / 四态 / 深色主题)
"""
import json, shutil, subprocess, sys
from pathlib import Path

PROJ = Path("demo-birthday")
ROOT_CFG = PROJ / "card-config.json"
WEB = PROJ / "web"
STUDIO = Path(__file__).resolve().parent
LAYERS = ["subject", "background", "lineart", "text", "effects"]


def main():
    photo = sys.argv[1] if len(sys.argv) > 1 else str(PROJ / "assets" / "source.png")
    print("使用照片:", photo)

    subprocess.run([sys.executable, "-u", str(STUDIO / "make_birthday_art.py"), photo, str(PROJ)], check=True)

    for n in LAYERS:
        shutil.copy2(PROJ / "assets" / f"{n}.png", WEB / "assets" / f"{n}.png")
    print("素材已同步 → web/assets")

    cfg = json.loads(ROOT_CFG.read_text(encoding="utf8"))
    web_cfg_path = WEB / "card-config.json"
    web_cfg = json.loads(web_cfg_path.read_text(encoding="utf8")) if web_cfg_path.exists() else {}
    merged = dict(cfg)
    assets = dict(web_cfg.get("assets", {}))
    assets.update({k: f"./assets/{k}.png" for k in LAYERS})
    assets["model"] = "./assets/card.glb"
    merged["assets"] = assets
    web_cfg_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf8")
    print("配置已同步 → web/card-config.json (age=%r, wish=%r)" % (cfg.get("age"), cfg.get("wish")))

    subprocess.run([sys.executable, "-u", str(STUDIO / "patch_birthday_viewer.py")], check=True)
    print("完成 → http://127.0.0.1:4180/  (四态页 /showcase.html)")


if __name__ == "__main__":
    main()
