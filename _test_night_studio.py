# -*- coding: utf-8 -*-
"""端到端测试: 工坊「Birthday / Night 高级款」模板(用你上传过的另一张图)。"""
import base64
import json
import time
import urllib.request
from pathlib import Path

B = "http://127.0.0.1:4399"
PHOTO = Path("card-studio/projects/card-mtvomjtr/_upload.jpg")   # 你上传过的另一张(5MB)

img = base64.b64encode(PHOTO.read_bytes()).decode()
payload = {
    "imageData": "data:image/jpeg;base64," + img,
    "template": "night",
    "title": "", "subtitle": "HAPPY BIRTHDAY",
    "technique": "2026.09.09", "edition": "CARD #0002",
    "age": "20", "wish": "MAY EVERY YEAR BE KIND TO YOU", "name": "",
    "collection": "BIRTHDAY COLLECTIBLE", "style": "ink", "mode": "auto",
}
req = urllib.request.Request(B + "/api/generate", data=json.dumps(payload).encode(),
                             headers={"Content-Type": "application/json"})
jid = json.loads(urllib.request.urlopen(req, timeout=60).read())["id"]
print("job:", jid, flush=True)

t0 = time.time()
while time.time() - t0 < 600:
    jobs = json.loads(urllib.request.urlopen(B + "/api/jobs", timeout=20).read())
    me = [j for j in jobs if j["id"] == jid]
    if not me:
        print("job 消失")
        break
    j = me[0]
    if j["status"] in ("done", "error"):
        log = json.loads(urllib.request.urlopen(B + "/api/jobs/" + jid + "/log", timeout=20).read())["lines"]
        print("\n".join(log[-12:]))
        print("FINAL:", j["status"], "| template:", j.get("template"))
        if j["status"] == "done":
            for f in ["static.png", "static-back.png", "static-preview.png"]:
                u = f"{B}/cardimg/{jid}/{f}"
                try:
                    r = urllib.request.urlopen(u, timeout=30)
                    print(f"  {f}: {r.status} {len(r.read())/1e6:.2f} MB")
                except Exception as e:
                    print(f"  {f}: ERR {repr(e)[:50]}")
            print("  网页:", urllib.request.urlopen(f"{B}/p/{jid}/", timeout=20).status)
        break
    time.sleep(4)
else:
    print("超时")
