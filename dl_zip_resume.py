# -*- coding: utf-8 -*-
"""Parallel chunked downloader for the Blender portable zip.

Egress is slow and flaky per connection, so split the file into N byte
segments, each downloaded by its own thread with 4 MB Range chunks and
mirror rotation. Official SHA-256 verified at the end. Rerun resumes any
incomplete segments.
"""
import os, ssl, sys, time, hashlib, urllib.request
from concurrent.futures import ThreadPoolExecutor

ssl._create_default_https_context = ssl._create_unverified_context

VERSION = "4.5.13"
NAME = f"blender-{VERSION}-windows-x64.zip"
EXPECTED_SHA = "b5fdf800ce65fa2f209e8f68d02667e4d720fa1c42f247c72d1882ab04decba6"
MIRRORS = [
    "https://download.blender.org/release/Blender4.5/",
    "https://mirror.clarkson.edu/blender/release/Blender4.5/",
    "https://ftp.nluug.nl/pub/graphics/blender/release/Blender4.5/",
]
TOOLS = os.path.join("demo-koi", "tools")
CHUNK = 4 * 1024 * 1024
SEGS = 4
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BlenderFetch/1.0"}


def head_size(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=30) as r:
        return int(r.headers["Content-Length"])


def fetch_range(url, start, end):
    req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def download_segment(urls, segfile, start, end):
    need = end - start
    have = os.path.getsize(segfile) if os.path.exists(segfile) else 0
    if have == need:
        return
    got = have
    mode = "ab" if have else "wb"
    tries = 0
    with open(segfile, mode) as out:
        while got < need:
            cur = start + got
            last = min(cur + CHUNK - 1, end - 1)
            url = urls[tries % len(urls)]
            try:
                data = fetch_range(url, cur, last)
                if len(data) != last - cur + 1:
                    raise IOError(f"short {len(data)} != {last-cur+1}")
                out.write(data)
                got += len(data)
                tries = 0
            except Exception:
                tries += 1
                if tries >= 80:
                    raise
                time.sleep(0.6)
                continue
    print(f"  segment {start//(1<<20)}MB done", flush=True)


def main():
    os.makedirs(TOOLS, exist_ok=True)
    target = os.path.join(TOOLS, NAME)
    if os.path.exists(target):
        print("already present", target)
        sys.exit(0)
    urls = [m + NAME for m in MIRRORS]
    total = None
    for u in urls:
        try:
            total = head_size(u)
            break
        except Exception:
            continue
    if total is None:
        print("no mirror reachable")
        sys.exit(1)
    print(f"total {total/1e6:.0f} MB, {SEGS} streams", flush=True)
    base = total // SEGS
    bounds = []
    for s in range(SEGS):
        bounds.append((s * base, total if s == SEGS - 1 else (s + 1) * base))
    parts = []
    with ThreadPoolExecutor(max_workers=SEGS) as ex:
        futs = []
        for s, (a, b) in enumerate(bounds):
            sf = target + f".seg{s}"
            parts.append(sf)
            futs.append(ex.submit(download_segment, urls, sf, a, b))
        for f in futs:
            try:
                f.result()
            except Exception as e:
                print("segment failed:", repr(e)[:140], flush=True)
                sys.exit(1)
    with open(target, "wb") as out:
        for sf in parts:
            with open(sf, "rb") as f:
                shutil_copy(out, f)
    h = hashlib.sha256()
    with open(target, "rb") as f:
        for part in iter(lambda: f.read(1 << 20), b""):
            h.update(part)
    if h.hexdigest() != EXPECTED_SHA:
        print("SHA MISMATCH", h.hexdigest(), "size", os.path.getsize(target))
        sys.exit(1)
    print("SHA256 OK", h.hexdigest(), os.path.getsize(target), "bytes", flush=True)
    for sf in parts:
        os.remove(sf)


def shutil_copy(out, f):
    while True:
        b = f.read(1 << 20)
        if not b:
            break
        out.write(b)


if __name__ == "__main__":
    main()
