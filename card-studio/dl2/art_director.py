# -*- coding: utf-8 -*-
"""
Art Director —— 看懂照片 + 产出 3~4 个真实卡面提案(V2 规范 §7/§4)
================================================================
分工(硬性):
  * 程序负责: PhotoDNA(确定性度量) + 规则打分 + 确定性渲染 + 文件与数据
  * AI 负责(可选): 语义判读(场景/情绪/风险/可排版区) 与"推荐语言"的语义理由
  * AI **不**直接生成带文字的最终卡; 提案一律由 design.py 程序化渲染

用法(命令行):
  python card-studio/dl2/art_director.py <照片> [--info <项目card-config.json>] [--out <目录>] [--ai]
输出:
  <out>/proposals.json   提案清单(语言/理由/规格/png 路径/分数)
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design  # noqa: E402
import photodna  # noqa: E402

# 已实现的渲染器; 规范要求的 PORTRAIT / CYBER 将在 Phase 3 补上
RENDERERS = {"editorial": True, "memory": True, "cinema": True, "portrait": True, "cyber": False}
LANG_CN = {"portrait": "PORTRAIT(肖像)", "cyber": "CYBER(赛博)", "editorial": "EDITORIAL(杂志)",
           "memory": "MEMORY(记忆)", "cinema": "CINEMA(电影)"}


def _clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def score_languages(dna):
    """按 PhotoDNA 的确定性度量给四套语言打分(V2 规范 §3 的输入特征)。"""
    br = dna["tone"]["brightness"]
    sat = dna["color"]["saturation"]
    warm = dna["color"]["warmth"]
    edge = dna["texture"]["edge_density"]
    subj = dna["subject"]
    area = subj.get("area_ratio") or 0.0
    faces_ok = bool(subj.get("faces_reliable"))
    contra = dna["tone"]["contrast"]

    scores, why = {}, {}
    # 可用留白(最大干净区) —— EDITORIAL 的关键依据
    regions = ((dna.get("space") or {}).get("regions") or [])
    neg = max([float(r.get("score") or 0) for r in regions], default=0.0)

    # CYBER: 暗调 + 色彩浓 + 细节密度高(霓虹/线框有东西可做)
    s_cyber = (_clamp((0.55 - br) * 1.8) * 0.55 + _clamp((sat - 0.30) * 1.6) * 0.30
               + _clamp((edge - 0.12) * 2.0) * 0.15)
    scores["cyber"] = s_cyber
    why["cyber"] = f"明度 {br:.2f}" + (f"、色彩浓(sat {sat:.2f})" if sat > 0.30 else "")

    # PORTRAIT: 干净背景 + 单人主体占比大 → 分层 + 艺术背景
    s_port = (_clamp((area - 0.10) * 2.2) * 0.45 + _clamp((0.22 - edge) * 3.2) * 0.35
              + (0.20 if faces_ok else 0.0))
    scores["portrait"] = s_port
    why["portrait"] = f"主体占比 {area:.2f}、背景复杂度 {edge:.2f}" + ("、人脸可靠" if faces_ok else "")

    # MEMORY: 暖 + 低饱和 + 低对比 → 胶片/纸张/手写
    s_mem = (_clamp(warm * 1.7) * 0.40 + _clamp((0.52 - sat) * 1.7) * 0.35
             + _clamp((0.26 - contra) * 1.8) * 0.25)
    scores["memory"] = s_mem
    why["memory"] = f"暖度 {warm:.2f}、饱和 {sat:.2f}、对比 {contra:.2f}"

    # CINEMA: 戏剧光比(高对比 + 偏暗) → letterbox + 电影调色 + 压字
    s_cin = _clamp((contra - 0.16) * 3.2) * 0.55 + _clamp((0.46 - br) * 1.5) * 0.45
    scores["cinema"] = s_cin
    why["cinema"] = f"对比 {contra:.2f}、明度 {br:.2f} —— 光比强, 适合电影感"

    # EDITORIAL: 大照片 + 大字留白 —— 有留白、细节足、曝光适中时最强(不要求抠图)
    s_edi = (_clamp(neg) * 0.40 + _clamp((edge - 0.08) * 1.4) * 0.35
             + _clamp(1 - abs(br - 0.50) * 2) * 0.25)
    scores["editorial"] = s_edi
    why["editorial"] = f"留白 {neg:.2f}、细节 {edge:.2f} —— 大照片 + 大字, 任何照片都能成立(不需要抠图)"

    out = []
    for lang, sc in sorted(scores.items(), key=lambda kv: -kv[1]):
        out.append({"lang": lang, "name": LANG_CN[lang], "score": round(sc, 3),
                    "why": why[lang], "renderer": RENDERERS.get(lang, False)})
    return out


def analyze(photo, use_ai=False):
    """程序度量 + (可选)AI 语义判读 → 分析结果。"""
    dna, _ = photodna.analyze(Path(photo))
    ranked = score_languages(dna)
    usable = [r for r in ranked if r["renderer"]]
    best = usable[0] if usable else ranked[0]
    out = {
        "ok": True,
        "size": dna["size"],
        "orientation": dna["orientation"],
        "tone": {"brightness": round(dna["tone"]["brightness"], 3),
                 "contrast": round(dna["tone"]["contrast"], 3)},
        "color": {"warmth": round(dna["color"]["warmth"], 3),
                  "saturation": round(dna["color"]["saturation"], 3),
                  "dominant": [{"hex": "#%02x%02x%02x" % tuple(int(c) for c in d["rgb"]),
                                "weight": round(d["weight"], 3)} for d in dna["color"]["dominant"][:4]]},
        "subject": {"area_ratio": dna["subject"].get("area_ratio"),
                    "faces_reliable": dna["subject"].get("faces_reliable"),
                    "center": dna["subject"].get("center")},
        "texture": dna["texture"], "mood": dna["mood"],
        "ai": dna.get("ai") or {},
        "ranked": ranked, "ai_offer": None,
        "recommended": best,
    }
    if use_ai:
        import ai_client as ai
        if ai.key_present():
            prompt = ("这是要做成数字收藏卡的照片。请判断并给出 JSON:\n"
                      "- scene: 一句话场景(≤40字)\n- mood: 1~3 个形容词\n"
                      "- subject: 主体是什么(≤20字)\n"
                      "- clean_areas: 适合放文字的区域 [{name:top|bottom|left|right|center, score:0~1, why:≤18字}]\n"
                      "- risks: 排版风险(≤60字)\n"
                      "- suggested_language: 从 portrait|cyber|editorial|memory 中选一个最合适的, "
                      "并给 language_why(≤40字)\n"
                      "portrait=干净背景单人照; cyber=夜景科技酷感; editorial=杂志大图留白; memory=怀旧胶片手写")
            schema = ('{"scene":"","mood":[],"subject":"","clean_areas":[{"name":"","score":0,"why":""}],'
                      '"risks":"","suggested_language":"","language_why":""}')
            text, meta = ai.ask_image(photo, prompt, schema)
            data = ai.parse_json(text) if text else None
            out["ai_offer"] = data or {"error": meta.get("error", "parse_failed")}
            out["ai_usage"] = (meta.get("usage") or {}).get("total_tokens")
        else:
            out["ai_offer"] = {"error": "no_key"}
    return out


def propose(photo, info=None, out_dir=None, n=3, langs=None, use_ai=False):
    """产出 n 个真实卡面提案(程序渲染), 返回清单。"""
    info = info or {}
    photo = Path(photo)
    out_dir = Path(out_dir or (photo.parent / "proposals"))
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis = analyze(photo, use_ai=use_ai)
    if langs:
        chosen = [{"lang": l, "why": "手动指定", "score": None} for l in langs]
    else:
        # 按推荐顺序取前 n 个"有渲染器"的语言(去重); 不足则只用现有数量
        seen, chosen = set(), []
        for r in analysis["ranked"]:
            if not r["renderer"] or r["lang"] in seen:
                continue
            seen.add(r["lang"])
            chosen.append(r)
            if len(chosen) >= n:
                break
        for r in analysis["ranked"]:                 # 仍不足则放宽: 允许重复语言的不同版式
            if len(chosen) >= n:
                break
            if r["renderer"] and sum(1 for c in chosen if c["lang"] == r["lang"]) < 2:
                chosen.append({**r, "why": (r["why"] or "") + "(换一种版式)"})
    props = []
    for i, c in enumerate(chosen):
        lang = c["lang"]
        try:
            png, spec = design.build(photo, info, lang=lang, out_dir=out_dir)
            # 缩略图(界面用): 512 宽 JPEG, 避免加载 2.5MB 大图
            thumb_name = ""
            try:
                from PIL import Image as _Im
                th_dir = Path(out_dir) / "thumbs"
                th_dir.mkdir(parents=True, exist_ok=True)
                im = _Im.open(png)
                im.thumbnail((512, 768), _Im.Resampling.LANCZOS)
                th = th_dir / (Path(png).stem + ".jpg")
                im.convert("RGB").save(th, quality=86)
                thumb_name = "thumbs/" + th.name
            except Exception as e:
                print("      缩略图失败:", type(e).__name__)
            props.append({
                "id": f"{chr(65 + i)}", "lang": lang, "name": LANG_CN[lang],
                "score": c.get("score"), "why": c.get("why"),
                "png": png.name, "thumb": thumb_name,
                "spec": {k: v for k, v in spec.items() if k != "palette"},
                "palette": {k: list(v) for k, v in (spec.get("palette") or {}).items()},
            })
        except Exception as e:
            props.append({"id": f"{chr(65 + i)}", "lang": lang, "error": f"{type(e).__name__}: {e}"})
    manifest = {"ok": True, "photo": photo.name, "analysis": analysis, "proposals": props,
                "ideal": analysis["ranked"][0] if analysis.get("ranked") else None,
                "pending": [r["lang"] for r in (analysis.get("ranked") or [])[:2] if not r["renderer"]],
                "out_dir": str(out_dir)}
    (out_dir / "proposals.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    return manifest


def find_photo(target):
    """支持传照片路径或项目目录(目录里找 source.png / _upload.*)。"""
    p = Path(target)
    if p.is_file():
        return p
    for pat in ("assets/source.png", "source.png", "_upload.*"):
        hits = sorted(p.glob(pat))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"项目里找不到原照片: {p}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo", help="照片路径, 或项目目录")
    ap.add_argument("--info", default=None, help="项目 card-config.json(V2 字段)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--langs", default=None, help="逗号分隔, 手动指定语言")
    ap.add_argument("--ai", action="store_true")
    ap.add_argument("--analyze-only", action="store_true", help="只做分析, 不渲染提案")
    a = ap.parse_args()
    photo = find_photo(a.photo)
    info = {}
    if a.info and Path(a.info).exists():
        info = json.loads(Path(a.info).read_text(encoding="utf8"))
    if a.analyze_only:
        res = analyze(photo, use_ai=a.ai)
        dest = Path(a.out) if a.out else photo.parent
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "_analyze.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf8")
        print("分析完成 →", dest / "_analyze.json")
        print("  推荐:", res["recommended"]["lang"], "|", res["recommended"]["why"])
        return
    langs = [x.strip() for x in a.langs.split(",")] if a.langs else None
    m = propose(photo, info, a.out, a.n, langs, a.ai)
    for p in m["proposals"]:
        print(f"  {p['id']} {p.get('name')} score={p.get('score')} → {p.get('png') or p.get('error')}")
    print("推荐:", m["analysis"]["recommended"]["lang"], "|", m["analysis"]["recommended"]["why"])


if __name__ == "__main__":
    main()
