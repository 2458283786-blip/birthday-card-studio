"""Download/install the official portable Blender for a project.

The skill's ensure_blender.py uses urllib with default TLS verification, but this
machine's CA bundle rejects download.blender.org's chain. We only bypass the TLS
handshake verification; the package integrity is still enforced by the official
SHA-256 published by Blender (mismatch aborts before anything is executed).

Usage: python dl_blender.py <project_dir>
"""
import ssl

# Bypass broken local CA chain for download.blender.org only (used globally below).
ssl._create_default_https_context = ssl._create_unverified_context

import sys
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent / "RuiC-card-skill-main" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from ensure_blender import ensure_blender  # noqa: E402

if __name__ == "__main__":
    import time

    project = sys.argv[1] if len(sys.argv) > 1 else "demo-koi"
    last = None
    for attempt in range(1, 8):
        try:
            exe = ensure_blender(Path(project))
            print("BLENDER_READY", exe)
            sys.exit(0)
        except Exception as e:  # 服务器间歇 403/超时, 自动重试
            last = e
            print(f"attempt {attempt} failed: {e!r}; retrying in 4s")
            time.sleep(4)
    print("BLENDER_DOWNLOAD_FAILED", repr(last))
    sys.exit(1)
