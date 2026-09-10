# -*- coding: utf-8 -*-
"""抽取演示视频关键帧, 供视觉分析。"""
import cv2
from pathlib import Path

SRC = Path(r"C:\Users\Lenovo\.dsh\attachments\v1\files\e2\e26e407c11bd125c07fb74693c61e8498b353b79c9c41e32d9f6aafc153a030f\demo-after.mp4")
OUT = Path(r"D:\陈大帅\ai搞一搞\虚拟产品项目\卡片card\_video-frames")
OUT.mkdir(parents=True, exist_ok=True)

cap = cv2.VideoCapture(str(SRC))
fps = cap.get(cv2.CAP_PROP_FPS)
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
dur = n / fps if fps else 0
print(f"fps={fps:.2f} frames={n} size={w}x{h} duration={dur:.2f}s")

count = 12
for i in range(count):
    idx = int(i * (n - 1) / (count - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    if not ok:
        print("fail at", idx)
        continue
    p = OUT / f"f{i:02d}_frame{idx}.png"
    ok, buf = cv2.imencode(".png", frame)   # 中文路径下 imwrite 会静默失败, 用 imencode
    if not ok:
        print("encode fail", idx)
        continue
    with open(p, "wb") as fh:
        fh.write(buf.tobytes())
    print("saved", p.name, f"{idx/fps:.2f}s", p.stat().st_size)
cap.release()
