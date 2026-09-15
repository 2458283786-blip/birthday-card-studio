# -*- coding: utf-8 -*-
"""
把 exports/ 里的 Card Package 打包成小程序能直接用的素材
==========================================================
用法:
  python tools/build_mp_packages.py                    # 打包 exports/ 下所有卡
  python tools/build_mp_packages.py CARD-0001 CARD-QR01

产出(miniprogram/data/):
  packages/<CARD-ID>/front.webp          正面整图(卡面无素材时用这张)
  packages/<CARD-ID>/back.webp           背面整图(没有背面就不产出)
  packages/<CARD-ID>/layers/*.webp       实际存在的分层(缺失的层不产出文件)
  packages/<CARD-ID>/card.json           精简后的卡牌数据(去掉 _studio 等生成侧参数)
  cards/manifest.js                      卡片索引(小程序直接 require)

要点:
  * 小程序代码包单包上限 2M, 所以图片一律降采样 + WebP; 单张卡约 80KB
  * `surface` 由卡面边缘取色算出: light/dark —— 卡牌页据此自动选背景(浅色卡用浅灰底)
  * 只在素材真实存在时才写字段/文件; 缺失一律不产出, 由小程序端 fallback
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "exports"
MP_DATA = ROOT / "miniprogram" / "data"
PKG_DIR = MP_DATA / "packages"

LAYERS = ("background", "subject", "effects", "text")
# 为什么没有 lineart: 网页版 shader 里它是给"主体加高光"的蒙版(tLine),
# 不是一张可见的图层 —— 当成图层画上去画面就错了。
WEBP_Q = 82
FRONT_SIZE = (720, 1080)      # 卡面整图(详情页铺满屏幕时用)
LAYER_SIZE = (640, 960)       # 分层素材(分层数多, 再压一档)
BACK_SIZE = (720, 1080)

# 层深度的兜底值(与 shader 的 parallax 同一套参数); 实际取值来自 card.json 的 _studio.parameters
DEFAULT_DEPTH = {"background": -0.30, "subject": 0.34, "effects": 0.64}
DEFAULT_FOIL = 0.55          # 材质覆盖层浓度(网页版默认 0.52~0.55)


def edge_tone(img):
    """从卡面四周取色判断这张卡是深色还是浅色(决定卡牌页背景)。"""
    im = img.convert("RGB").resize((80, 120), Image.LANCZOS)
    W, H = im.size
    px = im.load()
    pts = []
    for x in range(W):
        pts += [px[x, 2], px[x, H - 3]]
    for y in range(H):
        pts += [px[2, y], px[W - 3, y]]
    r = sum(p[0] for p in pts) / len(pts)
    g = sum(p[1] for p in pts) / len(pts)
    b = sum(p[2] for p in pts) / len(pts)
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return ("light" if lum > 0.62 else "dark"), round(lum, 3)


def save_webp(img, dst, size):
    dst.parent.mkdir(parents=True, exist_ok=True)
    out = img.convert("RGBA").resize(size, Image.LANCZOS)
    out.save(dst, "WEBP", quality=WEBP_Q, method=6)
    return dst.stat().st_size


def trim_card_json(card, params, appearance=None):
    """只保留小程序要用的字段; 生成侧参数(_studio 等)不进小程序包。"""
    keep = ("schemaVersion", "cardId", "displayId", "internalId", "theme",
            "template", "title", "date", "creator", "owner", "content",
            "material", "interaction", "media", "qr", "status", "cardVersion")
    out = {k: card[k] for k in keep if k in card}
    out["hasBack"] = False          # 下面按实际文件改
    out["layerNames"] = []
    out["surface"] = "dark"
    # 层深度: 卡牌页用它算层间视差(和网页版 shader 用同一个公式)
    out["depth"] = {
        k: params.get(f"{k}Depth", v) for k, v in DEFAULT_DEPTH.items()
    }
    # 材质: 网页版 CSS-3D 路径用 finish 选渐变与混合模式, foil 决定覆盖层浓度
    ap = appearance or {}
    finish = str(ap.get("finish") or "pearl")
    out["finish"] = finish
    out["foil"] = params.get("foil", DEFAULT_FOIL)
    out["holoEnabled"] = (bool((card.get("material") or {}).get("holoEnabled", True))
                          and finish != "original")
    return out


def build_assets(src, dst, card, params):
    """
    把一张卡的素材写成小程序可用的 WebP。
    返回 (data, sizes, lum)。
    「发布到云开发」也调这个函数 —— 保证两条路径产出的素材完全一致。
    """
    src = Path(src)
    dst = Path(dst)
    front_src = src / "preview" / "front.jpg"
    if not front_src.exists():
        raise FileNotFoundError(f"缺少 {front_src}")
    appearance = ((card.get("_studio") or {}).get("appearance") or {})
    data = trim_card_json(card, params, appearance)

    # 1) 正面整图
    front = Image.open(front_src).convert("RGB")
    size_front = save_webp(front, dst / "front.webp", FRONT_SIZE)
    data["surface"], lum = edge_tone(front)

    # 2) 背面
    size_back = 0
    back_src = src / "preview" / "back.jpg"
    if back_src.exists():
        size_back = save_webp(Image.open(back_src).convert("RGB"),
                              dst / "back.webp", BACK_SIZE)
        data["hasBack"] = True

    # 3) 分层(只打包真实存在的; 顺手清掉上一版留下的、这一版不再用的文件)
    layer_dir = dst / "layers"
    if layer_dir.is_dir():
        for stale in layer_dir.glob("*.webp"):
            if stale.stem not in LAYERS:
                stale.unlink()
    layer_bytes = 0
    for name in LAYERS:
        p = src / "layers" / f"{name}.png"
        if p.exists():
            layer_bytes += save_webp(Image.open(p), layer_dir / f"{name}.webp",
                                     LAYER_SIZE)
            data["layerNames"].append(name)

    sizes = {"front": size_front, "back": size_back, "layers": layer_bytes,
             "total": size_front + size_back + layer_bytes}
    return data, sizes, lum


def build_one(pkg):
    src = EXPORTS / pkg
    cfg_path = src / "card.json"
    if not cfg_path.exists():
        print(f"  跳过 {pkg}: 没有 card.json")
        return None
    if not (src / "preview" / "front.jpg").exists():
        print(f"  跳过 {pkg}: 没有 preview/front.jpg")
        return None
    card = json.loads(cfg_path.read_text(encoding="utf8"))
    dst = PKG_DIR / card["cardId"]
    params = ((card.get("_studio") or {}).get("parameters") or {})

    data, sizes, lum = build_assets(src, dst, card, params)
    (dst / "card.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")

    print(f"  {data['displayId']:12s} surface={data['surface']}(lum={lum}) "
          f"分层={len(data['layerNames'])}/5 背面={'有' if data['hasBack'] else '无'} "
          f"合计={sizes['total'] / 1024:.0f}KB "
          f"(正{sizes['front'] / 1024:.0f} 背{sizes['back'] / 1024:.0f} "
          f"层{sizes['layers'] / 1024:.0f})")
    return data


def write_manifest(cards):
    PKG_DIR.parent.joinpath("cards").mkdir(parents=True, exist_ok=True)
    lines = [
        "// 由 tools/build_mp_packages.py 生成, 不要手改",
        "// 卡片索引: 以后接后台 API 时, 用同样的结构替换这个文件即可",
        "module.exports = {",
        "  cards: [",
    ]
    for c in cards:
        item = {
            "cardId": c["cardId"],
            "displayId": c["displayId"],
            "title": c.get("title"),
            "date": c.get("date"),
            "surface": c["surface"],
            "depth": c.get("depth") or DEFAULT_DEPTH,
            "finish": c.get("finish") or "pearl",
            "foil": c.get("foil", DEFAULT_FOIL),
            "holoEnabled": bool(c.get("holoEnabled", True)),
            "hasBack": c["hasBack"],
            "layerNames": c["layerNames"],
            "front": f"/data/packages/{c['cardId']}/front.webp",
            "back": (f"/data/packages/{c['cardId']}/back.webp"
                     if c["hasBack"] else None),
            "layers": {n: f"/data/packages/{c['cardId']}/layers/{n}.webp"
                       for n in c["layerNames"]},
            "fields": {
                "message": (c.get("content") or {}).get("message") or "",
                "signature": (c.get("content") or {}).get("signature") or "",
                "ownerName": ((c.get("owner") or {}).get("name") or ""),
                "creatorName": ((c.get("creator") or {}).get("name") or ""),
                "qr": bool((c.get("qr") or {}).get("enabled")),
            },
        }
        lines.append("    " + json.dumps(item, ensure_ascii=False) + ",")
    lines += ["  ],", "};", ""]
    out = MP_DATA / "cards" / "manifest.js"
    out.write_text("\n".join(lines), encoding="utf8")
    return out


def build_all(pkgs=None, verbose=True):
    """把 exports/ 里的卡全部打包进小程序, 并重写索引。返回打包成功的卡片数据列表。
    发布脚本(tools/publish_to_mp.py)也调这个入口, 保证小程序里一定有对应的卡。"""
    pkgs = pkgs or sorted(p.name for p in EXPORTS.iterdir()
                          if p.is_dir() and (p / "card.json").exists())
    if verbose:
        print(f"打包 {len(pkgs)} 张卡 → {PKG_DIR.relative_to(ROOT)}")
    cards = [c for c in (build_one(p) for p in pkgs) if c]
    if not cards:
        return []
    write_manifest(cards)
    return cards


def main():
    args = sys.argv[1:]
    cards = build_all(args or None)
    if not cards:
        print("没有可打包的卡")
        return 1
    total = sum(f.stat().st_size for f in PKG_DIR.rglob("*") if f.is_file())
    print(f"\n索引: {(MP_DATA / 'cards' / 'manifest.js').relative_to(ROOT)}")
    print(f"素材总计: {total / 1024:.0f} KB  (小程序主包上限 2048 KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
