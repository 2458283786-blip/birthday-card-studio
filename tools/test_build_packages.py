# -*- coding: utf-8 -*-
"""
打包器测试（含"工作台改了我不知道"的探测）
==========================================
工作台一直在演进(比如新增了 AI 选底色、进阶设置面板), card.json 会长出新字段。
打包器用的是白名单 —— 新字段会被静默丢掉, 小程序就偷偷少了一块效果。
这个测试做三件事:
  1. 拿**真实的 exports/** 跑一遍: 有没有我不认识的新字段（有就会失败, 提醒我去接住）
  2. 确认探测器真的会报（塞一个假字段进去）
  3. 卡牌底色(工作台指定的) → 明暗判断 的逻辑对不对, 以及兼容旧数据

用法: python tools/test_build_packages.py
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_mp_packages as bmp   # noqa: E402

passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}" + (f"  → {extra}" if extra else ""))


def main():
    print("\n[1] 真实的 exports/ 里有没有我不认识的新字段")
    cards = sorted(bmp.EXPORTS.glob("*/card.json"))
    check("找得到导出的卡", len(cards) > 0, f"{len(cards)} 张")
    drifted = []
    for f in cards:
        card = json.loads(f.read_text(encoding="utf8"))
        params = ((card.get("_studio") or {}).get("parameters") or {})
        appearance = ((card.get("_studio") or {}).get("appearance") or {})
        for w in bmp.known_field_warnings(card, params, appearance):
            drifted.append(f"{card.get('displayId') or f.parent.name}: {w}")
    check("没有没接住的新字段（有的话我该去接）", not drifted,
          "\n      ".join(drifted))
    if drifted:
        print("      ↑ 这些字段目前会被打包器丢掉: 如果它们影响画面, 要加进小程序")

    print("\n[2] 探测器本身要真的会报")
    fake = {"cardId": "CARD-X", "content": {},
            "newAiThing": {"chosen": "#123456"}}
    warn = bmp.known_field_warnings(fake, {"brandNewParam": 1},
                                    {"finish": "pearl", "newLook": True})
    check("顶层新字段被报出来", any("newAiThing" in w for w in warn), str(warn))
    check("parameters 新字段被报出来", any("brandNewParam" in w for w in warn))
    check("appearance 新字段被报出来", any("newLook" in w for w in warn))
    check("认识的老字段不会被误报",
          not bmp.known_field_warnings(
              {"cardId": "CARD-Y", "content": {}, "theme": "birthday"},
              {"foil": 0.5, "subjectDepth": 0.3}, {"finish": "gold", "background": "#000"}))

    print("\n[3] 卡牌底色 → 明暗判断")
    check("深色 #080c16 → dark", bmp.surface_from_color("#080c16")[0] == "dark",
          str(bmp.surface_from_color("#080c16")))
    check("浅色 #faf7f2 → light", bmp.surface_from_color("#faf7f2")[0] == "light",
          str(bmp.surface_from_color("#faf7f2")))
    check("没有 # 也能认", bmp.surface_from_color("fff8f0")[0] == "light")
    check("非法颜色 → 返回 None（调用方会退回看图取色）",
          bmp.surface_from_color("not-a-color") == (None, None))
    check("空值不报错", bmp.surface_from_color(None) == (None, None))
    check("亮度是 0~1 之间的数",
          0 <= bmp.surface_from_color("#808080")[1] <= 1,
          str(bmp.surface_from_color("#808080")))

    print("\n[4] 带进小程序的字段")
    card = {
        "cardId": "CARD-Z", "displayId": "CARD #Z", "date": "2026-09-09",
        "theme": "birthday", "template": "birthday-night",
        "title": "YOUR DAY", "content": {"message": "hi"},
        "owner": {"id": "", "name": ""}, "creator": {"id": "", "name": ""},
        "qr": {"enabled": False}, "material": {"holoEnabled": True},
        "status": "final",
        "_studio": {"parameters": {}, "appearance": {}}
    }
    data = bmp.trim_card_json(card, {"foil": 0.6, "subjectDepth": 0.4},
                              {"finish": "gold", "background": "#101820"})
    check("_studio 不会进小程序包", "_studio" not in data)
    check("渲染要用的字段都带上了",
          all(k in data for k in ("cardId", "displayId", "date", "surface",
                                  "bgColor", "depth", "finish", "foil", "holoEnabled")),
          json.dumps(list(data.keys()), ensure_ascii=False))
    check("材质参数照抄", data["finish"] == "gold" and data["foil"] == 0.6)
    check("层深度照抄", data["depth"]["subject"] == 0.4, json.dumps(data["depth"]))
    check("底色带上了", data["bgColor"] == "#101820", str(data["bgColor"]))
    check("original 材质 → 关掉全息",
          bmp.trim_card_json(card, {}, {"finish": "original"})["holoEnabled"] is False)
    check("holoEnabled=false 也照传",
          bmp.trim_card_json({"material": {"holoEnabled": False}}, {}, {})["holoEnabled"] is False)

    print("\n[5] 区域材质（照网页版 app.js 的规则）")
    base_card = {"material": {"holoEnabled": True},
                 "content": {}, "cardId": "CARD-M"}
    mats, holo = bmp.material_regions(base_card, {"foil": 0.55}, {"finish": "pearl"})
    check("默认: 边框/主体/背景 = pearl", 
          [mats[k]["type"] for k in ("frame", "subject", "background")] == ["pearl"] * 3,
          json.dumps(mats, ensure_ascii=False))
    check("默认: 文字 = matte 且材质量为 0（字体不上材质）",
          mats["text"]["type"] == "matte" and mats["text"]["amount"] == 0,
          json.dumps(mats["text"]))
    check("默认材质量 = foil 参数（文字除外）",
          mats["frame"]["amount"] == 0.55 and mats["subject"]["amount"] == 0.55,
          json.dumps({k: mats[k]["amount"] for k in mats}))
    check("holoOn 判定照抄（pearl → true）", holo is True)
    check("材质名 → 索引正确 (matte0 pearl1 foil2 gloss3)",
          mats["pearl" if False else "frame"]["index"] == 1 and mats["text"]["index"] == 0,
          json.dumps(mats, ensure_ascii=False))

    mats2, _ = bmp.material_regions(
        {"material": {"regions": {"subject": "gold"}, "amounts": {"background": 0.2}}},
        {"foil": 0.5}, {"finish": "gold"})
    check("区域材质可被覆盖（未知名字回退到默认）",
          mats2["subject"]["type"] == "pearl" and mats2["background"]["amount"] == 0.2,
          json.dumps(mats2, ensure_ascii=False))

    mats3, holo3 = bmp.material_regions(
        {"material": {"holoEnabled": False}}, {}, {"finish": "pearl"})
    check("holoEnabled=false → 所有材质量归零",
          all(m["amount"] == 0 for m in mats3.values()) and holo3 is False,
          json.dumps({k: mats3[k]["amount"] for k in mats3}))
    mats4, holo4 = bmp.material_regions({}, {}, {"finish": "original"})
    check("original 材质 → 关闭全息且材质量归零",
          holo4 is False and all(m["amount"] == 0 for m in mats4.values()))

    print("\n[6] 区域材质有偏差时要报警（别默默丢掉效果）")
    warn_ok = bmp.material_warnings(bmp.material_regions(
        {"material": {"amounts": {"text": 0.5}}}, {"foil": 0.5}, {"finish": "pearl"})[0])
    check("文字层配了材质 → 报警", any("文字层" in w for w in warn_ok), str(warn_ok))
    warn_mix = bmp.material_warnings(bmp.material_regions(
        {"material": {"regions": {"subject": "gloss"}}}, {"foil": 0.5}, {"finish": "pearl"})[0])
    check("各区域材质不一致 → 报警", any("不一致" in w for w in warn_mix), str(warn_mix))
    check("默认配置不报警（不能天天狼来了）",
          bmp.material_warnings(bmp.material_regions(
              {"material": {}}, {"foil": 0.5}, {"finish": "pearl"})[0]) == [])

    print(f"\n结果: {passed} 通过 / {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
