# -*- coding: utf-8 -*-
"""
Card Package 的 card.json 结构(文档 §14 / §16 / §17)
====================================================
把现有 card-config.json 适配成 card.json v1.0:
  * 内部 ID 与展示 ID 分离: internalId(不可预测) / cardId(CARD #0001)
  * optional 字段为空时一律为 null 或 "",UI 侧自然隐藏(不留占位)
  * qr / media / collection 只做字段预留
"""
import json
import os
import time
import uuid
from datetime import date
from pathlib import Path

SCHEMA_VERSION = "1.0"


def _date_str(v):
    """把 2026.09.09 / 2026-09-09 统一成 2026-09-09; 无法解析时原样返回。"""
    if not v:
        return ""
    s = str(v).strip().replace(".", "-").replace("/", "-")
    parts = [p for p in s.split("-") if p]
    if len(parts) >= 3:
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{y:04d}-{m:02d}-{d:02d}"
        except ValueError:
            return s
    return s


def _finish_to_material(finish):
    """现有 4 种质感 → 文档的 material.type。"""
    return {
        "pearl": "pearl",
        "silver": "silver-foil",
        "gold": "gold-foil",
        "original": "matte",
    }.get(str(finish or "").lower(), "pearl")


def build_card_json(project, card_id, internal_id=None, theme="birthday", template=None,
                    layers=None, has_back=True, status="final"):
    """card_id 传规范形式(CARD-0001); 展示形式自动派生为 CARD #0001。"""
    project = Path(project)
    cfg_path = project / "card-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf8")) if cfg_path.exists() else {}
    tpl = template or cfg.get("backStyle") or "night"
    params = cfg.get("parameters", {}) or {}
    finish = (cfg.get("appearance") or {}).get("finish") or "pearl"
    mat = cfg.get("material") or {}
    canonical = str(card_id).strip().replace("#", "").replace(" ", "-").upper()
    if not canonical.startswith("CARD-"):
        canonical = "CARD-" + canonical
    display = "CARD #" + canonical.split("-")[-1]

    def s(key):
        v = cfg.get(key)
        return str(v).strip() if v not in (None, "") else ""

    layers = layers or {}
    data = {
        "schemaVersion": SCHEMA_VERSION,
        "cardId": canonical,                 # 规范 ID(目录/文件/系统使用)
        "displayId": display,                # 展示 ID(CARD #0001)
        "internalId": internal_id or (uuid.uuid4().hex[:16]),   # 内部不可预测 ID
        "theme": theme,
        "template": f"birthday-{tpl}" if theme == "birthday" else tpl,
        # 正面字段属于 Artwork 内容; 没有就是 null(不虚构、不占位)
        "title": s("title") or None,
        "date": _date_str(s("technique")),
        "createdAt": date.today().isoformat(),
        "creator": {"id": "", "name": s("createdBy")},
        "owner": {"id": "", "name": s("ownedBy")},
        "content": {
            "age": s("age") or None,
            "subtitle": s("subtitle") or None,
            "message": s("wish") or None,
            "signature": s("tagline") or None,
            "name": s("name") or None,
        },
        "front": {"image": "front.png"},
        "back": {"image": "back.png"} if has_back else None,
        "layers": {
            "background": layers.get("background"),
            "subject": layers.get("subject"),
            "effects": layers.get("effects"),
            "text": layers.get("text"),
            "lineart": layers.get("lineart"),
            "frame": None,
        },
        "material": {
            # type = 主材质(取边框区域材质, 缺省回落到 finish 映射)
            "type": ((mat.get("regions") or {}).get("frame") if mat else None) or _finish_to_material(finish),
            "holoEnabled": mat.get("holoEnabled", finish != "original"),
            "foil": params.get("foil"),
            "regions": mat.get("regions") or {},
            "amounts": mat.get("amounts") or {},
        },
        "interaction": {"parallax": True, "flip": has_back, "holo": finish != "original"},
        "media": {"type": "image", "src": "front.png", "poster": "preview/front.jpg"},
        "qr": {"enabled": False, "target": "showcase", "url": None},
        "status": status,
        "cardVersion": 1,
        "metadata": {"tags": [], "note": "", "custom": {}},
        "collection": {"collectionId": None},
        # 生成侧参数(Showcase 不读, 供工作台/重制使用)
        "_studio": {
            "parameters": params,
            "safeArea": cfg.get("safeArea"),
            "appearance": cfg.get("appearance"),
            "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    }
    # 空值清理: 可选对象里空字符串 → 保留 ""(表示"未提供"), 但整块无内容时置 null
    if not data["creator"]["name"]:
        data["creator"] = {"id": "", "name": ""}
    return data


def next_card_id(seq_file):
    """CARD #0001 递增(展示用友好编号, 与内部 ID 分离)。"""
    seq_file = Path(seq_file)
    n = 0
    if seq_file.exists():
        try:
            n = int(seq_file.read_text(encoding="utf8").strip() or "0")
        except ValueError:
            n = 0
    n += 1
    seq_file.parent.mkdir(parents=True, exist_ok=True)
    seq_file.write_text(str(n), encoding="utf8")
    return f"CARD #{n:04d}", f"CARD-{n:04d}"


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "demo-birthday"
    print(json.dumps(build_card_json(p, "CARD #0001"), ensure_ascii=False, indent=2))
