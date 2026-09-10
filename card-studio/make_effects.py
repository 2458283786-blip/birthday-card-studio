# -*- coding: utf-8 -*-
"""
前景层生成器: 星尘 / 光点 / 星芒 / 光带
======================================
输出 1024x1536 透明 RGBA, 作为 effects.png 放在 主体之上、文字之下,
在查看器里以最大的 Z 深度做视差(前景), 制造"卡牌内部有空间"的感觉。
用法: python make_effects.py <输出路径>
"""
import math, random, sys
from PIL import Image, ImageDraw, ImageFilter

W, H = 1024, 1536
random.seed(11)
GOLD = (255, 226, 164)
WARM = (255, 245, 224)


def rot_ellipse(cx, cy, a, b, ang, n=60):
    pts = []
    for i in range(n):
        u = 2 * math.pi * i / n
        x, y = a * math.cos(u), b * math.sin(u)
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        pts.append((cx + x * c - y * s, cy + x * s + y * c))
    return pts


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "effects.png"
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def keep_clear(x, y):
        """主体正中央留一点呼吸空间, 但允许少量粒子压过主体形成纵深。"""
        d = math.hypot(x - 512, (y - 780) * 0.8)
        return d > 150 or random.random() < 0.22

    # 1) 远处细小星点(数量多、颗粒小)
    far = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(far)
    for _ in range(150):
        x, y = random.randint(0, W - 1), random.randint(0, H - 1)
        if not keep_clear(x, y):
            continue
        r = random.uniform(1.0, 3.2)
        a = random.randint(45, 110)
        fd.ellipse([x - r, y - r, x + r, y + r], fill=WARM + (a,))
    far = far.filter(ImageFilter.GaussianBlur(0.6))
    layer.alpha_composite(far)

    # 2) 近处散景光斑(大而虚, 视差最明显)
    near = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    nd = ImageDraw.Draw(near)
    for _ in range(26):
        x, y = random.randint(0, W - 1), random.randint(0, H - 1)
        if not keep_clear(x, y):
            continue
        r = random.uniform(9, 22)
        a = random.randint(22, 52)
        nd.ellipse([x - r, y - r, x + r, y + r], fill=GOLD + (a,))
    near = near.filter(ImageFilter.GaussianBlur(7))
    layer.alpha_composite(near)

    # 3) 星芒(少量, 十字光)
    for _ in range(20):
        x, y = random.randint(40, W - 40), random.randint(40, H - 40)
        if not keep_clear(x, y):
            continue
        ln = random.uniform(10, 26)
        a = random.randint(140, 225)
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        wd = random.choice([1, 1, 2])
        gd.line([(x - ln, y), (x + ln, y)], fill=GOLD + (a,), width=wd)
        gd.line([(x, y - ln * 0.8), (x, y + ln * 0.8)], fill=GOLD + (a,), width=wd)
        gd.ellipse([x - 2.4, y - 2.4, x + 2.4, y + 2.4], fill=(255, 252, 240, min(255, a + 30)))
        layer.alpha_composite(g.filter(ImageFilter.GaussianBlur(0.5)))

    # 4) 柔和光带(拉出前后方向感)
    for _ in range(7):
        cx, cy = random.randint(120, W - 120), random.randint(150, H - 150)
        a_len, b_len = random.uniform(70, 150), random.uniform(3, 7)
        ang = random.uniform(-28, 28)
        s = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(s).polygon(rot_ellipse(cx, cy, a_len, b_len, ang),
                                  fill=(255, 240, 205, random.randint(18, 34)))
        layer.alpha_composite(s.filter(ImageFilter.GaussianBlur(10)))

    layer.save(out)
    print("effects written:", out, layer.size)


if __name__ == "__main__":
    main()
