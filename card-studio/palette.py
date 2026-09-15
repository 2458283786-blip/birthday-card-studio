# -*- coding: utf-8 -*-
"""
取色助手(进阶设置面板用)
======================
从项目的原照片里提取候选色; 可选让 DeepSeek 选出最适合做卡牌底色的那个。
结果写到 <项目>/_palette.json(避免管道传参), 由工坊读取。

用法: python card-studio/palette.py <项目目录> [--ai]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "dl2"))

import photodna  # noqa: E402


def hx(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(int(v) for v in rgb))


def tone_of(rgb, k, desat=0.0):
    g = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    rgb = [c + (g - c) * desat for c in rgb]
    return [max(0, min(255, c * k)) for c in rgb]


def find_image(project):
    for pat in ("_upload.*", "assets/source.png", "source.png"):
        hits = sorted(project.glob(pat))
        if hits:
            return hits[0]
    return None


def main():
    project = Path(sys.argv[1]).resolve()
    use_ai = "--ai" in sys.argv
    img = find_image(project)
    out = {"ok": False}
    if not img:
        out["error"] = "找不到原照片"
    else:
        dna, _ = photodna.analyze(img)
        dom, tone, edges = dna["color"]["dominant"], dna["tone"], dna["color"]["edges"]
        cands = []
        for i, d in enumerate(dom[:3]):
            cands.append({"role": f"主色{i + 1}", "hex": hx(d["rgb"]), "raw": d["rgb"], "weight": d["weight"]})
        cn = {"top": "上", "bottom": "下", "left": "左", "right": "右"}
        for k in ("top", "bottom", "left", "right"):
            cands.append({"role": "边缘·" + cn[k], "hex": hx(edges[k]), "raw": edges[k]})
        for k, label in (("shadow", "阴影调"), ("midtone", "中间调"), ("highlight", "高光调")):
            cands.append({"role": label, "hex": hx(tone[k]), "raw": tone[k]})
        # 直接可用的"卡牌底色"候选(压暗 + 降饱和, 保证浅色字可读)
        for label, rgb, k, ds in (("推荐·边缘色暗调", edges["bottom"], 0.45, 0.22),
                                  ("推荐·主色暗调", dom[0]["rgb"], 0.45, 0.25),
                                  ("推荐·阴影暗调", tone["shadow"], 0.55, 0.15)):
            cands.append({"role": label, "hex": hx(tone_of(rgb, k, ds)), "raw": tone_of(rgb, k, ds),
                          "is_base": True})
        out = {"ok": True, "candidates": cands, "mood": dna.get("mood"),
               "warmth": dna["color"]["warmth"], "brightness": tone["brightness"]}
        if use_ai:
            import ai_client as ai
            if not ai.key_present():
                out["ai"] = {"error": "no_key"}
            else:
                listing = "\n".join(f"- {c['role']}: {c['hex']}" for c in cands)
                prompt = ("这是要印成数字收藏卡的照片。卡片版式: 照片占上部约 3/4 并渐隐融入底色, "
                          "下部深色底上排浅色文字(年龄数字/日期/编号)。\n"
                          "请从下面的候选色中选一个最适合做【卡牌底色】的:\n" + listing +
                          "\n要求: 浅色文字清晰可读(明度够低)、与照片同色系、不要纯黑、避免中等明度脏灰。")
                schema = ('{"chosen_role":"候选名","chosen_hex":"#rrggbb","why":"不超过40字",'
                          '"surround_hex":"#rrggbb(页面外围背景建议)","reject":"一句话说明你否决了什么"}')
                text, meta = ai.ask_image(img, prompt, schema)
                data = ai.parse_json(text) if text else None
                out["ai"] = data or {"error": meta.get("error", "parse_failed")}
                out["ai_usage"] = (meta.get("usage") or {}).get("total_tokens")
    (project / "_palette.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print("[取色] 完成, 候选", len(out.get("candidates", [])), "个", "| AI:", "有" if out.get("ai") else "无")
    return 0


if __name__ == "__main__":
    sys.exit(main())
