# -*- coding: utf-8 -*-
"""给项目 card-config.json 附加二维码矩阵(qrUrl 有值才做), 并同步 web 副本。

用法: python card-studio/attach_qr.py <项目目录>
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qr_util  # noqa: E402


def main():
    proj = Path(sys.argv[1]).resolve()
    p = proj / "card-config.json"
    if not p.exists():
        print("[qr] 没有 card-config.json")
        return 1
    cfg = json.loads(p.read_text(encoding="utf8"))
    url = str(cfg.get("qrUrl") or "").strip()
    if not url:
        cfg.pop("qr", None)
        print("[qr] 未填链接 → 不生成")
    else:
        qr_util.attach(cfg)
        n = len((cfg.get("qr") or {}).get("matrix") or [])
        print(f"[qr] 已生成 {n}×{n} 矩阵: {url}")
    j = json.dumps(cfg, ensure_ascii=False, indent=2)
    p.write_text(j, encoding="utf8")
    web = proj / "web" / "card-config.json"
    if web.parent.exists():
        web.write_text(j, encoding="utf8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
