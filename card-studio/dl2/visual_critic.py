# -*- coding: utf-8 -*-
"""
AI Visual Critic(V2 规范 §8 / §15)
================================
分两层:
  * 程序硬指标(确定性): 文字对比度、文字覆盖率、文字贴边距离、有无文字层
  * AI 评审(可选): 可读性 / 是否压住主体 / 层次 / 品牌一致性 + 1~3 条可执行建议 + 各维度评分
分工原则不变: 程序量出来的才是事实; AI 的判断标注为"AI 认为"。

用法: python card-studio/dl2/visual_critic.py <项目目录> [--ai]
输出: <项目>/_critic.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _lum(rgb):
    c = np.asarray(rgb, np.float32) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2])


def find(project, names):
    for n in names:
        for base in ("assets", "web/assets"):
            p = Path(project) / base / n
            if p.exists():
                return p
    return None


def program_checks(project):
    front_p = find(project, ["front.png", "static.png"])
    text_p = find(project, ["text.png"])
    out = {"ok": False, "checks": []}
    if not front_p:
        out["error"] = "找不到正面图"
        return out
    front = Image.open(front_p).convert("RGB")
    a = np.asarray(front, np.float32)
    report = []

    if not text_p:
        report.append({"name": "文字层", "pass": None, "detail": "无独立文字层(该语言未输出分层), 跳过对比度检查"})
        out.update({"ok": True, "checks": report, "front": str(front_p)})
        return out

    tl = Image.open(text_p).convert("RGBA")
    t = np.asarray(tl, np.float32)
    mask = t[..., 3] > 40
    n = int(mask.sum())
    report.append({"name": "文字层", "pass": bool(n > 50), "detail": f"文字像素 {n}"})
    if n > 50:
        lum = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
        text_lum = float(lum[mask].mean())
        # 背景 = 文字掩膜膨胀后减去文字本身
        m = Image.fromarray((mask * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(9))
        ring = (np.asarray(m) > 40) & (~mask)
        bg_lum = float(lum[ring].mean()) if ring.sum() > 50 else float(lum.mean())
        L1, L2 = (_lum([text_lum * 255] * 3), _lum([bg_lum * 255] * 3))
        ratio = (max(L1, L2) + 0.05) / (min(L1, L2) + 0.05)
        report.append({"name": "文字对比度", "pass": bool(ratio >= 3.0), "value": round(ratio, 2),
                       "detail": f"文字/背景亮度 {text_lum:.0f} / {bg_lum:.0f} → 对比 {ratio:.2f}:1"
                                 + ("(≥3 可用, ≥4.5 更稳)" if ratio < 4.5 else "(充足)")})
        # 文字覆盖率 + 贴边
        cov = n / float(mask.size)
        report.append({"name": "文字覆盖率", "pass": bool(0.01 <= cov <= 0.22), "value": round(cov * 100, 2),
                       "detail": f"占画面 {cov * 100:.2f}%"})
        ys, xs = np.where(mask)
        h, w = mask.shape
        edge = min(xs.min(), ys.min(), w - 1 - xs.max(), h - 1 - ys.max())
        report.append({"name": "文字贴边", "pass": bool(edge >= int(w * 0.02)), "value": int(edge),
                       "detail": f"距最近边缘 {edge}px" + ("" if edge >= w * 0.02 else "(过近, 建议留白)")})
    out.update({"ok": True, "checks": report, "front": str(front_p)})
    return out


def ai_review(project, front_path):
    import ai_client as ai
    if not ai.key_present():
        return {"error": "no_key"}
    prompt = ("这是一张「数字收藏卡」的正面成图。请以设计评审的身份检查并给出 JSON:\n"
              "- scores: {readability, composition, depth, brand} 各 0~10\n"
              "- issues: 1~3 条具体问题(≤24 字/条)\n"
              "- fixes: 1~3 条可执行修改建议(≤24 字/条)\n"
              "- verdict: 一句话总评(≤40 字)\n"
              "判断标准: 文字是否清晰可读、是否压住人脸或主体、是否有层次与留白、"
              "是否像一件收藏品而不是网页特效。不确定的不要编。")
    schema = ('{"scores":{"readability":0,"composition":0,"depth":0,"brand":0},'
              '"issues":[],"fixes":[],"verdict":""}')
    text, meta = ai.ask_image(front_path, prompt, schema)
    data = ai.parse_json(text) if text else None
    if not data:
        return {"error": meta.get("error", "parse_failed")}
    data["usage"] = (meta.get("usage") or {}).get("total_tokens")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--ai", action="store_true")
    a = ap.parse_args()
    proj = Path(a.project).resolve()
    rep = program_checks(proj)
    if a.ai and rep.get("front"):
        rep["ai"] = ai_review(proj, rep["front"])
    (proj / "_critic.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf8")
    print("[评审] 程序检查", len(rep.get("checks", [])), "项 | AI:",
          "有" if rep.get("ai") and not rep["ai"].get("error") else (rep.get("ai", {}).get("error", "无")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
