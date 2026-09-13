# -*- coding: utf-8 -*-
"""
DL2 · PhotoDNA 分析可视化
========================
把 PhotoDNA 画成人能一眼看懂的图:
  左: 照片 + 叠加(红=人脸 / 黄=主体框 / 绿=可排版区(分数) / 蓝=地平线)
  右: 主色卡、明暗与色温指标、AI 判读与**程序校验结果**(✓/✗)

用法: python card-studio/dl2/analyze_sheet.py [照片目录] [--out 输出png]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import photodna  # noqa: E402

FONTS = r"C:\Windows\Fonts"
OUT = Path("dl2/analysis")


def f(size, bold=False):
    return ImageFont.truetype(FONTS + (r"\msyhbd.ttc" if bold else r"\msyh.ttc"), size)


def panel(rec, folder, width=1200):
    im = Image.open(folder / rec["file"]).convert("RGB")
    if rec["orientation"]["applied_deg"]:
        im = im.rotate(-rec["orientation"]["applied_deg"], expand=True)
    ph = 900
    scale = ph / im.height
    pw = int(im.width * scale)
    photo = im.resize((pw, ph), Image.Resampling.LANCZOS)
    side_w = width - pw
    canvas = Image.new("RGB", (width, ph), (22, 25, 33))
    canvas.paste(photo, (0, 0))
    d = ImageDraw.Draw(canvas, "RGBA")

    def bx(b, color, label=None, w=3):
        if not b:
            return
        x, y, bw, bh = b
        box = [x * scale, y * scale, (x + bw) * scale, (y + bh) * scale]
        d.rectangle(box, outline=color, width=w)
        if label:
            d.rectangle([box[0], box[1] - 22, box[0] + 8 * len(label) + 10, box[1]], fill=color)
            d.text((box[0] + 5, box[1] - 20), label, font=f(15, True), fill=(20, 22, 28))

    d.rectangle([0, 0, pw - 1, ph - 1], outline=(90, 96, 110, 160), width=1)
    for fc in rec["subject"]["faces"]:
        bx(fc, (232, 90, 90, 235), "FACE")
    bx(rec["subject"]["box"], (240, 196, 90, 220), f"SUBJECT {rec['subject']['source']}")
    for r in rec["space"]["regions"][:3]:
        bx(r["box"], (120, 220, 140, 200), f"{r['score']} {r['name']}")
    hz = rec["space"]["horizon"]
    if hz.get("y") and hz.get("conf", 0) > 0.3:
        y = hz["y"] * ph
        d.line([(0, y), (pw, y)], fill=(120, 180, 255, 210), width=2)
        d.text((8, y - 20), f"horizon {hz['y']} ({hz['conf']})", font=f(14), fill=(150, 200, 255))

    # ---- 右栏 ----
    x0, y = pw + 22, 22
    d.text((x0, y), rec["file"], font=f(22, True), fill=(238, 234, 226)); y += 34
    c = rec["color"]
    d.text((x0, y), f"主体 {rec['subject']['source']} · 占卡面 {rec['subject']['area_ratio']} · 人脸 {len(rec['subject']['faces'])}",
           font=f(16), fill=(198, 196, 190)); y += 26
    d.text((x0, y), f"方向修正 {rec['orientation']['applied_deg']}° (置信 {rec['orientation']['confidence']})",
           font=f(16), fill=(198, 196, 190)); y += 30

    d.text((x0, y), "主色", font=f(16, True), fill=(230, 226, 216)); y += 24
    sw = 54
    for i, dom in enumerate(c["dominant"][:5]):
        rgb = tuple(dom["rgb"])
        d.rectangle([x0 + i * (sw + 6), y, x0 + i * (sw + 6) + sw, y + sw], fill=rgb,
                    outline=(90, 96, 110, 200))
        d.text((x0 + i * (sw + 6), y + sw + 4), f"{dom['weight']:.2f}", font=f(12), fill=(170, 170, 165))
    y += sw + 26

    tone, mood = rec["tone"], rec["mood"]
    lines = [
        f"亮度 {tone['brightness']} · 对比 {tone['contrast']} · 暖度 {c['warmth']} · 饱和 {c['saturation']}",
        f"情绪代理 {mood['key']} (启发式)",
        f"纹理: 边缘密度 {rec['texture']['edge_density']} · 颗粒 {rec['texture']['grain_sigma']}",
        f"地平线 y={rec['space']['horizon'].get('y')} conf={rec['space']['horizon'].get('conf')}",
    ]
    for ln in lines:
        d.text((x0, y), ln, font=f(15), fill=(196, 194, 188)); y += 22
    y += 8

    d.text((x0, y), "可排版区(程序实测)", font=f(16, True), fill=(230, 226, 216)); y += 24
    for r in rec["space"]["regions"][:4]:
        col = (120, 220, 140) if r["score"] > 0.6 else (230, 200, 110) if r["score"] > 0.45 else (220, 130, 120)
        d.text((x0, y), f"{r['score']:.2f} {r['name']:<14s} 边{r['edge_density']:.3f} 脸叠{r['face_overlap']:.2f} {r['text_color']}",
               font=f(15), fill=col); y += 21
    y += 8

    ai = rec.get("ai") or {}
    if ai:
        d.text((x0, y), "AI 判读", font=f(16, True), fill=(230, 226, 216)); y += 24
        for ln in [f"场景: {ai.get('scene','')}", f"情绪: {ai.get('mood')}"]:
            d.text((x0, y), ln[:52], font=f(14), fill=(198, 200, 205)); y += 20
        risks = str(ai.get("risks", ""))
        d.text((x0, y), "风险: " + risks[:50], font=f(14), fill=(226, 178, 150)); y += 20
        if len(risks) > 50:
            d.text((x0, y), "      " + risks[50:100], font=f(14), fill=(226, 178, 150)); y += 20
        y += 6
        d.text((x0, y), "AI 建议 → 程序校验", font=f(16, True), fill=(230, 226, 216)); y += 24
        for v in (rec.get("ai_validation") or []):
            mark, col = ("✓", (120, 220, 140)) if v["accepted"] else ("✗", (232, 110, 100))
            d.text((x0, y), f"{mark} AI:{v['ai_name']}({v['ai_score']}) → {v['matched_cell']} {v['reason']}",
                   font=f(14), fill=col); y += 20
    return canvas


def main():
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "dl2/photos")
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted([p for p in folder.glob("*") if p.suffix.lower() in photodna.EXTS])
    panels = []
    for p in files:
        rec, _cached = photodna.analyze(p)
        img = panel(rec, folder)
        one = OUT / (p.stem + "-analysis.png")
        img.save(one)
        print("  ", one)
        panels.append(img)
    if panels:
        W = max(i.width for i in panels)
        gap = 18
        sheet = Image.new("RGB", (W, sum(i.height for i in panels) + gap * (len(panels) + 1)), (12, 14, 20))
        y = gap
        for i in panels:
            sheet.paste(i, (0, y))
            y += i.height + gap
        out = OUT / "sheet-all.png"
        sheet.save(out)
        print("总览:", out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
