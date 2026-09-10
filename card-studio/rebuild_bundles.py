# -*- coding: utf-8 -*-
"""
用 esbuild 从 app.js 重建 app.bundle.js(修复"打包版比源码旧"的问题)
===================================================================
* 直接调用 @esbuild/win32-x64/esbuild.exe(不经过 node 包装器, 避免受限环境的管道问题)
* 覆盖: 模板 + 所有 demo/成品项目 + 工坊运行期项目
* 重建后校验: 是否包含 uFxDepth/uHasFx/uSafeOffset(新版特性) 与我们的补丁标记

用法: python card-studio/rebuild_bundles.py [--check-only] [目录...]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ESBUILD = ROOT / "node_modules" / "@esbuild" / "win32-x64" / "esbuild.exe"

MARKERS = ["uFxDepth", "uHasFx", "uSafeOffset", "* depth * .20;", "mix(0.15, 1.0, tilt)",
           "已回退到 front.png", "缺少 3D 模型", "!layers.size"]


def web_dirs():
    dirs = [ROOT / "RuiC-card-skill-main" / "assets" / "web-template"]
    for d in ("demo-koi", "demo-birthday"):          # web 直接在项目下一层
        w = ROOT / d / "web"
        if w.is_dir():
            dirs.append(w)
    for sub in (ROOT / "birthday-set").glob("*"):     # 成品目录本身就是 web
        if (sub / "app.js").exists():
            dirs.append(sub)
    for d in ("birthday-build", "card-studio/projects"):
        for sub in (ROOT / d).glob("*"):
            if (sub / "web").is_dir():
                dirs.append(sub / "web")
    return [d for d in dirs if (d / "app.js").exists()]


def build(web, check_only=False):
    entry, out = web / "app.js", web / "app.bundle.js"
    before = out.stat().st_size if out.exists() else 0
    if not check_only:
        r = subprocess.run([str(ESBUILD), str(entry), "--bundle", f"--outfile={out}",
                            "--platform=browser", "--format=esm", "--target=es2020",
                            "--charset=utf8", "--log-level=warning"], capture_output=True, text=True)
        if r.returncode != 0:
            return f"失败: {r.stderr.strip()[:120]}"
    s = out.read_text(encoding="utf8", errors="replace")
    missing = [m for m in MARKERS if m not in s]
    size = out.stat().st_size
    tag = "OK" if not missing else "缺: " + ",".join(missing)
    return f"{size/1e6:5.2f} MB (原 {before/1e6:5.2f})  {tag}"


def main():
    if not ESBUILD.exists():
        print("找不到 esbuild:", ESBUILD)
        return 1
    check_only = "--check-only" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dirs = [(ROOT / a).resolve() for a in args] if args else web_dirs()
    for d in dirs:
        print(f"{d.relative_to(ROOT)}  " + build(d, check_only), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
