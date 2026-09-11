# -*- coding: utf-8 -*-
"""
按 meta.json + 模板名生成生日收藏卡(供工坊调用)
==============================================
把"模板 → 外观/材质/层深"的唯一来源固定在 build_birthday_set.TEMPLATES,
避免服务端再抄一份配置。

用法: python card-studio/build_card_from_meta.py <项目目录> <图片> <模板名>
模板名: celebration | soft | pop | night | diorama
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_birthday_set as B  # noqa: E402

TEMPLATES = list(B.TEMPLATES.keys())


def main():
    project, image, tpl = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    if tpl not in B.TEMPLATES:
        print(f"未知模板: {tpl}; 可用: {', '.join(TEMPLATES)}")
        return 2
    t = B.TEMPLATES[tpl]
    meta = {}
    mp = project / "meta.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf8"))

    params = dict(t["params"])
    params.setdefault("textDepth", {"celebration": 0.40, "soft": 0.38, "pop": 0.45,
                                    "night": 0.55, "diorama": 0.60}[tpl])

    def m(key, default=""):
        v = meta.get(key)
        return v if v not in (None, "") else default

    cfg = {
        "title": m("title") if m("title") != "无题" else "",
        "subtitle": m("subtitle", "HAPPY BIRTHDAY"),
        "tagline": m("tagline"),
        "technique": m("technique"),
        "edition": m("edition"),
        "wish": m("wish"),
        "age": m("age"),
        "name": m("name"),
        "collection": m("collection"),
        "description": m("description"),
        "createdBy": m("createdBy"),
        "ownedBy": m("ownedBy"),
        "backStyle": tpl,
        "appearance": {"finish": t.get("finish", "pearl"), "background": t["page_bg"]},
        "material": t.get("material", {}),
        "parameters": params,
        "safeArea": {"scale": 1.0, "offset": [0.0, 0.0]},
        "_provenance": {"template": tpl, "made_by": "card-studio/build_card_from_meta.py"},
    }
    (project / "card-config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf8")
    print(f"[模板 {tpl}] 配置已写入, 开始生成五层素材…", flush=True)
    r = subprocess.run([sys.executable, "-u", str(HERE / "birthday_system.py"),
                        image, str(project), tpl], cwd=str(HERE.parent))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
