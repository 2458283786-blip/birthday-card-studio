# -*- coding: utf-8 -*-
"""
小程序页面示意图生成器(不是小程序代码, 只是静态示意图)
=====================================================
白底简约版, 用 exports/ 里的真实 Card Package 合成 4 张图:
  01-collection.png        收藏页(白底, 一行两个)
  02-card-front.png        卡牌页: 静置浮动 / 拖动 / 陀螺仪 / 翻面 / 字段
  03-card-back.png         背面(字段有无对比)
  04-layers-and-states.png 卡内分层 + 缺东西时的降级规则

静态图片无法表现浮动/转动/虹彩, 图上会标注"示意图"。
用法: python mockups/make_mockups.py
"""
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "exports"
OUT = ROOT / "mockups"

# ---------- 设计令牌(简约白) ----------
TOK = {
    "sheet_bg":  (237, 239, 243),      # 示意图画布
    "screen_bg": (255, 255, 255),      # 小程序页面: 白
    "bezel":     (22, 24, 29),
    "paper":     (247, 247, 248),      # 卡片页轻微托底
    "ink":       (22, 24, 29),
    "ink_muted": (108, 114, 126),
    "ink_faint": (156, 162, 174),
    "hair":      (228, 230, 235),
    "gold":      (176, 138, 62),
    "gold_soft": (215, 178, 100),
    "panel":     (255, 255, 255),
}

SW, SH = 375, 812
BEZEL = 13
RAD = 26

FONTS = {
    "cjk":   "C:/Windows/Fonts/Deng.ttf",
    "cjk_l": "C:/Windows/Fonts/Dengl.ttf",
    "cjk_b": "C:/Windows/Fonts/Dengb.ttf",
    "latin": next((f"C:/Windows/Fonts/{n}" for n in
                   ("georgia.ttf", "times.ttf", "arial.ttf")
                   if os.path.exists(f"C:/Windows/Fonts/{n}")),
                  "C:/Windows/Fonts/Deng.ttf"),
}
_cache = {}


def F(kind, size):
    size = int(round(size))
    key = (kind, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(FONTS[kind], size)
    return _cache[key]


def ls_text(d, x, y, s, font, fill, ls=0.0, align="left"):
    if not s:
        return 0
    widths = [d.textlength(ch, font=font) for ch in s]
    total = sum(widths) + ls * (len(s) - 1)
    if align == "center":
        x -= total / 2
    elif align == "right":
        x -= total
    cx = x
    for ch, w in zip(s, widths):
        d.text((cx, y), ch, font=font, fill=fill)
        cx += w + ls
    return total


def soft_shadow(base, box, radius, blur=14, alpha=70, dy=8):
    w, h = box[2] - box[0], box[3] - box[1]
    pad = blur * 3
    m = Image.new("L", (w + pad * 2, h + pad * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [pad, pad + dy, pad + w, pad + h + dy], radius, fill=alpha)
    m = m.filter(ImageFilter.GaussianBlur(blur))
    base.paste(Image.new("RGB", m.size, (0, 0, 0)), (box[0] - pad, box[1] - pad), m)


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius, fill=255)
    return m


def paste_rounded(base, img, xy, size, radius=10):
    base.paste(img.resize(size, Image.LANCZOS), xy, rounded_mask(size, radius))


def paste_card(base, img, xy, size, radius=11, shadow=True):
    if shadow:
        soft_shadow(base, (xy[0], xy[1], xy[0] + size[0], xy[1] + size[1]),
                    radius, blur=14, alpha=62, dy=9)
    paste_rounded(base, img, xy, size, radius)


def paste_rot_card(base, img, size, center, angle=0.0, alpha=255, radius=13,
                   shadow=True):
    """贴一张可旋转、可半透明的卡(用来表现"静置轻微浮动"的残影)。"""
    card = img.resize(size, Image.LANCZOS).convert("RGBA")
    card.putalpha(rounded_mask(size, radius))
    if angle:
        card = card.rotate(angle, resample=Image.BICUBIC, expand=True)
    if alpha < 255:
        card.putalpha(card.getchannel("A").point(lambda v: int(v * alpha / 255)))
    w, h = card.size
    xy = (int(center[0] - w / 2), int(center[1] - h / 2))
    if shadow:
        soft_shadow(base, (xy[0], xy[1], xy[0] + w, xy[1] + h), radius,
                    blur=17, alpha=52, dy=11)
    base.paste(card, xy, card)


def chip(d, x, y, n, r=11):
    d.ellipse([x - r, y - r, x + r, y + r], fill=TOK["gold_soft"])
    d.text((x, y - 1), str(n), font=F("latin", 13), fill=(38, 28, 8), anchor="mm")


def status_bar(d, ink):
    d.text((26, 15), "9:41", font=F("latin", 13), fill=ink)
    bx = SW - 26
    for i, h in enumerate((4, 6, 8, 10)):
        d.rounded_rectangle([bx - 62 + i * 5, 25 - h, bx - 59 + i * 5, 25], 1, fill=ink)
    for r in (9, 6, 3):
        d.arc([bx - 34 - r, 29 - r * 2, bx - 34 + r, 29], 215, 325, fill=ink, width=2)
    d.rounded_rectangle([bx - 24, 14, bx, 26], 4, outline=ink, width=1)
    d.rounded_rectangle([bx - 22, 16, bx - 6, 24], 2, fill=ink)
    d.rounded_rectangle([bx + 1, 18, bx + 3, 22], 1, fill=ink)


def icon_button(d, x, y, kind):
    s = 34
    d.rounded_rectangle([x, y, x + s, y + s], 11, fill=(244, 245, 247),
                        outline=TOK["hair"], width=1)
    cx, cy = x + s / 2, y + s / 2
    ink = (58, 62, 72)
    if kind == "save":
        d.line([cx, cy - 7, cx, cy + 3], fill=ink, width=2)
        d.line([cx - 4, cy - 1, cx, cy + 3, cx + 4, cy - 1], fill=ink, width=2)
        d.line([cx - 6, cy + 7, cx + 6, cy + 7], fill=ink, width=2)
    else:
        for dx, dy in ((-5, -4), (5, -1), (-5, 3)):
            d.ellipse([cx + dx - 2, cy + dy - 2, cx + dx + 2, cy + dy + 2], fill=ink)
        d.line([cx - 4, cy - 3, cx + 4, cy - 1], fill=ink, width=1)
        d.line([cx - 4, cy + 3, cx + 4, cy - 1], fill=ink, width=1)


def back_chevron(d, x, y, ink=(52, 56, 66)):
    d.line([x + 8, y, x, y + 9, x + 8, y + 18], fill=ink, width=2)


def art(pkg, name):
    return Image.open(EXPORTS / pkg / "preview" / f"{name}.jpg").convert("RGB")


def card_fields(pkg):
    return json.loads((EXPORTS / pkg / "card.json").read_text(encoding="utf8"))


# ---------- 屏幕: 收藏页(白) ----------
def screen_collection():
    sc = Image.new("RGB", (SW, SH), TOK["screen_bg"])
    d = ImageDraw.Draw(sc)
    status_bar(d, TOK["ink"])
    ls_text(d, 24, 62, "COLLECTION", F("latin", 13), TOK["ink"], 2.4)
    ls_text(d, SW - 24, 66, "2 CARDS", F("latin", 10), TOK["ink_faint"], 1.6, "right")
    d.line([24, 90, SW - 24, 90], fill=TOK["hair"], width=1)

    cards = ["CARD-0001", "CARD-QR01"]
    tw, th, ty = 150, 225, 118
    for i, pkg in enumerate(cards):
        x = 24 + i * 177
        paste_card(sc, art(pkg, "front"), (x, ty), (tw, th), radius=10)
        ls_text(d, x, ty + th + 16, pkg.replace("-", " #"), F("latin", 11),
                TOK["ink"], 1.4)
        ls_text(d, x, ty + th + 34, card_fields(pkg)["date"].replace("-", "."),
                F("latin", 10), TOK["ink_faint"], 1.2)
    ls_text(d, SW / 2, 440, "", F("cjk_l", 11), TOK["ink_faint"], 0.8, "center")
    return sc


# ---------- 屏幕: 卡牌页(白, 静置浮动) ----------
def screen_card(card_img, fields, side="front"):
    sc = Image.new("RGB", (SW, SH), TOK["screen_bg"])
    d = ImageDraw.Draw(sc)
    # 轻微托底, 让卡片"浮"在白纸上
    glow = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(glow).ellipse([-40, 150, SW + 40, 690], fill=34)
    sc.paste(Image.new("RGB", (SW, SH), (238, 240, 244)), (0, 0),
             glow.filter(ImageFilter.GaussianBlur(80)))
    d = ImageDraw.Draw(sc)

    status_bar(d, TOK["ink"])
    back_chevron(d, 24, 60)
    icon_button(d, SW - 88, 52, "save")
    icon_button(d, SW - 48, 52, "share")

    cw = 327
    ch = int(cw * 1.5)
    cx, cy = (SW - cw) // 2, 150
    center = (cx + cw / 2, cy + ch / 2)
    # 静置浮动: 两层淡残影 + 主体(静态图用"叠影"表达轻微浮动)
    paste_rot_card(sc, card_img, (cw, ch), (center[0] + 6, center[1] - 4),
                   angle=1.5, alpha=26, radius=13)
    paste_rot_card(sc, card_img, (cw, ch), (center[0] - 5, center[1] + 3),
                   angle=-1.2, alpha=44, radius=13)
    paste_rot_card(sc, card_img, (cw, ch), center, angle=0.0, radius=13)

    if side == "front":
        y = cy + ch + 26
        ls_text(d, SW / 2, y, fields["displayId"], F("latin", 11), TOK["ink"],
                1.8, "center")
        ls_text(d, SW / 2, y + 20, fields["date"].replace("-", "."), F("latin", 10.5),
                TOK["ink_muted"], 1.4, "center")
        msg = (fields["content"].get("message") or "").strip()
        if msg:
            ls_text(d, SW / 2, y + 46, msg, F("latin", 10), TOK["ink_faint"],
                    1.1, "center")
        ls_text(d, SW / 2, SH - 46, "拖动旋转 · 点击翻面", F("cjk_l", 11),
                TOK["ink_faint"], 0.8, "center")
        ls_text(d, SW / 2, SH - 28, "首次进入提示一次，随后自动淡出", F("cjk_l", 10),
                (196, 200, 208), 0.6, "center")
    else:
        ls_text(d, SW / 2, SH - 46, "点击卡片翻回正面", F("cjk_l", 11),
                TOK["ink_faint"], 0.8, "center")
    return sc


# ---------- 组图 ----------
def sheet(w, h, title, subtitle):
    im = Image.new("RGB", (w, h), TOK["sheet_bg"])
    d = ImageDraw.Draw(im)
    d.text((56, 40), title, font=F("cjk_b", 26), fill=TOK["ink"])
    d.text((56, 80), subtitle, font=F("cjk_l", 12.5), fill=TOK["ink_muted"])
    ls_text(d, w - 56, 44, "示意图 · 非最终效果", F("cjk_l", 11.5),
            TOK["ink_faint"], 0.4, "right")
    return im


def phone(content, xy):
    w, h = SW + BEZEL * 2, SH + BEZEL * 2
    ph = Image.new("RGB", (w, h), TOK["bezel"])
    ImageDraw.Draw(ph).rounded_rectangle([0, 0, w - 1, h - 1], RAD + 7,
                                         outline=(58, 61, 70), width=2)
    ph.paste(content, (BEZEL, BEZEL), rounded_mask((SW, SH), RAD))
    return ph, xy


def notes(im, x, y, items, width=560):
    d = ImageDraw.Draw(im)
    cy = y
    for n, head, body in items:
        chip(d, x + 11, cy + 12, n)
        d.text((x + 34, cy), head, font=F("cjk_b", 14.5), fill=TOK["ink"])
        cy += 24
        line, buf = "", []
        for ch in body:
            if d.textlength(line + ch, font=F("cjk", 12.5)) > width - 34:
                buf.append(line)
                line = ch
            else:
                line += ch
        buf.append(line)
        for b in buf:
            d.text((x + 34, cy), b, font=F("cjk", 12.5), fill=TOK["ink_muted"])
            cy += 20
        cy += 15
    return cy


def mini_frame(frac, w=92, h=168, grid=False, hl=False):
    """放大过渡的小样: frac=卡片占宽比例"""
    f = Image.new("RGB", (w, h), TOK["screen_bg"])
    d = ImageDraw.Draw(f)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 12, outline=TOK["hair"], width=1)
    if grid:
        for i in range(2):
            tw, th = 30, 45
            x, y = 12 + i * 40, 26
            if hl and i == 0:
                d.rounded_rectangle([x - 4, y - 4, x + tw + 3, y + th + 3], 6,
                                    outline=TOK["gold"], width=2)
            paste_card(f, art("CARD-0001", "front"), (x, y), (tw, th), radius=4,
                       shadow=False)
        return f
    cw = max(24, int((w - 22) * frac))
    ch = int(cw * 1.5)
    if ch > h - 34:
        ch = h - 34
        cw = int(ch / 1.5)
    paste_card(f, art("CARD-0001", "front"), ((w - cw) // 2, (h - ch) // 2),
               (cw, ch), radius=6)
    return f


def arrow(d, x, y):
    d.line([x, y, x + 20, y], fill=TOK["ink_faint"], width=2)
    d.polygon([(x + 20, y - 5), (x + 30, y), (x + 20, y + 5)], fill=TOK["ink_faint"])


def rule_rows(im, x, y, w, rows):
    d = ImageDraw.Draw(im)
    cy = y
    for cond, res in rows:
        d.rounded_rectangle([x, cy, x + w, cy + 54], 12, fill=TOK["panel"],
                            outline=TOK["hair"], width=1)
        d.text((x + 18, cy + 9), cond, font=F("cjk", 12), fill=TOK["ink_muted"])
        d.text((x + 18, cy + 29), res, font=F("cjk_b", 13), fill=TOK["ink"])
        cy += 62
    return cy


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f1, b1 = art("CARD-0001", "front"), art("CARD-0001", "back")
    b2 = art("CARD-QR01", "back")
    j1, j2 = card_fields("CARD-0001"), card_fields("CARD-QR01")

    # ---------- 01 收藏页 ----------
    im = sheet(1180, 1010, "收藏页（白底 · 一行两个）",
               "打开小程序先看到这里；不放任何「生日」之类的模板字样")
    im.paste(*phone(screen_collection(), (66, 96)))
    end = notes(im, 520, 130, [
        (1, "一行两个", "卡片按时间排列，一行两张；上滑丝滑滚动，滑到底自然回弹。"),
        (2, "只写卡号和日期", "卡片下面就是 CARD #0001 和 2026.09.09，没有「生日」「我的」这类字样。"),
        (3, "点任意一张 → 放大到全屏", "卡片从它原来的位置放大铺满屏幕（有过渡动画），见下一张图。"),
        (4, "整页就是白的", "白底、细线、几乎没有装饰；唯一的颜色来自卡片自己。"),
    ])
    d = ImageDraw.Draw(im)
    bx, by, bw, bh = 554, end + 6, 300, 122
    d.rounded_rectangle([bx, by, bx + bw, by + bh], 14, fill=(255, 255, 255),
                        outline=TOK["hair"], width=1)
    d.text((bx + bw / 2, by + 38), "还没有卡", font=F("cjk_b", 15),
           fill=TOK["ink_faint"], anchor="mm")
    d.text((bx + bw / 2, by + 66), "做好第一张卡后，它会出现在这里",
           font=F("cjk_l", 11), fill=TOK["ink_faint"], anchor="mm")
    d.text((bx + bw / 2, by + bh + 16), "↑ 一张卡都没有时（不留空卡框）",
           font=F("cjk_l", 11), fill=TOK["ink_faint"], anchor="mm")
    notes(im, 520, end + 168, [
        (5, "卡片少时下方就留白", "两张卡就只占两格，不硬塞装饰、不放假卡片去填满屏幕。"),
        (6, "以后接上后台", "现在放的是两张真实示例卡；接了后台，这里就是客户自己的全部卡片。"),
    ])
    im.save(OUT / "01-collection.png")

    # ---------- 02 卡牌页 ----------
    im = sheet(1180, 1140, "卡牌页（白底 · 静置会轻轻浮动）",
               "点击后卡片放大铺满屏幕；手指拖动会转，倾斜手机跟着动")
    im.paste(*phone(screen_card(f1, j1, "front"), (66, 80)))
    notes(im, 520, 122, [
        (1, "静置时轻轻浮动", "不动它的时候，卡片会极轻微地浮动、摆动——不是一张死图（图上用两层淡叠影表示这个动作）。"),
        (2, "手指拖动 → 卡片跟着转", "能看到厚度和侧面反光；松手后自己缓缓回正。"),
        (3, "倾斜手机 → 卡片跟着倾斜", "用手机陀螺仪，像真拿在手里；手机不支持时自动改用拖动。"),
        (4, "点击卡片 → 翻面", "背面是统一的收藏品身份区（见下一张图）。"),
        (5, "卡牌的「含义」在卡下方", "卡号、纪念日期、寄语——都是生成这张卡时填的字段；没填的整行不出现。"),
        (6, "顶部只有返回 / 保存 / 分享", "没有滑块、没有参数、没有文件名、没有 AI 按钮。"),
    ], width=560)
    # 放大过渡小样
    d = ImageDraw.Draw(im)
    ty = 916
    d.text((520, ty - 34), "点击后：从卡片原来的位置放大到全屏（有过渡动画）",
           font=F("cjk", 12.5), fill=TOK["ink_muted"])
    for i, mf in enumerate([mini_frame(0, grid=True, hl=True),
                             mini_frame(0.62), mini_frame(0.94)]):
        im.paste(mf, (520 + i * 122, ty))
        if i < 2:
            arrow(d, 520 + i * 122 + 96, ty + 84)
    for i, label in enumerate(["收藏页", "放大中", "铺满全屏"]):
        d.text((520 + i * 122 + 46, ty + 176), label, font=F("cjk_l", 11),
               fill=TOK["ink_faint"], anchor="mm")
    im.save(OUT / "02-card-front.png")

    # ---------- 03 背面 ----------
    im = sheet(1360, 1010, "卡片背面（统一的收藏品身份区）",
               "正面可以千变万化；背面只有卡号、日期和「真的填了」的字段")
    im.paste(*phone(screen_card(b2, j2, "back"), (56, 96)))
    im.paste(*phone(screen_card(b1, j1, "back"), (520, 96)))
    d = ImageDraw.Draw(im)
    d.text((256, 948), "字段都填了：卡号 · FOR 小明 · 日期 · 寄语 · 二维码",
           font=F("cjk", 12.5), fill=TOK["ink"], anchor="mm")
    d.text((720, 948), "只填了卡号 + 日期：其余整行不出现",
           font=F("cjk", 12.5), fill=TOK["ink"], anchor="mm")
    notes(im, 950, 130, [
        (1, "二维码：有就显示", "卡背的 QR 是现实世界进入数字卡牌的入口；没有就完全不显示，不留空位。"),
        (2, "FOR 小明：来自 owner 字段", "Created by（制作者）和 Owned by（当前拥有者）是两个不同的人，有才显示。"),
        (3, "Date：这张卡纪念的那天", "必选。制作日期不出现在客户可见的界面上。"),
        (4, "同一张卡的另一种背面", "这张没有二维码、没有 owner —— 右下角和中间那一行整块消失，版面自己收拢。"),
        (5, "点击卡片 → 翻回正面", "翻面两个方向都通，动画连贯。"),
    ], width=380)
    im.save(OUT / "03-card-back.png")

    # ---------- 04 分层 & 降级 ----------
    im = sheet(1400, 1010, "卡内分层 & 各种「缺东西」时怎么办",
               "左边：卡牌内部是一叠有前后距离的层；右边：任何素材缺失都不会白屏或报错")
    sc = Image.new("RGB", (700, 830), TOK["panel"])
    ImageDraw.Draw(sc).rounded_rectangle([0, 0, 699, 829], 18,
                                         outline=TOK["hair"], width=1)
    d = ImageDraw.Draw(sc)
    d.text((36, 26), "卡牌内部的层（示意：实际层间距很小）", font=F("cjk_b", 15),
           fill=TOK["ink"])
    root = EXPORTS / "CARD-0001"
    stack = [("text", "文字层（最前）"), ("lineart", "线稿层"),
             ("effects", "光点 / 装饰层"), ("subject", "照片主体层"),
             ("background", "背景层（最后）")]
    sw_, sh_ = 132, 198
    x0, y0, step = 76, 430, (32, -24)
    poss = []
    for i, (name, _) in enumerate(reversed(stack)):     # 最前面的层最后画
        x, y = x0 + i * step[0], y0 + i * step[1]
        poss.append((x, y, len(stack) - i))
        soft_shadow(sc, (x, y, x + sw_, y + sh_), 12, blur=11, alpha=58, dy=6)
        plate = Image.new("RGB", (sw_, sh_), (11, 16, 32))
        layer = Image.open(root / "layers" / f"{name}.png").convert("RGBA")
        plate = Image.alpha_composite(
            plate.convert("RGBA"), layer.resize((sw_, sh_), Image.LANCZOS)).convert("RGB")
        paste_rounded(sc, plate, (x, y), (sw_, sh_), 12)
        ImageDraw.Draw(sc).rounded_rectangle(
            [x, y, x + sw_ - 1, y + sh_ - 1], 12, outline=(70, 78, 96), width=1)
    for x, y, n in poss:
        chip(d, x + 16, y + 16, n, r=10)
    ly = 408
    for i, (_, label) in enumerate(stack):
        chip(d, 384, ly + 9, i + 1, r=10)
        d.text((404, ly), label, font=F("cjk", 13), fill=TOK["ink"])
        ly += 30
    d.text((36, 668), "转动和静置浮动时，这五层按前后顺序错开，",
           font=F("cjk", 12.5), fill=TOK["ink_muted"])
    d.text((36, 690), "卡片就有了「厚度」和纵深。", font=F("cjk", 12.5),
           fill=TOK["ink_muted"])
    d.text((36, 730),
           "第一版：用微信样式表让这五层浮在不同深度；\n"
           "第二版：同一批层交给 WebGL 合成，出现虹彩\n"
           "和箔片随角度流动 —— 与客户现在看到的网页一致。",
           font=F("cjk", 12), fill=TOK["ink_faint"], spacing=7)
    im.paste(sc, (56, 120))

    rule_rows(im, 800, 130, 540, [
        ("缺少分层素材时", "只用正面整图 → 绝不白屏"),
        ("这张卡没有背面", "卡片不可翻面 → 点击无反应，不报错"),
        ("没有二维码", "背面不显示二维码 → 不留空位"),
        ("没填 Created by / Owned by", "背面不出现该行 → 版面自动收拢"),
        ("没填寄语 / 署名", "卡下方不出现该行 → 不显示空白文本"),
        ("手机不支持陀螺仪", "只用手指拖动 → 交互不丢失"),
        ("设备不支持 WebGL（第二版）", "自动退回第一版效果 → 卡还是能看"),
    ])
    d = ImageDraw.Draw(im)
    d.text((800, 578), "一句话：", font=F("cjk_b", 14), fill=TOK["ink"])
    for i, t in enumerate(["客户永远不会看到报错、白屏、",
                           "空白占位，也不会看到工作台的任何东西。"]):
        d.text((800, 606 + i * 22), t, font=F("cjk", 12.5), fill=TOK["ink_muted"])
    d.text((800, 672), "四张图都是静态示意图 · 浮动 / 转动 / 虹彩 / 陀螺仪无法在图片里呈现",
           font=F("cjk_l", 11), fill=TOK["ink_faint"])
    im.save(OUT / "04-layers-and-states.png")

    for f in sorted(OUT.glob("*.png")):
        print(f"{f.name:26s} {f.stat().st_size / 1024:7.0f} KB  "
              f"{Image.open(f).size[0]}x{Image.open(f).size[1]}")


if __name__ == "__main__":
    main()
