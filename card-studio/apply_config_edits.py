# -*- coding: utf-8 -*-
"""
保存配置修改并重出静态卡面(文档 §17: 保存当前配置 → 生成/整理 front/back/…)
=====================================================================
只重画文字层(与二维码), 不跑 Blender —— 改文案几秒钟出图。

用法: python card-studio/apply_config_edits.py <项目目录> <edits.json>
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import qr_util  # noqa: E402

EDITABLE = ["title", "subtitle", "tagline", "technique", "edition", "wish",
            "age", "name", "collection", "description", "qrUrl"]


def find_image(project):
    for pat in ("_upload.*", "assets/source.png", "source.png"):
        hits = sorted(project.glob(pat))
        if hits:
            return hits[0]
    return None


def main():
    project = Path(sys.argv[1]).resolve()
    edits = json.loads(Path(sys.argv[2]).read_text(encoding="utf8"))
    cfg_path = project / "card-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf8"))

    changed = []
    for k in EDITABLE:
        if k in edits:
            v = str(edits[k] or "").strip()
            if cfg.get(k) != v:
                changed.append(k)
            cfg[k] = v
    # 二维码: 链接变了就重算矩阵; 清空则移除
    if "qrUrl" in edits:
        if cfg.get("qrUrl"):
            qr_util.attach(cfg)
        else:
            cfg.pop("qr", None)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf8")

    # 同步回 meta.json(便于以后整张重生成)
    meta_path = project / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf8"))
            for k in EDITABLE:
                if k in edits:
                    meta[k] = cfg.get(k, "")
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf8")
        except Exception as e:
            print(f"[警告] meta.json 未同步: {type(e).__name__}")

    tpl = (cfg.get("_provenance") or {}).get("template") or cfg.get("backStyle") or "studio"
    image = find_image(project)
    print(f"[编辑] 模板={tpl} 改动字段={changed or '无'} 图片={image.name if image else '缺失'}")

    if tpl in ("celebration", "soft", "pop", "night", "diorama"):
        if not image:
            print("[错误] 找不到原始照片, 无法重画文字层")
            return 2
        r = subprocess.run([sys.executable, "-u", str(HERE / "birthday_system.py"),
                            str(image), str(project), tpl], cwd=str(ROOT))
        return r.returncode

    # 经典模板: 用 skill 的排版脚本重画 text.png
    gen = ROOT / "RuiC-card-skill-main" / "scripts" / "generate_typography.py"
    if gen.exists():
        sys.path.insert(0, str(gen.parent))
        try:
            import generate_typography
            out = generate_typography.create(str(project))
            print(f"[编辑] 经典排版已重画: {out}")
            return 0
        except Exception as e:
            print(f"[错误] 经典排版重画失败: {type(e).__name__}: {e}")
            return 3
    print("[提示] 未找到 generate_typography.py, 仅更新配置(正面文字不变)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
