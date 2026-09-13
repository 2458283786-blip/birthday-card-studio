# -*- coding: utf-8 -*-
"""
DL2 · AI 语义分析(每个能力都有确定性回退)
========================================
对一张或一批照片调用 DeepSeek 视觉, 产出结构化判断并缓存到
  <照片目录>/_ai-analysis.json     (键 = 文件名)
缓存内容含模型名与 token 用量, 便于复现与成本核算。

用法:
  python card-studio/dl2/ai_analyze.py <照片或目录> [--force]
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ai_client as ai  # noqa: E402

CACHE_NAME = "_ai-analysis.json"
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

PROMPT = ("这是一张要制作成数字收藏卡的真实照片。请客观分析, 不要恭维, 不要编造。"
          "重点判断: 主体是什么/在哪、画面情绪、哪些区域适合放标题与信息。")
SCHEMA = """{
  "scene": "一句话场景描述(中文, 不超过40字)",
  "subject": {"what": "主体(不超过20字)", "position": "left|center|right + top|middle|bottom"},
  "mood": ["1-3个形容词"],
  "clean_areas": [{"name": "top|bottom|left|right|center", "score": 0.0, "why": "不超过18字"}],
  "risks": "排版风险(不超过60字)",
  "rotation_fix": "none|rotate90cw|rotate90ccw|rotate180",
  "suggested_language": "editorial|memory|cinema",
  "suggested_copy": {"title": "不超过12字", "wish": "不超过20字"}
}"""


def load_cache(folder):
    p = Path(folder) / CACHE_NAME
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf8"))
        except Exception:
            pass
    return {}


def analyze(path, force=False, cache=None):
    path = Path(path)
    folder = path.parent
    cache = cache if cache is not None else load_cache(folder)
    if not force and path.name in cache and cache[path.name].get("ok"):
        return cache[path.name], True

    t0 = time.time()
    text, meta = ai.ask_image(path, PROMPT, SCHEMA)
    data = ai.parse_json(text) if text else None
    rec = {
        "ok": bool(data),
        "file": path.name,
        "seconds": round(time.time() - t0, 1),
        "model": meta.get("model"),
        "usage": meta.get("usage"),
        "error": None if data else meta.get("error", "parse_failed"),
        "analysis": data,
    }
    if not data and text:
        rec["raw"] = text[:1500]
    cache[path.name] = rec
    (folder / CACHE_NAME).write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf8")
    return rec, False


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "dl2/photos")
    force = "--force" in sys.argv
    files = sorted([p for p in target.glob("*") if p.suffix.lower() in EXTS]) if target.is_dir() else [target]
    if not ai.key_present():
        print("未设置 DEEPSEEK_API_KEY —— 已跳过 AI 分析(程序化管线仍可运行)")
        return 0
    total = 0
    for f in files:
        rec, cached = analyze(f, force)
        tag = "缓存" if cached else f"{rec['seconds']}s"
        tok = (rec.get("usage") or {}).get("total_tokens", "-")
        print(f"  {f.name:24s} {tag:>7s}  tokens={tok}  ok={rec['ok']}")
        if rec["ok"]:
            a = rec["analysis"]
            areas = sorted(a.get("clean_areas", []), key=lambda x: -x.get("score", 0))[:2]
            top = ", ".join(f"{x['name']}:{x['score']}" for x in areas)
            print(f"      scene={a.get('scene')}")
            print(f"      mood={a.get('mood')} | 语言建议={a.get('suggested_language')} | 旋转={a.get('rotation_fix')}")
            print(f"      可排版区: {top}")
            print(f"      风险: {a.get('risks')}")
            total += tok if isinstance(tok, int) else 0
        else:
            print(f"      失败: {rec.get('error')}")
    print(f"\n合计 tokens: {total}(约 {total/1e6:.4f}M)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
