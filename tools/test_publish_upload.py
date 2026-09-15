# -*- coding: utf-8 -*-
"""
真发布路径的可执行测试（用本地假服务器冒充微信的接口）
======================================================
为什么需要它: 真发布要正式 AppID + AppSecret, 现在还没有, 所以这条路一直没被验证过。
但"脚本发出的请求长什么样、上传的文件有没有损坏、写进数据库的记录对不对"
这些全都能测 —— 起一个本地 HTTP 服务, 假装自己是 api.weixin.qq.com 就行。

验证内容:
  1. 拿 access_token 的请求参数对不对
  2. 申请上传地址时带了 env 和 path
  3. 真正上传时 multipart 的字段/key/Signature 齐不齐, **文件字节有没有损坏**
  4. 写数据库的 query 里, 记录结构对不对(assets 是 cloud:// fileID)
  5. 记录文件落盘(publish/<CODE>/record.json)与云端写入的内容一致
  6. 微信报错(比如 40164 本机 IP 不在白名单)能被翻译成人话

用法: python tools/test_publish_upload.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent

# 假服务器收到的所有东西都记在这里
SEEN = {"token": [], "uploadfile": [], "cos": [], "databaseadd": []}
# 需要模拟"微信报错"时把它设成一个 errcode
FORCE_TOKEN_ERROR = {"code": None}


class FakeWeChat(BaseHTTPRequestHandler):
    server_version = "FakeWeChat/1.0"

    def log_message(self, *args):
        pass                                   # 别刷屏

    # ---------- 工具 ----------
    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n)

    # ---------- 路由 ----------
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        if url.path == "/cgi-bin/token":
            SEEN["token"].append(qs)
            if FORCE_TOKEN_ERROR["code"]:
                self._send({"errcode": FORCE_TOKEN_ERROR["code"],
                            "errmsg": "invalid ip 1.2.3.4, not in whitelist"})
                return
            self._send({"access_token": "FAKE-TOKEN", "expires_in": 7200})
            return
        self._send({"errcode": 404, "errmsg": "no such path"}, 404)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        body = self._read()

        if url.path == "/tcb/uploadfile":
            payload = json.loads(body.decode("utf8"))
            SEEN["uploadfile"].append({"query": urllib.parse.parse_qs(url.query),
                                       "body": payload})
            self._send({
                "errcode": 0,
                "url": f"http://127.0.0.1:{self.server.server_port}/cos",
                "token": "FAKE-COS-TOKEN",
                "authorization": "FAKE-SIGNATURE",
                "file_id": f"cloud://test-env.{payload['env']}/{payload['path']}",
                "cos_file_id": "FAKE-COS-FILEID",
            })
            return

        if url.path == "/cos":
            ctype = self.headers.get("Content-Type") or ""
            boundary = ctype.split("boundary=")[-1].encode("utf8")
            fields, files = parse_multipart(body, boundary)
            SEEN["cos"].append({"fields": fields,
                                "filename": files.get("_filename"),
                                "size": len(files.get("file", b"")),
                                "blob": files.get("file", b"")})
            self.send_response(201)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if url.path == "/tcb/databaseadd":
            payload = json.loads(body.decode("utf8"))
            SEEN["databaseadd"].append({"query": urllib.parse.parse_qs(url.query),
                                        "body": payload})
            self._send({"errcode": 0, "id": "doc-fake-1"})
            return

        self._send({"errcode": 404, "errmsg": "no such path"}, 404)


def parse_multipart(body, boundary):
    """够用的 multipart 解析: 返回 (普通字段, 文件字段)。"""
    fields = {}
    files = {}
    for part in body.split(b"--" + boundary):
        if not part.strip() or part.strip() == b"--":
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        if not _:
            continue
        data = data.rstrip(b"\r\n")
        head_text = head.decode("utf8", "replace")
        name = re.search(r'name="([^"]+)"', head_text)
        if not name:
            continue
        key = name.group(1)
        fname = re.search(r'filename="([^"]*)"', head_text)
        if fname:
            fields[key] = "<file>"
            files["_filename"] = fname.group(1)
            files["file"] = data
        else:
            fields[key] = data.decode("utf8", "replace")
    return fields, files


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeWeChat)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def run_publish(env, args):
    cmd = [sys.executable, str(TOOLS / "publish_to_mp.py")] + args
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf8", errors="replace",
                       env=dict(os.environ, **env))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}" + (f"  → {extra}" if extra else ""))


def main():
    srv = start_server()
    port = srv.server_port
    base = f"http://127.0.0.1:{port}"

    tmp = Path(tempfile.mkdtemp(prefix="cardstudio-test-"))
    publish_dir = tmp / "publish"
    secret_file = tmp / "mp-secret.json"
    mock_codes = tmp / "mockcodes.js"
    secret_file.write_text(json.dumps({
        "appid": "wxtest0000000000", "secret": "fake-secret",
        "env": "test-env", "collection": "cards"}), encoding="utf8")

    env = {
        "CARDSTUDIO_API_BASE": base,
        "CARDSTUDIO_SECRET_FILE": str(secret_file),
        "CARDSTUDIO_PUBLISH_DIR": str(publish_dir),
        "CARDSTUDIO_MOCK_CODES": str(mock_codes),
    }

    try:
        print("\n[1] 真发布: 素材上传 + 写数据库")
        code, out = run_publish(env, ["CARD-0001"])
        print("      脚本输出末行:", out.strip().splitlines()[-1] if out.strip() else "(空)")
        check("脚本执行成功", code == 0, out[-400:] if code else "")

        # --- access_token ---
        check("拿到了 access_token（带 appid 与 secret）",
              len(SEEN["token"]) == 1 and
              SEEN["token"][0].get("appid") == ["wxtest0000000000"] and
              SEEN["token"][0].get("grant_type") == ["client_credential"],
              json.dumps(SEEN["token"], ensure_ascii=False))

        # --- 上传 ---
        src_layers = sorted((ROOT / "exports" / "CARD-0001" / "layers").glob("*.png"))
        expect_files = 2 + len([p for p in src_layers
                                if p.stem in ("background", "subject", "effects", "text")])
        check(f"申请了 {expect_files} 个上传地址（正面+背面+分层）",
              len(SEEN["uploadfile"]) == expect_files,
              f"实际 {len(SEEN['uploadfile'])}")
        paths = [u["body"]["path"] for u in SEEN["uploadfile"]]
        check("上传路径按卡片分目录",
              all(p.startswith("card/CARD-0001/") for p in paths), str(paths))
        check("每个申请都带对了 env",
              all(u["body"]["env"] == "test-env" for u in SEEN["uploadfile"]))
        check("access_token 挂在 URL 上",
              all(u["query"].get("access_token") == ["FAKE-TOKEN"]
                  for u in SEEN["uploadfile"]))

        # --- COS 表单字段 ---
        cos = SEEN["cos"]
        check("真的 POST 了文件到 COS", len(cos) == expect_files, f"实际 {len(cos)}")
        ok_fields = all(
            c["fields"].get("Signature") == "FAKE-SIGNATURE"
            and c["fields"].get("x-cos-security-token") == "FAKE-COS-TOKEN"
            and c["fields"].get("x-cos-meta-fileid") == "FAKE-COS-FILEID"
            and c["fields"].get("key", "").startswith("card/CARD-0001/")
            for c in cos)
        check("multipart 里 cos 要求的字段齐全", ok_fields,
              json.dumps(cos[0]["fields"] if cos else {}, ensure_ascii=False))

        # --- 文件字节有没有损坏 ---
        from PIL import Image
        import io
        # 用发布目录里落盘的素材做基准
        pub = [p for p in publish_dir.iterdir() if p.is_dir()][0]
        pairs = [("front.webp", pub / "front.webp"), ("back.webp", pub / "back.webp")]
        for f in sorted((pub / "layers").glob("*.webp")):
            pairs.append((f"layers/{f.name}", f))
        sent = {c["fields"].get("key"): c for c in cos}
        all_ok = True
        detail = []
        for key, local_file in [(
                f"card/CARD-0001/{k}", v) for k, v in pairs]:
            c = sent.get(key)
            if not c:
                all_ok = False
                detail.append(f"缺 {key}")
                continue
            blob = local_file.read_bytes()
            if c["size"] != len(blob) or c["blob"] != blob:
                all_ok = False
                detail.append(f"{key} 字节不一致")
            else:
                # 顺带确认传上去的确实是能打开的 WebP
                im = Image.open(io.BytesIO(c["blob"]))
                if im.size != (640, 960) and "front" not in key and "back" not in key:
                    detail.append(f"{key} 尺寸异常 {im.size}")
        check("每个文件的字节与本地完全一致（没损坏/没串位）", all_ok, "；".join(detail))

        # --- 数据库记录 ---
        check("写了一条数据库记录", len(SEEN["databaseadd"]) == 1)
        if SEEN["databaseadd"]:
            q = SEEN["databaseadd"][0]["body"]["query"]
            check("query 指向 cards 集合", 'db.collection("cards")' in q, q[:80])
            m = re.search(r"add\(\{data:\s*(\{.*\})\}\)\s*$", q, re.S)
            doc = json.loads(m.group(1)) if m else {}
            check("记录里有 code 且是规范形式（无横线）",
                  bool(doc.get("code")) and "-" not in doc.get("code", "-"),
                  str(doc.get("code")))
            check("记录初始状态是未领取",
                  doc.get("status") == "unclaimed" and doc.get("ownerOpenId") == ""
                  and doc.get("claimedAt") is None,
                  json.dumps({k: doc.get(k) for k in ("status", "ownerOpenId", "claimedAt")}))
            check("assets.front 是云存储 fileID",
                  str(doc.get("assets", {}).get("front", "")).startswith("cloud://"),
                  str(doc.get("assets", {}).get("front")))
            check("assets.layers 是云存储 fileID 映射",
                  isinstance(doc.get("assets", {}).get("layers"), dict)
                  and all(str(v).startswith("cloud://")
                          for v in doc["assets"]["layers"].values()),
                  json.dumps(doc.get("assets", {}).get("layers"), ensure_ascii=False))
            check("card 字段带渲染必需项",
                  all(k in doc.get("card", {}) for k in
                      ("cardId", "displayId", "date", "surface", "depth")),
                  json.dumps(list(doc.get("card", {}).keys()), ensure_ascii=False))

            # --- 落盘的 record.json 与云端一致 ---
            rec_file = pub / "record.json"
            check("发布了 record.json", rec_file.exists())
            if rec_file.exists():
                on_disk = json.loads(rec_file.read_text(encoding="utf8"))
                check("落盘记录与写库内容一致",
                      on_disk.get("code") == doc.get("code")
                      and on_disk.get("assets", {}).get("front") == doc["assets"]["front"]
                      and on_disk.get("card", {}).get("depth") == doc["card"].get("depth"),
                      "字段不一致")

            # --- 台账 ---
            ledger = json.loads((publish_dir / "_ledger.json").read_text(encoding="utf8"))
            entry = ledger["codes"][-1] if ledger.get("codes") else {}
            check("台账记下了这个码（mode=cloud, 带 docId）",
                  entry.get("mode") == "cloud" and entry.get("docId") == "doc-fake-1"
                  and entry.get("code") == doc.get("code"),
                  json.dumps(entry, ensure_ascii=False))
            check("真发布不写本地演示码",
                  not mock_codes.exists() or doc["code"] not in mock_codes.read_text(encoding="utf8"))

        print("\n[2] 微信报错时的提示（模拟本机 IP 不在白名单）")
        SEEN["token"].clear()
        FORCE_TOKEN_ERROR["code"] = 40164
        code, out = run_publish(env, ["CARD-0002"])
        check("脚本以失败退出", code != 0)
        check("提示里点明了 IP 白名单",
              "IP 白名单" in out or "白名单" in out, out.strip()[-200:])
        check("没有继续去上传", len(SEEN["cos"]) == expect_files,
              "报错后不该再传文件")

    finally:
        FORCE_TOKEN_ERROR["code"] = None
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n结果: {passed} 通过 / {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
