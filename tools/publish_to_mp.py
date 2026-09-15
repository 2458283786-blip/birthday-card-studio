# -*- coding: utf-8 -*-
"""
工作台侧「发布到小程序」—— 给一张卡出一个一次性导入码
=====================================================
用法(在项目根目录执行):

  python tools/publish_to_mp.py --list
      看已经发出去的码、属于哪张卡、谁领了

  python tools/publish_to_mp.py CARD-0002 --dry-run
      本地发布(不联网): 出码, 并把码写进小程序的"本地演示码"。
      开发者工具里立刻能手输这个码导入, 走完整条流程 —— 不需要 AppID。

  python tools/publish_to_mp.py CARD-0002
      真发布: 素材传到云开发存储 + 往云数据库写一条"未领取"记录。
      需要根目录的 mp-secret.json (见 mp-secret.example.json), 且要有正式 AppID。

  python tools/publish_to_mp.py CARD-0002 --count 5
      一次发 5 个码(例如一批实体卡, 一卡一码)。

  python tools/publish_to_mp.py --status
      从云开发拉取: 每个码有没有被领、什么时候领的(需要 mp-secret.json)。

产出:
  publish/<CODE>/{front.webp,back.webp,layers/*.webp,card.json}   发布用的素材
  publish/<CODE>/record.json                                     写进数据库的那条记录
  publish/_ledger.json                                           本地台账(发过哪些码)

安全:
  * AppSecret 只放在 mp-secret.json, 该文件已在 .gitignore 里, 永不入库
  * 一个码对应一次发放; 同一张卡可以再发新码(比如客户弄丢了)
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_mp_packages as bmp            # noqa: E402
from claim_code import make_code, normalize, pretty   # noqa: E402

EXPORTS = ROOT / "exports"
# 下面三个路径/变量只为自动化测试能指到临时位置; 正常使用不要设置
PUBLISH = Path(os.environ.get("CARDSTUDIO_PUBLISH_DIR", ROOT / "publish"))
LEDGER = PUBLISH / "_ledger.json"
SECRET = Path(os.environ.get("CARDSTUDIO_SECRET_FILE", ROOT / "mp-secret.json"))
MOCK_CODES = Path(os.environ.get("CARDSTUDIO_MOCK_CODES",
                                 ROOT / "miniprogram" / "data" / "cards" / "mockcodes.js"))

API = os.environ.get("CARDSTUDIO_API_BASE", "https://api.weixin.qq.com").rstrip("/")


# ---------------------------------------------------------------- 台账

def load_ledger():
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf8"))
        except Exception:
            pass
    return {"codes": []}


def save_ledger(ledger):
    PUBLISH.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf8")


def ledger_find(ledger, code):
    for item in ledger["codes"]:
        if item["code"] == code:
            return item
    return None


def new_code(ledger):
    for _ in range(50):
        code = make_code()
        if not ledger_find(ledger, code):
            return code
    raise RuntimeError("连续 50 次都撞码, 不正常")


# ------------------------------------------------- 本地演示码(mockcodes.js)

def read_mock_codes():
    if not MOCK_CODES.exists():
        return {}
    out = {}
    for line in MOCK_CODES.read_text(encoding="utf8").splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith('"'):
            continue
        k, _, v = line.partition(":")
        try:
            out[json.loads(k.strip())] = json.loads(v.strip())
        except Exception:
            continue
    return out


def write_mock_codes(mapping):
    lines = [
        "// 由 tools/publish_to_mp.py / claim_code.py 生成, 不要手改",
        "// 仅用于本地演示(mode: 'mock'): 不连云开发也能走完导入流程。",
        "// 正式环境的导入码由云开发登记处下发, 与这个文件无关。",
        "module.exports = {",
    ]
    for code, card_id in mapping.items():
        lines.append(f"  {json.dumps(code)}: {json.dumps(card_id)},")
    lines += ["};", ""]
    MOCK_CODES.parent.mkdir(parents=True, exist_ok=True)
    MOCK_CODES.write_text("\n".join(lines), encoding="utf8")


# ---------------------------------------------------------------- 网络

def _post_json(url, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf8"))


def _multipart(fields, filename, blob, file_field="file"):
    boundary = "----cardstudio" + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode("utf8"))
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        .encode("utf8"))
    parts.append(blob)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def explain(err):
    """把微信的报错翻译成"你该去做什么"。"""
    code = err.get("errcode")
    msg = err.get("errmsg", "")
    hint = {
        40164: "本机公网 IP 不在小程序的 IP 白名单里 —— 去小程序后台「开发管理 → 开发设置 → "
               "服务器域名/IP 白名单」把报错里给出的那个 IP 加进去, 或者先把白名单清空",
        40013: "AppID 不对, 检查 mp-secret.json",
        40125: "AppSecret 不对(注意不要在后台重置后还用旧的)",
        40001: "access_token 失效, 重新跑一次即可",
        41001: "缺少 access_token 参数",
        85088: "该小程序没有开通云开发, 或环境 ID 写错了",
        -1: "微信侧系统繁忙, 过一会儿重试",
    }.get(code, "对照微信文档排查")
    return f"errcode={code} errmsg={msg} → {hint}"


def access_token(appid, secret):
    url = (f"{API}/cgi-bin/token?grant_type=client_credential"
           f"&appid={appid}&secret={secret}")
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf8"))
    if "access_token" not in data:
        raise RuntimeError("拿 access_token 失败: " + explain(data))
    return data["access_token"]


def tcb_upload(token, env, cloud_path, blob):
    """上传一个文件到云存储, 返回 fileID(cloud://...)。"""
    r = _post_json(f"{API}/tcb/uploadfile?access_token={token}",
                   {"env": env, "path": cloud_path})
    if r.get("errcode"):
        raise RuntimeError("申请上传地址失败: " + explain(r))
    body, ctype = _multipart({
        "key": cloud_path,
        "Signature": r["authorization"],
        "x-cos-security-token": r["token"],
        "x-cos-meta-fileid": r["cos_file_id"],
        "success_action_status": "201",
    }, Path(cloud_path).name, blob)
    req = urllib.request.Request(r["url"], data=body,
                                 headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=120) as resp:
        if resp.status not in (200, 201, 204):
            raise RuntimeError(f"上传失败 HTTP {resp.status}")
    return r["file_id"]


def tcb_add(token, env, collection, doc):
    query = (f'db.collection("{collection}").add({{data: '
             f"{json.dumps(doc, ensure_ascii=False)}}})")
    r = _post_json(f"{API}/tcb/databaseadd?access_token={token}",
                   {"env": env, "query": query})
    if r.get("errcode"):
        raise RuntimeError("写数据库失败: " + explain(r))
    return r.get("id")


def tcb_query_by_code(token, env, collection, code):
    query = (f'db.collection("{collection}").where({{code: "{code}"}})'
             f".limit(1).get()")
    r = _post_json(f"{API}/tcb/databasequery?access_token={token}",
                   {"env": env, "query": query})
    if r.get("errcode"):
        raise RuntimeError("查数据库失败: " + explain(r))
    rows = r.get("data")
    if isinstance(rows, str):
        rows = json.loads(rows)
    return (rows or [None])[0]


# ---------------------------------------------------------------- 发布

def load_secret():
    if not SECRET.exists():
        raise SystemExit(
            "找不到 mp-secret.json。真发布需要它(见 mp-secret.example.json)。\n"
            "只想本地试流程的话, 加 --dry-run 就不需要任何密钥。")
    cfg = json.loads(SECRET.read_text(encoding="utf8"))
    for key in ("appid", "secret", "env"):
        if not cfg.get(key):
            raise SystemExit(f"mp-secret.json 缺少 {key}")
    cfg.setdefault("collection", "cards")
    return cfg


def find_card(card_id):
    for p in EXPORTS.iterdir():
        cfg = p / "card.json"
        if not cfg.exists():
            continue
        card = json.loads(cfg.read_text(encoding="utf8"))
        if card.get("cardId") == card_id or p.name == card_id:
            return p, card
    return None, None


def publish(card_id, count, dry):
    print(f"发布 {card_id} × {count} 份" + ("  [本地演示模式 · 不联网]" if dry else "  [真发布到云开发]"))

    src, card = find_card(card_id)
    if not src:
        raise SystemExit(f"exports/ 里找不到 {card_id}（先在工作台里导出这张卡）")

    # 先确认密钥齐了, 再干打包这种费时的活
    cfg = None if dry else load_secret()
    token = access_token(cfg["appid"], cfg["secret"]) if cfg else None

    # 小程序里必须已经有这张卡, 否则导入后也看不到画面
    cards = bmp.build_all(verbose=False)
    if not any(c["cardId"] == card["cardId"] for c in cards):
        raise SystemExit(f"{card['cardId']} 打包进小程序失败, 请先解决上面的报错")

    ledger = load_ledger()

    mock_map = read_mock_codes()
    issued = []
    for _ in range(count):
        code = new_code(ledger)
        entry = {
            "code": code,
            "pretty": pretty(code),
            "cardId": card["cardId"],
            "displayId": card.get("displayId") or card["cardId"],
            "issuedAt": int(time.time() * 1000),
            "mode": "dry" if dry else "cloud",
            "status": "unclaimed",
            "claimedAt": None,
        }

        if dry:
            mock_map[normalize(code)] = card["cardId"]
            out_dir = PUBLISH / code
            out_dir.mkdir(parents=True, exist_ok=True)
            # 记录结构和真发布**完全一致**, 只是素材用小程序包内的本地路径。
            # card 字段直接复用打包器的 trim_card_json —— 保证"本地样板"和
            # "真上传的数据"不可能漂移(之前手写就漂了: depth 形状不一样)。
            params = ((card.get("_studio") or {}).get("parameters") or {})
            data = bmp.trim_card_json(card, params)
            data["hasBack"] = (src / "preview" / "back.jpg").exists()
            layer_names = [n for n in bmp.LAYERS
                           if (src / "layers" / f"{n}.png").exists()]
            data["layerNames"] = layer_names
            record = {
                "code": normalize(code),
                "cardId": card["cardId"],
                "status": "unclaimed",
                "ownerOpenId": "",
                "claimedAt": None,
                "createdAt": entry["issuedAt"],
                "card": data,
                "assets": {
                    "front": f"/data/packages/{card['cardId']}/front.webp",
                    "back": (f"/data/packages/{card['cardId']}/back.webp"
                             if data["hasBack"] else None),
                    "layers": {n: f"/data/packages/{card['cardId']}/layers/{n}.webp"
                               for n in layer_names},
                },
                "note": "本地演示: 未上传云端, 仅登记在小程序 data/cards/mockcodes.js",
            }
            (out_dir / "record.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf8")
        else:
            out_dir = PUBLISH / code
            params = ((card.get("_studio") or {}).get("parameters") or {})
            data, sizes, _lum = bmp.build_assets(src, out_dir, card, params)
            (out_dir / "card.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")

            assets = {}
            front = out_dir / "front.webp"
            assets["front"] = tcb_upload(
                token, cfg["env"], f"card/{card['cardId']}/front.webp",
                front.read_bytes())
            back = out_dir / "back.webp"
            if back.exists():
                assets["back"] = tcb_upload(
                    token, cfg["env"], f"card/{card['cardId']}/back.webp",
                    back.read_bytes())
            layers = {}
            for layer_file in sorted((out_dir / "layers").glob("*.webp")):
                layers[layer_file.stem] = tcb_upload(
                    token, cfg["env"],
                    f"card/{card['cardId']}/layers/{layer_file.name}",
                    layer_file.read_bytes())
            assets["layers"] = layers

            record = {
                "code": normalize(code),
                "cardId": card["cardId"],
                "status": "unclaimed",
                "ownerOpenId": "",
                "claimedAt": None,
                "createdAt": entry["issuedAt"],
                "card": data,
                "assets": assets,
            }
            entry["docId"] = tcb_add(token, cfg["env"], cfg["collection"], record)
            (out_dir / "record.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf8")
            entry["uploaded"] = {"front": assets["front"],
                                 "back": assets.get("back"),
                                 "layers": len(layers)}
            print(f"  上传完成: 正面 + 背面 + {len(layers)} 个分层 "
                  f"(共 {sizes['total'] / 1024:.0f}KB)")

        ledger["codes"].append(entry)
        issued.append(entry)

    save_ledger(ledger)
    if dry:
        write_mock_codes(mock_map)

    print()
    for entry in issued:
        print(f"  导入码: {entry['pretty']}   →  {entry['displayId']}")
    print()
    if dry:
        print("现在就能试: 打开小程序 → 收藏页 → 输入导入码 → 卡片出现。")
        print("再输一次同一个码会直接进入(本人不算重复导入);")
        print("长按收藏页的演示码提示可以重置本地登记处。")
        print(f"台账: {LEDGER.relative_to(ROOT)}")
    else:
        print("已写入云数据库, 客户在小程序里输这个码即可领取。")
        print("看领取情况: python tools/publish_to_mp.py --status")
    return 0


def cmd_list():
    ledger = load_ledger()
    if not ledger["codes"]:
        print("还没有发过码。试试: python tools/publish_to_mp.py CARD-0001 --dry-run")
        return 0
    print(f"共 {len(ledger['codes'])} 个码:")
    print(f"  {'导入码':<11} {'卡片':<11} {'方式':<6} {'状态':<8} 发出时间")
    for item in ledger["codes"]:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(item["issuedAt"] / 1000))
        status = item.get("status", "unclaimed")
        if status == "claimed" and item.get("claimedAt"):
            status += "(" + time.strftime("%m-%d %H:%M",
                                          time.localtime(item["claimedAt"] / 1000)) + ")"
        print(f"  {item['pretty']:<11} {item['displayId']:<11} "
              f"{item['mode']:<6} {status:<8} {when}")
    print()
    print("说明: 本地台账只记录'发出去过什么'。真实领取状态以云数据库为准(status 命令)。")
    return 0


def cmd_status():
    cfg = load_secret()
    ledger = load_ledger()
    cloud_codes = [x for x in ledger["codes"] if x["mode"] == "cloud"]
    if not cloud_codes:
        print("台账里还没有'真发布'的码。")
        return 0
    token = access_token(cfg["appid"], cfg["secret"])
    changed = 0
    for item in cloud_codes:
        row = tcb_query_by_code(token, cfg["env"], cfg["collection"],
                                normalize(item["code"]))
        if not row:
            print(f"  {item['pretty']}  云端没有这条记录(可能被删了)")
            continue
        owner = row.get("ownerOpenId") or ""
        if owner and item.get("status") != "claimed":
            item["status"] = "claimed"
            item["claimedAt"] = row.get("claimedAt")
            changed += 1
        state = "已领取" if owner else "未领取"
        when = ""
        if row.get("claimedAt"):
            when = time.strftime("%Y-%m-%d %H:%M",
                                 time.localtime(row["claimedAt"] / 1000))
        print(f"  {item['pretty']}  {item['displayId']}  {state}  {when}")
    if changed:
        save_ledger(ledger)
    return 0


def main():
    ap = argparse.ArgumentParser(description="工作台侧: 出一张卡的小程序导入码")
    ap.add_argument("card", nargs="?", help="卡号, 如 CARD-0002")
    ap.add_argument("--dry-run", action="store_true",
                    help="本地发布(不联网): 出码并写进小程序本地演示码")
    ap.add_argument("--count", type=int, default=1, help="发几个码(默认 1)")
    ap.add_argument("--list", action="store_true", help="看已发出的码")
    ap.add_argument("--status", action="store_true", help="从云开发拉领取状态")
    args = ap.parse_args()

    if args.list:
        return cmd_list()
    if args.status:
        return cmd_status()
    if not args.card:
        ap.print_help()
        return 1
    if args.count < 1:
        raise SystemExit("--count 至少是 1")
    return publish(args.card, args.count, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
