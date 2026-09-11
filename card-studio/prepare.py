# -*- coding: utf-8 -*-
"""
卡片工坊 · 素材加工
====================
把一张拖进来的图变成四层卡面素材 + 配置(全部程序化, 无 AI)。

用法:
  python prepare.py <project_dir> <image_path> <style> <meta.json> [mode]

style: ink(宣纸墨韵) | space(深空星夜) | plain(素雅米白) | blackgold(玄黑烫金)
mode:  auto=自动判断(推荐) | keep=保留整图不抠 | cut=扣除纯色底

图片处理原则(按你的要求):
  * 绝不硬抠复杂背景。纯色底才抠, 且抠得保守(只去与边角几乎同色的像素)
  * 其他情况默认"保留整图", 图片所有颜色原样上卡, 两侧用衬底色
"""
import argparse, json, math, os, random, sys, traceback
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageOps

CANVAS = (1024, 1536)          # 竖版卡画布
CUT_BOX = (900, 980)           # 抠图主体构图区 (宽, 高)
CUT_CENTER = (512, 762)
KEEP_BOX = (940, 960)          # 整图模式构图区(基本铺满留少量边, 不裁切)
KEEP_CENTER = (512, 768)
random.seed(7)

INK = (26, 24, 22)
PAPER = (244, 239, 227)

SKILL = Path(__file__).resolve().parent.parent / "RuiC-card-skill-main" / "scripts"
JOB_LOG = os.environ.get("CARD_JOB_LOG", "")


def log(msg):
    line = f"[工坊] {msg}"
    print(line, flush=True)
    if JOB_LOG:
        try:
            with open(JOB_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


# ----------------------------------------------------------------- 素材判断/抠图
def load_rgba(path):
    im = ImageOps.exif_transpose(Image.open(path))   # 手机横拍 EXIF 旋转先摆正
    if im.mode in ("RGBA", "LA"):
        return im.convert("RGBA")
    return im.convert("RGB").convert("RGBA")


def has_real_alpha(im):
    a = im.getchannel("A")
    hist = a.histogram()
    return hist[0] / (im.size[0] * im.size[1]) > 0.002


def detect_checkerboard(im):
    """有棋盘格底返回 (RGBA图, 报告), 否则 None。"""
    try:
        sys.path.insert(0, str(SKILL))
        from checkerboard_to_alpha import detect_checkerboard, convert_to_alpha
    except Exception:
        return None
    try:
        rep = detect_checkerboard(im)
        if rep is None:
            return None
        out, _ = convert_to_alpha(im, rep)
        return out, rep
    except Exception:
        return None


def border_purity(im):
    """检查四边颜色是否纯净, 返回 (是否纯色底, 颜色波动spread, 背景主色)。"""
    try:
        import numpy as np
    except Exception:
        return False, 99, None
    W, H = im.size
    scale = 480.0 / max(W, H)
    small = im.resize((max(1, int(W * scale)), max(1, int(H * scale))), Image.Resampling.BILINEAR)
    sw, sh = small.size
    rgb = np.asarray(small.convert("RGB")).astype(np.int16)
    edges = np.concatenate([rgb[0:2].reshape(-1, 3), rgb[-2:].reshape(-1, 3),
                            rgb[:, 0:2].reshape(-1, 3), rgb[:, -2:].reshape(-1, 3)])
    bg = np.median(edges, axis=0)
    spread = float(np.abs(edges - bg).max())
    pure = spread <= 10.0
    return pure, round(spread, 1), [int(v) for v in bg]


def flood_cutout(im, tol):
    """把与四边连通的相近颜色当背景抹掉。tol 越小越保守(去得越少)。"""
    try:
        import numpy as np
    except Exception:
        log("本机没有 numpy, 无法抠图(请改用透明底PNG或整图模式)")
        return None
    W, H = im.size
    scale = 480.0 / max(W, H)
    small = im.resize((max(1, int(W * scale)), max(1, int(H * scale))), Image.Resampling.BILINEAR)
    sw, sh = small.size
    rgb = np.asarray(small.convert("RGB")).astype(np.int16)
    edges = np.concatenate([rgb[0:2].reshape(-1, 3), rgb[-2:].reshape(-1, 3),
                            rgb[:, 0:2].reshape(-1, 3), rgb[:, -2:].reshape(-1, 3)])
    bg = np.median(edges, axis=0)
    dist = np.abs(rgb - bg).max(axis=2)
    ok = dist <= tol
    from collections import deque
    seed = np.zeros((sh, sw), bool)
    seed[0, :] = ok[0, :]
    seed[-1, :] = ok[-1, :]
    seed[:, 0] = ok[:, 0]
    seed[:, -1] = ok[:, -1]
    vis = np.zeros((sh, sw), bool)
    dq = deque()
    for y in (0, sh - 1):
        for x in range(sw):
            if seed[y, x] and not vis[y, x]:
                vis[y, x] = True
                dq.append((y, x))
    for x in (0, sw - 1):
        for y in range(sh):
            if seed[y, x] and not vis[y, x]:
                vis[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < sh and 0 <= nx < sw and not vis[ny, nx] and ok[ny, nx]:
                vis[ny, nx] = True
                dq.append((ny, nx))
    frac = 1.0 - float(vis.mean())
    if not (0.05 <= frac <= 0.97):
        return None
    mask_small = Image.fromarray((~vis).astype("uint8") * 255, "L")
    mask = mask_small.resize((W, H), Image.Resampling.BILINEAR).point(lambda v: 255 if v > 127 else 0)
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.0))
    rgba = im.convert("RGBA")
    rgba.putalpha(ImageChops.multiply(rgba.getchannel("A"), mask))
    return rgba, {"subject_fraction": round(frac, 3), "bg": [int(v) for v in bg]}


# ----------------------------------------------------------------- 背景风格
def _grain(base, n, lo=0, hi=16, alpha=255):
    rgba = base.mode == "RGBA"
    for _ in range(n):
        x, y = random.randint(0, base.size[0] - 1), random.randint(0, base.size[1] - 1)
        v = random.randint(lo, hi)
        c = tuple(max(0, min(255, ch - v)) for ch in base.getpixel((x, y))[:3])
        base.putpixel((x, y), c + ((alpha,) if rgba else ()))
    return base


def _wash(base, cx, cy, rx, ry, color, alpha, blur=50):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                                  fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(layer)
    return base


def background_ink():
    im = Image.new("RGBA", CANVAS, PAPER + (255,))
    _wash(im, 180, 1150, 560, 300, (122, 118, 106), 40, 60)
    _wash(im, 930, 1210, 640, 330, (112, 108, 98), 32, 70)
    _wash(im, 280, 300, 380, 90, (214, 208, 194), 40, 40)
    _wash(im, 900, 260, 320, 80, (206, 200, 186), 34, 40)
    _wash(im, 512, 700, 240, 240, (178, 58, 42), 16, 3)
    _grain(im, 2600)
    return im.convert("RGB").convert("RGBA")


def background_space():
    im = Image.new("RGBA", CANVAS, (10, 13, 32, 255))
    d = ImageDraw.Draw(im)
    for yy in range(CANVAS[1]):
        t = yy / CANVAS[1]
        col = (int(8 + 20 * t), int(11 + 40 * t), int(30 + 78 * t))
        d.line([(0, yy), (CANVAS[0], yy)], fill=col + (255,))
    _wash(im, 220, 500, 420, 300, (98, 118, 214), 26, 90)
    _wash(im, 860, 1150, 460, 320, (150, 90, 190), 22, 100)
    for _ in range(330):
        x, y = random.randint(0, CANVAS[0] - 1), random.randint(0, CANVAS[1] - 1)
        v = random.randint(150, 255)
        r = random.choice([1, 1, 1, 2])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(v, v, min(255, v + 8), random.randint(60, 220)))
    _grain(im, 900, lo=0, hi=10)
    return im.convert("RGB").convert("RGBA")


def background_plain():
    im = Image.new("RGBA", CANVAS, (247, 243, 233, 255))
    _wash(im, 240, 260, 500, 160, (232, 226, 210), 44, 90)
    _wash(im, 830, 1280, 520, 220, (226, 219, 200), 46, 90)
    _grain(im, 2200)
    return im.convert("RGB").convert("RGBA")


def background_blackgold():
    im = Image.new("RGBA", CANVAS, (20, 16, 13, 255))
    d = ImageDraw.Draw(im)
    for yy in range(CANVAS[1]):
        t = yy / CANVAS[1]
        col = (int(16 + 26 * t), int(12 + 20 * t), int(9 + 16 * t))
        d.line([(0, yy), (CANVAS[0], yy)], fill=col + (255,))
    _wash(im, 200, 420, 500, 380, (110, 78, 40), 30, 120)
    _wash(im, 880, 1150, 560, 420, (120, 84, 42), 26, 130)
    GOLD = (238, 205, 148)
    for _ in range(220):
        x, y = random.randint(0, CANVAS[0] - 1), random.randint(0, CANVAS[1] - 1)
        v = random.randint(90, 220)
        r = random.choice([1, 1, 2])
        d.ellipse([x - r, y - r, x + r, y + r],
                  fill=tuple(int(GOLD[i] * v / 255) for i in range(3)) + (255,))
    return im.convert("RGB").convert("RGBA")


STYLES = {"ink": background_ink, "space": background_space,
          "plain": background_plain, "blackgold": background_blackgold}
PAGE_BG = {"ink": "#efe9db", "space": "#0b0f24", "plain": "#f3efe4", "blackgold": "#16110d"}


# ----------------------------------------------------------------- 摆放/线稿
def place(im, box, center):
    """按 contain 缩放(不裁切)并贴到透明画布中心, 返回 RGBA 画布。"""
    W, H = CANVAS
    bw, bh = box
    cx, cy = center
    iw, ih = im.size
    scale = min(bw / iw, bh / ih, 2.0)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    sub = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(sub, (cx - nw // 2, cy - nh // 2), sub)
    return canvas


def make_lineart(subject_rgba):
    """主体轮廓 -> 白底黑线。"""
    W, H = CANVAS
    a = subject_rgba.getchannel("A").point(lambda v: 255 if v > 12 else 0)
    ring = ImageChops.subtract(a.filter(ImageFilter.MaxFilter(7)), a)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    white = Image.new("RGB", (W, H), (255, 255, 255))
    return Image.composite(black, white, ring)


def blank_lineart():
    return Image.new("RGB", CANVAS, (255, 255, 255))


def lineart_keep(subject_rgba):
    """整图模式线稿: 画面内部高对比边缘描线 + 画幅细边框(白底黑线)。"""
    W, H = CANVAS
    L = subject_rgba.convert("RGB").convert("L")
    mag = ImageChops.subtract(L.filter(ImageFilter.MaxFilter(7)),
                              L.filter(ImageFilter.MinFilter(7)))
    mask = mag.point(lambda v: 255 if v > 42 else 0)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    white = Image.new("RGB", (W, H), (255, 255, 255))
    out = Image.composite(black, white, mask)
    # 画幅细边框(主体内容外缘一圈), 保证体检通过且视觉上是精致画框
    a = subject_rgba.getchannel("A").point(lambda v: 255 if v > 12 else 0)
    box = a.getbbox()
    if box:
        x0, y0, x1, y1 = box
        m = 2
        ImageDraw.Draw(out).rectangle([x0 - m, y0 - m, x1 + m, y1 + m],
                                      outline=(30, 28, 26), width=3)
    return out


# ----------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("image")
    ap.add_argument("style", choices=list(STYLES))
    ap.add_argument("meta")
    ap.add_argument("mode", nargs="?", default="auto",
                    choices=["auto", "keep", "cut"])
    a = ap.parse_args()
    mode = a.mode if a.mode in ("auto", "keep", "cut") else "auto"

    root = Path(a.project).resolve()
    (root / "assets").mkdir(parents=True, exist_ok=True)
    meta = json.loads(Path(a.meta).read_text(encoding="utf-8"))

    src = load_rgba(a.image)
    src.save(root / "assets" / "source.png")
    log(f"收到素材 {src.size[0]}x{src.size[1]}px, 处理方式: "
        + {"auto": "自动判断", "keep": "保留整图(不抠)", "cut": "扣除纯色底"}[mode])

    kind = None          # 'transparent' | 'keep'
    subject_src = None   # 透明主体源图(用于抠图模式)
    report = {}

    if mode == "keep":
        kind = "keep"
        log("按你的选择: 保留整图全部颜色, 不抠任何背景")
    else:
        if has_real_alpha(src):
            subject_src = src
            kind = "transparent"
            log("检测到透明通道 → 直接作为透明主体")
        else:
            det = detect_checkerboard(src)
            if det is not None:
                subject_src, report = det
                kind = "transparent"
                log("检测到棋盘格底 → 已确定性转成真透明")
            else:
                pure, spread, bg = border_purity(src)
                log(f"底色分析: {'纯色底' if pure else '非纯色底(波动 ' + str(spread) + ') '}")
                if pure or mode == "cut":
                    # 保守容差: 只去掉与边角几乎同色的像素
                    tol = max(5, min(14, int(spread) + 3))
                    log(f"开始抠纯色底(保守容差 {tol})…")
                    cut = flood_cutout(src, tol)
                    if cut is None:
                        if mode == "auto":
                            log("抠图判定不可靠 → 自动改为保留整图(不硬抠)")
                            kind = "keep"
                        else:
                            log("错误: 没能安全抠出主体(底色不纯或主体贴边)。")
                            log("建议: 换透明底PNG, 或在上一步选「保留整图」。")
                            raise SystemExit(2)
                    else:
                        subject_src, report = cut
                        kind = "transparent"
                        log(f"抠图完成: 主体占比 {report.get('subject_fraction', 0) * 100:.1f}%")
                else:
                    # 非纯色底 + 自动模式 → 不硬抠, 整图保留
                    kind = "keep"
                    log("背景不是纯色 → 自动改为保留整图, 颜色全保留(选「抠纯色底」可强制尝试)")

    if kind == "keep":
        box, center = KEEP_BOX, KEEP_CENTER
        # 整图作为不透明面板(有透明通道则按整张含透明处理)
        if has_real_alpha(src):
            subject = place(src, box, center)
        else:
            subject = place(src.convert("RGB").convert("RGBA"), box, center)
        subject.save(root / "assets" / "subject.png")
        log(f"整图已上卡 {subject.size[0]}x{subject.size[1]}(完整保留, 两侧衬底)")
        lineart_keep(subject).save(root / "assets" / "lineart.png")
        log("线稿层: 画面边缘描线 + 画幅细框")
    else:
        hist = subject_src.getchannel("A").histogram()
        vis = 1 - hist[0] / (subject_src.size[0] * subject_src.size[1])
        if vis < 0.03:
            log("错误: 图片几乎全透明, 没有可用的主体。")
            raise SystemExit(2)
        subject = place(subject_src, CUT_BOX, CUT_CENTER)
        subject.save(root / "assets" / "subject.png")
        log(f"主体已摆放 {subject.size[0]}x{subject.size[1]}")
        make_lineart(subject).save(root / "assets" / "lineart.png")
        log("线稿已生成(主体轮廓描边, 与主体严格对齐)")

    bg = STYLES[a.style]()
    bg.save(root / "assets" / "background.png")
    log(f"背景生成: {a.style}")

    finish = meta.get("finish", "gold") or "gold"
    config = {
        "title": meta.get("title", "无题") or "无题",
        "subtitle": meta.get("subtitle", ""),
        "technique": meta.get("technique", ""),
        "tagline": meta.get("tagline", ""),
        "edition": meta.get("edition", "NO.001 / 001"),
        "collection": meta.get("collection", "我的全息典藏") or "我的全息典藏",
        "description": meta.get("description", "") or "拖图生成的程序化全息卡。",
        "qrUrl": meta.get("qrUrl", ""),
        "appearance": {"finish": finish, "background": PAGE_BG[a.style]},
        "parameters": {"subjectScale": 1.0, "subjectDepth": 0.3,
                       "backgroundDepth": -0.2, "foil": 0.62},
        "safeArea": {"scale": 1.12, "offset": [-0.06, -0.085]},
        "_provenance": {"source_image": "assets/source.png",
                        "made_by": "card-studio/prepare.py",
                        "template": "studio",
                        "style": a.style, "mode": mode, "report": report},
    }
    try:                                    # 有二维码链接 → 生成矩阵(§11)
        import qr_util
        qr_util.attach(config)
    except Exception as e:
        log(f"二维码跳过: {type(e).__name__}")
    (root / "card-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    log("配置已写入 card-config.json, 素材就绪")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        log("错误: 处理素材时发生异常, 请换一张图试试")
        raise SystemExit(2)
