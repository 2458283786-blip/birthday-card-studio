# -*- coding: utf-8 -*-
"""
程序化「锦鲤 · 国风水墨」分层素材生成器（无 AI 参与）
=====================================================
产出三张画布 1024x1536 的分层图:
  assets/subject.png     主体(透明 RGBA, 红白锦鲤 + 墨斑 + 鳍尾)
  assets/background.png  背景(不透明, 宣纸底 + 淡墨远山/波纹/印章日轮 + 纸纹颗粒)
  assets/lineart.png     线稿(白底黑线, 与主体共用同一套几何, 严格对齐)

文字层 text.png 由 scripts/generate_typography.py 用 card-config.json 排版生成。

运行:  python make_art.py
"""
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import math, os, random

W, H = 1024, 1536
SS = 3                      # 矢量超采样倍率, 抗锯齿
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
random.seed(20260908)

INK = (26, 24, 22)
PAPER = (244, 239, 227)
CRIMSON = (196, 54, 38)
CRIMSON_HI = (233, 96, 52)
BELLY = (250, 238, 214)
SEAL = (178, 58, 42)


# ---------------------------------------------------------------- 几何工具
def rot_ellipse(cx, cy, a, b, angle_deg, n=48):
    """旋转椭圆的折线点列(用于绘制/裁剪)。"""
    pts = []
    for i in range(n):
        u = 2 * math.pi * i / n
        x, y = a * math.cos(u), b * math.sin(u)
        c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
        pts.append((cx + x * c - y * s, cy + x * s + y * c))
    return pts


def lerp(a, b, t):
    return a + (b - a) * t


def ramp(c0, c1, t):
    """两个 RGB 三元组之间的线性渐变。"""
    return tuple(int(lerp(c0[i], c1[i], t)) for i in range(3))


def smoothstep(a, b, t):
    t = max(0.0, min(1.0, (t - a) / (b - a)))
    return t * t * (3 - 2 * t)


def spine():
    """鱼脊采样: 从吻部(t=0)到尾柄(t=1), 返回 (x,y,半宽,角度deg)。"""
    X0, Y0, LX = 268.0, 692.0, 566.0
    pts = []
    N = 80
    for i in range(N + 1):
        t = i / N
        x = X0 + LX * t
        y = Y0 - 74 * math.sin(math.pi * t)          # 背部微微上弓
        # 半宽: 吻部圆钝 -> 头部鼓起 -> 颈部收 -> 胸腹最宽 -> 尾柄细
        if t < 0.10:
            hw = 66 + 34 * smoothstep(0, 0.10, t)
        elif t < 0.24:
            hw = 100 - 42 * smoothstep(0.10, 0.24, t)
        elif t < 0.48:
            hw = 58 + 92 * smoothstep(0.24, 0.48, t)
        elif t < 0.85:
            hw = 150 - 108 * smoothstep(0.48, 0.85, t)
        else:
            hw = 42 - 26 * smoothstep(0.85, 1.0, t)
        pts.append((x, y, max(hw, 2.0)))
    return pts


def spine_frame(t):
    """给定 t∈[0,1] 返回 (x, y, 切角deg)。"""
    SP = spine()
    f = t * (len(SP) - 1)
    i = int(f)
    i = min(i, len(SP) - 2)
    u = f - i
    x = lerp(SP[i][0], SP[i + 1][0], u)
    y = lerp(SP[i][1], SP[i + 1][1], u)
    ang = math.degrees(math.atan2(SP[i + 1][1] - SP[i][1], SP[i + 1][0] - SP[i][0]))
    return x, y, ang


def body_polygon():
    """主体轮廓: 沿脊线左右各偏半个宽度合成闭合多边形。"""
    SP = spine()
    left, right = [], []
    for i in range(len(SP)):
        x0, y0, hw0 = SP[i]
        x1, y1 = SP[min(i + 1, len(SP) - 1)][0], SP[min(i + 1, len(SP) - 1)][1]
        ang = math.atan2(y1 - y0, x1 - x0) + math.pi / 2
        nx, ny = math.cos(ang), math.sin(ang)
        left.append((x0 + nx * hw0, y0 + ny * hw0))
        right.append((x0 - nx * hw0, y0 - ny * hw0))
    return left + right[::-1]


def tail_fans():
    """三瓣尾鳍折线(基点在尾柄端)。"""
    BX, BY = 810.0, 618.0  # 尾柄前端(接身体后段)
    fans = []
    # 上瓣
    top = [(BX, BY)]
    for i in range(1, 15):
        u = i / 14
        top.append((lerp(BX, 962, u), BY - 90 * u - 265 * smoothstep(0.15, 1, u)))
    top.append((962, 262))
    for i in range(1, 15):
        u = i / 14
        top.append((lerp(962, BX, u), lerp(262, BY, smoothstep(0, 1, u)) - 40 * math.sin(math.pi * u)))
    fans.append(top)
    # 中瓣
    mid = [(BX, BY)]
    for i in range(1, 15):
        u = i / 14
        mid.append((lerp(BX, 1004, u), BY - 6 * u + 128 * math.sin(math.pi * u)))
    mid.append((1004, 618))
    for i in range(1, 15):
        u = i / 14
        mid.append((lerp(1004, BX, u), lerp(618, BY, u) + 26 * math.sin(math.pi * u)))
    fans.append(mid)
    # 下瓣
    low = [(BX, BY)]
    for i in range(1, 15):
        u = i / 14
        low.append((lerp(BX, 958, u), BY + 40 * u + 268 * smoothstep(0.15, 1, u)))
    low.append((958, 908))
    for i in range(1, 15):
        u = i / 14
        low.append((lerp(958, BX, u), lerp(908, BY, smoothstep(0, 1, u)) + 46 * math.sin(math.pi * u)))
    fans.append(low)
    return fans


def pectoral_fin():
    """胸鳍(腹侧, 前伸下垂)。"""
    x, y, _ = spine_frame(0.28)
    return [(x + 10, y + 118), (x - 96, y + 196), (x - 178, y + 248),
            (x - 226, y + 236), (x - 168, y + 186), (x - 92, y + 118),
            (x + 26, y + 104)]


def dorsal_fin():
    """背鳍(背缘, 低矮起伏)。"""
    pts = []
    for u in range(0, 17):
        t = 0.52 + 0.30 * u / 16
        x, y, ang = spine_frame(t)
        pts.append((x, y - 96 - 26 * math.sin(math.pi * u / 16) - 30 * smoothstep(0, 1, u / 16) * 0))
    # 改用简单的锯齿状低鳍
    out = []
    for u in range(0, 25):
        t = 0.50 + 0.32 * u / 24
        x, y, ang = spine_frame(t)
        lift = 78 if u % 2 == 0 else 52
        out.append((x, y - lift))
    return out


def whiskers():
    """两道口须(吻部向前)。"""
    hx, hy, ang = spine_frame(0.015)
    return [
        [(hx - 18, hy - 6), (hx - 70, hy - 52), (hx - 122, hy - 84), (hx - 156, hy - 96)],
        [(hx - 18, hy + 6), (hx - 62, hy + 60), (hx - 100, hy + 100), (hx - 132, hy + 126)],
    ]


def ink_blotches():
    """身上墨斑(裁剪在身体轮廓内)。"""
    blobs = []
    b1x, b1y, _ = spine_frame(0.50)
    blobs.append(rot_ellipse(b1x - 6, b1y - 118, 118, 64, -4, 36))
    b2x, b2y, _ = spine_frame(0.68)
    blobs.append(rot_ellipse(b2x - 10, b2y - 88, 86, 52, 8, 36))
    b3x, b3y, _ = spine_frame(0.36)
    blobs.append(rot_ellipse(b3x + 24, b3y - 126, 66, 40, -10, 32))
    return blobs


def head_cap():
    """头部墨顶(眼后至头顶黑斑), 裁剪在身体轮廓内。"""
    hx, hy, ang = spine_frame(0.115)
    return rot_ellipse(hx, hy, 150, 92, ang - 8, 40)


# ---------------------------------------------------------------- 主体层
def draw_subject():
    cv = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    # 1) 身体: 纵向渐变(背深红 -> 腹部米白) 裁剪身体轮廓
    body_pts = [(x * SS, y * SS) for (x, y) in body_polygon()]
    bm = Image.new("L", (W * SS, H * SS), 0)
    ImageDraw.Draw(bm).polygon(body_pts, fill=255)
    bm = bm.filter(ImageFilter.GaussianBlur(1.2))
    grad = Image.new("RGBA", (W * SS, H * SS))
    dg = ImageDraw.Draw(grad)
    y0, y1 = 400 * SS, 900 * SS
    for yy in range(0, H * SS, 2):
        t = max(0.0, min(1.0, (yy - y0) / (y1 - y0)))
        if t < 0.45:
            c = ramp(CRIMSON, CRIMSON_HI, t / 0.45)
        elif t < 0.75:
            c = ramp(CRIMSON_HI, BELLY, (t - 0.45) / 0.30)
        else:
            c = ramp(BELLY, (252, 246, 230), (t - 0.75) / 0.25)
        dg.line([(0, yy), (W * SS, yy)], fill=c + (255,))
    grad.putalpha(bm)
    cv.alpha_composite(grad)
    # 2) 尾鳍(半透明)在身体下
    for fan in tail_fans():
        fm = Image.new("L", (W * SS, H * SS), 0)
        ImageDraw.Draw(fm).polygon([(x * SS, y * SS) for (x, y) in fan], fill=255)
        fm = fm.filter(ImageFilter.GaussianBlur(1.2))
        fg = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        dfg = ImageDraw.Draw(fg)
        for yy in range(0, H * SS, 4):
            t = max(0.0, min(1.0, (yy - 200 * SS) / (960 * SS)))
            if t < 0.6:
                c = ramp(CRIMSON, CRIMSON_HI, t / 0.6)
            else:
                c = ramp(CRIMSON_HI, (250, 230, 190), (t - 0.6) / 0.4)
            dfg.line([(0, yy), (W * SS, yy)], fill=c + (255,))
        fg.putalpha(fm.point(lambda v: int(v * 0.80)))
        cv.alpha_composite(fg)
    # 3) 背鳍(半透明)
    df = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    ImageDraw.Draw(df).polygon([(x * SS, y * SS) for (x, y) in dorsal_fin()], fill=CRIMSON + (140,))
    cv.alpha_composite(df.filter(ImageFilter.GaussianBlur(1.0)))
    # 4) 胸鳍(半透明米白 + 后缘略深)
    pf = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    ImageDraw.Draw(pf).polygon([(x * SS, y * SS) for (x, y) in pectoral_fin()],
                               fill=(248, 236, 208, 225))
    cv.alpha_composite(pf.filter(ImageFilter.GaussianBlur(0.8)))
    # 5) 墨顶/墨斑(裁剪在身体轮廓内)
    ink = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    di = ImageDraw.Draw(ink)
    for blob in ink_blotches() + [head_cap()]:
        di.polygon([(x * SS, y * SS) for (x, y) in blob], fill=INK + (232,))
    ink_a = ImageChops.multiply(ink.getchannel("A"), bm)
    ink.putalpha(ink_a.point(lambda v: int(v * 0.82)))
    cv.alpha_composite(ink.filter(ImageFilter.GaussianBlur(1.4)))
    # 6) 口须
    for wh in whiskers():
        ImageDraw.Draw(cv).line([(x * SS, y * SS) for (x, y) in wh],
                                fill=INK + (215,), width=int(7 * SS), joint="curve")
    # 7) 眼 + 嘴线
    ex, ey, _ = spine_frame(0.135)
    cx, cy = ex - 8, ey - 118          # 眼位于头上部侧方
    ImageDraw.Draw(cv).ellipse([(cx - 13) * SS, (cy - 13) * SS,
                                (cx + 13) * SS, (cy + 13) * SS], fill=INK + (255,))
    ImageDraw.Draw(cv).ellipse([(cx - 5) * SS, (cy - 5) * SS,
                                (cx + 5) * SS, (cy + 5) * SS], fill=(255, 250, 240, 255))
    hx0, hy0, _ = spine_frame(0.012)
    ImageDraw.Draw(cv).arc([(hx0 - 26) * SS, (hy0 - 26) * SS, (hx0 + 26) * SS, (hy0 + 26) * SS],
                           start=220, end=340, fill=INK + (190,), width=int(4 * SS))
    # 8) 嘴角水泡
    for (bx, by, r, a) in [(150, 830, 9, 150), (135, 880, 7, 120), (122, 925, 5, 100), (170, 985, 6, 80)]:
        ImageDraw.Draw(cv).ellipse([(bx - r) * SS, (by - r) * SS, (bx + r) * SS, (by + r) * SS],
                                   outline=(140, 160, 168, 150), width=int(2.4 * SS))
    # 缩小回真实分辨率
    return cv.resize((W, H), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------- 线稿层
def draw_lineart():
    """白底黑线: 与主体共用几何, 一笔一笔描出轮廓。"""
    cv = Image.new("RGBA", (W * SS, H * SS), (255, 255, 255, 255))
    d = ImageDraw.Draw(cv)
    d.polygon([(x * SS, y * SS) for (x, y) in body_polygon()],
              outline=(24, 22, 20, 255), width=int(5 * SS))
    for fan in tail_fans():
        d.polygon([(x * SS, y * SS) for (x, y) in fan],
                  outline=(30, 28, 26, 255), width=int(4 * SS))
    d.polygon([(x * SS, y * SS) for (x, y) in pectoral_fin()],
              outline=(30, 28, 26, 255), width=int(4 * SS))
    for i in range(0, len(dorsal_fin()), 2):
        p = dorsal_fin()[i:i + 2]
        if len(p) == 2:
            d.line([(p[0][0] * SS, p[0][1] * SS), (p[1][0] * SS, p[1][1] * SS)],
                   fill=(30, 28, 26, 255), width=int(4 * SS))
    for blob in ink_blotches() + [head_cap()]:
        d.polygon([(x * SS, y * SS) for (x, y) in blob],
                  outline=(34, 32, 30, 160), width=int(2 * SS))
    for wh in whiskers():
        d.line([(x * SS, y * SS) for (x, y) in wh], fill=(24, 22, 20, 255),
               width=int(6 * SS), joint="curve")
    # 鳍内纹路
    hx, hy, _ = spine_frame(0.115)
    ex, ey = hx - 8, hy - 118
    d.ellipse([(ex - 11) * SS, (ey - 11) * SS, (ex + 11) * SS, (ey + 11) * SS],
              fill=(24, 22, 20, 255))
    tail_base = (810.0, 618.0)
    for (tx, ty) in [(962, 262), (1004, 618), (958, 908)]:
        for k in range(1, 5):
            u = k / 5
            d.line([(tail_base[0] * SS, tail_base[1] * SS),
                    ((tail_base[0] + (tx - tail_base[0]) * u) * SS,
                     (tail_base[1] + (ty - tail_base[1]) * u + 22 * math.sin(math.pi * u)) * SS)],
                   fill=(40, 38, 36, 110), width=int(2 * SS))
    px, py, _ = spine_frame(0.28)
    for k in (0.3, 0.55, 0.8):
        d.line([((px + 10) * SS, (py + 118) * SS),
                ((px - 178 * k) * SS, (py + 118 + 120 * k) * SS)],
               fill=(40, 38, 36, 100), width=int(2 * SS))
    return cv.resize((W, H), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------- 背景层
def draw_background():
    bg = Image.new("RGBA", (W, H), PAPER + (255,))
    d = ImageDraw.Draw(bg)
    # 1) 淡墨远山(左/右两团)
    for (cx, cy, rx, ry, a) in [(180, 1120, 520, 260, 42), (900, 1160, 600, 300, 34)]:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                                      fill=(120, 116, 106, a))
        layer = layer.filter(ImageFilter.GaussianBlur(60))
        bg.alpha_composite(layer)
    # 2) 脊线远山剪影
    for (cx, cy, rx, ry, a) in [(300, 1050, 620, 210, 30), (760, 1010, 560, 200, 26)]:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                                      fill=(104, 100, 92, a))
        layer = layer.filter(ImageFilter.GaussianBlur(70))
        bg.alpha_composite(layer)
    # 3) 印章红日轮(淡, 衬在主体后方)
    sun = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sun)
    ds.ellipse([512 - 216, 618 - 216, 512 + 216, 618 + 216], fill=SEAL + (52,))
    ds.ellipse([512 - 200, 618 - 200, 512 + 200, 618 + 200], outline=SEAL + (70,), width=5)
    sun = sun.filter(ImageFilter.GaussianBlur(2))
    bg.alpha_composite(sun)
    # 4) 顶部两缕云气
    for (cx, cy, rx, ry, a) in [(300, 470, 300, 60, 30), (820, 420, 280, 54, 26),
                                (560, 330, 240, 44, 22)]:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                                      fill=(214, 208, 194, a))
        layer = layer.filter(ImageFilter.GaussianBlur(36))
        bg.alpha_composite(layer)
    # 5) 水波(主体下方)
    for (rx, ry, a, wd) in [(340, 92, 150, 4), (400, 106, 110, 4), (470, 124, 76, 4),
                            (545, 142, 52, 3)]:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dl = ImageDraw.Draw(layer)
        dl.ellipse([560 - rx, 1140 - ry, 560 + rx, 1140 + ry],
                   outline=(96, 92, 84, a), width=wd)
        layer = layer.filter(ImageFilter.GaussianBlur(1.2))
        bg.alpha_composite(layer)
    # 6) 远岸一线 + 零落墨点
    dl = ImageDraw.Draw(bg)
    dl.line([(60, 1250), (460, 1252), (620, 1246), (964, 1250)], fill=(110, 106, 98, 110), width=3)
    dl.line([(60, 1250), (460, 1252), (620, 1246), (964, 1250)], fill=(110, 106, 98, 110), width=3)
    for (x, y, r, a) in [(150, 1210, 5, 90), (870, 1195, 4, 80), (920, 1235, 3, 70),
                         (96, 1230, 4, 85), (600, 1170, 3, 60)]:
        dl.ellipse([x - r, y - r, x + r, y + r], fill=(104, 100, 92, a))
    # 7) 宣纸颗粒 + 轻微暗角
    for _ in range(2600):
        x, y = random.randint(0, W - 1), random.randint(0, H - 1)
        v = random.randint(0, 18)
        c = 255 - v
        bg.putpixel((x, y), (c, c - 2 if c > 2 else 0, c - 5 if c > 5 else 0, 255))
    # 8) 整体留白提亮, 让主体区可读
    bright = Image.new("RGBA", (W, H), (252, 249, 242, 255))
    bg = Image.blend(bg, bright, 0.16)
    return bg.convert("RGB").convert("RGBA")


# ---------------------------------------------------------------- 主流程
def main():
    os.makedirs(OUT, exist_ok=True)
    bg = draw_background()
    bg.save(os.path.join(OUT, "background.png"))
    sub = draw_subject()
    sub.save(os.path.join(OUT, "subject.png"))
    ln = draw_lineart()
    ln.convert("RGB").save(os.path.join(OUT, "lineart.png"))
    # 拼一张自检预览
    chk = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(chk)
    for yy in range(0, H, 32):
        for xx in range(0, W, 32):
            d.rectangle([xx, yy, xx + 31, yy + 31],
                        fill=(196, 196, 196, 255) if (xx // 32 + yy // 32) % 2 else (222, 222, 222, 255))
    chk.alpha_composite(sub)
    prev = Image.new("RGBA", (W * 2, H), (255, 255, 255, 255))
    prev.paste(bg, (0, 0))
    prev.paste(chk, (W, 0))
    prev.paste(ln, (0, 0)).paste(ln, (W, 0)) if False else None
    prev.save(os.path.join(OUT, "_preview.png"))
    print("assets written:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
