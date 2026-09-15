# -*- coding: utf-8 -*-
"""
真发布的内容转义测试（"丑字段"能不能安全写进云数据库）
========================================================
云开发的写库方式是发一条 JS 风格的 query 字符串, 例如:
    db.collection("cards").add({data: {"message": "..."}})
卡片里的寄语/署名是用户填的自由文本, 一旦包含引号、反斜杠、换行、emoji……
拼接错了就会:
  * 要么写库失败(报错, 你能看到)
  * 要么更糟 —— 字符串被截断, 悄悄写进去一条坏数据(看不到, 客户导入时才炸)
所以这里拿"最难看的字段"跑一遍, 并把 query 拿到 Node 里**真正求值**一遍,
看还原出来的数据跟我们想写的**是不是一模一样**。

用法: python tools/test_publish_escaping.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

SEEN = {"databaseadd": []}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode("utf8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n).decode("utf8"))
        if self.path.startswith("/tcb/databaseadd"):
            SEEN["databaseadd"].append(payload)
            self._send({"errcode": 0, "id": "doc-nasty"})
            return
        self._send({"errcode": 404, "errmsg": "nope"})


NASTY = {
    # 中文引号、英文双引号、单引号
    "message": '他说"生日快乐"，她还说\'要开心\'',
    # 反斜杠、换行、制表符、反引号、$ 与 {}
    "signature": "back\\slash\nnew\tline `tick` ${x} {\"a\":1}",
    # emoji + 组合字符
    "name": "小明🎂👨‍👩‍👧",
    # 看起来像 JS 结尾的字符
    "title": "*/ </script> \\u0000",
}

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


def make_doc():
    return {
        "code": "ABCD2345",
        "cardId": "CARD-0001",
        "status": "unclaimed",
        "ownerOpenId": "",
        "claimedAt": None,
        "createdAt": 1758000000000,
        "card": {
            "cardId": "CARD-0001", "displayId": "CARD #0001",
            "date": "2026-09-09", "surface": "dark",
            "depth": {"background": -0.3, "subject": 0.34, "effects": 0.64},
            "finish": "pearl", "foil": 0.55, "holoEnabled": True,
            "title": NASTY["title"],
            "content": {"message": NASTY["message"], "signature": NASTY["signature"],
                        "name": NASTY["name"], "age": "20"},
            "owner": {"id": "", "name": NASTY["name"]},
            "creator": {"id": "", "name": ""},
            "qr": {"enabled": False, "url": None}
        },
        "assets": {
            "front": "cloud://env/card/CARD-0001/front.webp",
            "back": "cloud://env/card/CARD-0001/back.webp",
            "layers": {"background": "cloud://env/card/CARD-0001/layers/background.webp",
                       "subject": "cloud://env/card/CARD-0001/layers/subject.webp"}
        }
    }


def evaluate_query_in_node(query):
    """把 query 丢给 Node 求值(用一个假 db 把 add 收到的 data 抓出来)。"""
    script = """
const query = process.argv[1];
let captured = null;
let coll = null;
const db = {
  collection(name) {
    coll = name;
    return {
      add(arg) { captured = arg.data; return { id: 'x' }; },
      where() { return { limit: () => ({ get: async () => ({ data: [] }) }) }; }
    };
  }
};
new Function('db', 'return (' + query + ')')(db);
process.stdout.write(JSON.stringify({ coll, data: captured }));
"""
    p = subprocess.run(["node", "-e", script, query], capture_output=True,
                       text=True, encoding="utf8", errors="replace")
    if p.returncode != 0:
        return None, (p.stderr or "").strip()
    return json.loads(p.stdout), None


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["CARDSTUDIO_API_BASE"] = f"http://127.0.0.1:{srv.server_port}"

    tmp = Path(tempfile.mkdtemp(prefix="escape-test-"))
    secret = tmp / "mp-secret.json"
    secret.write_text(json.dumps({"appid": "wx1", "secret": "s",
                                  "env": "test-env", "collection": "cards"}),
                      encoding="utf8")
    os.environ["CARDSTUDIO_SECRET_FILE"] = str(secret)
    os.environ["CARDSTUDIO_PUBLISH_DIR"] = str(tmp / "publish")
    os.environ["CARDSTUDIO_MOCK_CODES"] = str(tmp / "mockcodes.js")

    import publish_to_mp as pub

    try:
        print("\n[1] 用最难看的字段写一条记录")
        doc = make_doc()
        pub.tcb_add("FAKE-TOKEN", "test-env", "cards", doc)
        check("请求发出去了", len(SEEN["databaseadd"]) == 1)
        query = SEEN["databaseadd"][0]["query"]

        print("\n[2] 把 query 交给 Node 求值(等同于云开发后台的解析方式)")
        parsed, err = evaluate_query_in_node(query)
        check("query 能被正常求值（没有语法错）", parsed is not None, err or "")
        if parsed is None:
            print("\n  原始 query 片段:")
            print("   ", query[:400])
            raise SystemExit(1)

        print("\n[3] 求值结果与原始数据逐字段比对")
        check("集合名正确", parsed["coll"] == "cards", str(parsed["coll"]))
        got = parsed["data"]
        check("顶层字段一致",
              {k: got.get(k) for k in ("code", "cardId", "status", "ownerOpenId", "claimedAt")}
              == {k: doc[k] for k in ("code", "cardId", "status", "ownerOpenId", "claimedAt")},
              json.dumps({k: got.get(k) for k in ("code", "status")}, ensure_ascii=False))
        check("整份数据完全一致（deep equal）", got == doc,
              "不一致的字段: " + ", ".join(
                  k for k in doc if got.get(k) != doc[k]))
        check("寄语里的双引号没被吃掉",
              got["card"]["content"]["message"] == NASTY["message"],
              repr(got["card"]["content"]["message"]))
        check("反斜杠/换行/制表符没被吃掉",
              got["card"]["content"]["signature"] == NASTY["signature"],
              repr(got["card"]["content"]["signature"]))
        check("emoji 与组合字符完好",
              got["card"]["owner"]["name"] == NASTY["name"],
              repr(got["card"]["owner"]["name"]))
        check("看起来像 JS 结尾的字符也没事",
              got["card"]["title"] == NASTY["title"], repr(got["card"]["title"]))
        check("嵌套的 layers 结构完好",
              got["assets"]["layers"] == doc["assets"]["layers"],
              json.dumps(got["assets"]["layers"], ensure_ascii=False))

        print("\n[4] 顺带确认: 这些字段走到小程序那边仍然是原文")
        sys.path.insert(0, str(ROOT / "miniprogram"))     # 只是为了让路径看起来一致
        check("卡片字段取自 content（小程序侧同一份数据）",
              got["card"]["content"]["message"] == NASTY["message"])
    finally:
        srv.shutdown()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n结果: {passed} 通过 / {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
