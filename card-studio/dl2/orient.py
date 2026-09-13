# -*- coding: utf-8 -*-
"""
DL2 · 方向自动校正(纯程序化, 零 AI)
==================================
手机照片常见"像素本身转了 90°/180° 但没有 EXIF 标记"。做法:
对 0/90/180/270 四个方向分别跑 Haar 人脸检测, 取"人脸数 × 单脸面积"最高者;
人脸检不出时退回"人像常识"启发式(竖向构图优先)。给置信度, 低置信度不动原图。

用法:
    from orient import detect, apply
    deg, conf, detail = detect("photo.jpg")     # deg ∈ {0,90,180,270} 表示需要顺时针补转的角度
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

_CASCADE = None


def _cascade():
    global _CASCADE
    if _CASCADE is None:
        xml = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _CASCADE = cv2.CascadeClassifier(xml)
    return _CASCADE


def _face_stats(bgr):
    """返回 (最大单脸占比, 人脸数): 占比比"数量×占比"更可靠, 因为侧倒图常出现假阳性。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    h, w = gray.shape[:2]
    faces = _cascade().detectMultiScale(gray, 1.12, 5,
                                        minSize=(int(min(h, w) * 0.06),) * 2)
    if len(faces) == 0:
        return 0.0, 0
    ratio = max(fw * fh for (_x, _y, fw, fh) in faces) / float(w * h)
    return ratio, len(faces)


def load_upright(path):
    """读取照片并应用 EXIF 方向(不做内容方向推断)。"""
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def detect(path, min_gain=1.15, min_ratio=0.015):
    """返回 (需要顺时针补转的角度, 置信度, 说明)。判据: 最大单脸占比最高者胜出;
    需要比 0° 明显更大(gain)且达到绝对下限(min_ratio), 否则保持原方向。"""
    im = load_upright(path)
    stats = {}
    for deg in (0, 90, 180, 270):
        rot = np.asarray(im.rotate(-deg, expand=True))          # rotate(-deg) = 顺时针 deg
        stats[deg] = _face_stats(cv2.cvtColor(rot, cv2.COLOR_RGB2BGR))
    best = max(stats, key=lambda d: stats[d][0])
    best_ratio, best_faces = stats[best]
    base_ratio = stats[0][0]
    if best_faces == 0 or best_ratio < min_ratio:
        return 0, 0.0, "未检出可信人脸, 保持原方向"
    gain = (best_ratio / base_ratio) if base_ratio > 1e-9 else float("inf")
    if best == 0 or gain < min_gain:
        return 0, round(min(1.0, gain / min_gain), 2), f"0°已最优(脸占比={base_ratio:.3f})"
    conf = round(min(1.0, (gain / min_gain) * 0.6 + min(1.0, best_ratio / 0.05) * 0.4), 2)
    return best, conf, f"转 {best}° 后脸占比 {best_ratio:.3f} vs 0° {base_ratio:.3f}(脸数={best_faces})"


def apply(path, out_path=None, deg=None):
    """把照片转正并保存; deg=None 时自动推断。返回 (out_path, deg, conf, detail)。"""
    if deg is None:
        deg, conf, detail = detect(path)
    else:
        conf, detail = 1.0, "指定角度"
    im = load_upright(path)
    if deg:
        im = im.rotate(-deg, expand=True)
    out = Path(out_path) if out_path else Path(path).with_name(Path(path).stem + "_upright.jpg")
    im.save(out, "JPEG", quality=95)
    return out, deg, conf, detail
