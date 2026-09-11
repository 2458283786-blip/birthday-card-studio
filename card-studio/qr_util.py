# -*- coding: utf-8 -*-
"""
二维码工具(文档 §11: 有就展示, 没有就不显示)
==========================================
用 vendored segno 生成模块矩阵并写进 card-config.json,
网页端与离线渲染都只按矩阵绘制 —— 不引入任何 JS 二维码依赖。

配置形态:
  "qr": {"enabled": true, "url": "https://…", "size": 29, "matrix": ["0101…", …]}
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_VENDOR = HERE / "vendor"
if _VENDOR.is_dir():
    sys.path.insert(0, str(_VENDOR))


def qr_payload(url, error="m"):
    """生成可绘制的二维码数据; 失败时返回 enabled=False(卡面自动不显示)。"""
    url = str(url or "").strip()
    if not url:
        return None
    try:
        import segno
        q = segno.make(url, error=error)
        rows = ["".join("1" if v else "0" for v in row) for row in q.matrix]
        return {"enabled": True, "url": url, "size": len(rows), "matrix": rows}
    except Exception as e:            # 依赖缺失或内容过长
        return {"enabled": False, "url": url, "error": str(e)[:100]}


def attach(cfg):
    """把 meta/UI 传入的 qrUrl 变成 cfg["qr"](就地修改并返回)。"""
    if not isinstance(cfg, dict):
        return cfg
    payload = qr_payload(cfg.get("qrUrl") or (cfg.get("qr") or {}).get("url"))
    if payload:
        cfg["qr"] = payload
    return cfg
