# -*- coding: utf-8 -*-
"""
把"身份证背板"(四种 backStyle)应用到模板与所有项目的 app.js
==========================================================
之前只有 birthday-set/demo-birthday 打了这个补丁, 工坊生成的卡翻到背面还是
模板自带的 White Atelier 背板 —— 这里统一掉。

幂等: 背板里已有 backStyle 标记就跳过。之后用 rebuild_bundles.py 重建 bundle。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "card-studio"))
from build_birthday_set import BACK_JS  # noqa: E402


def patch_file(p):
    s = p.read_text(encoding="utf8")
    i = s.find("function backTexture() {")
    if i < 0:
        return "无 backTexture"
    j = s.find("\n}\n", i)
    if j < 0:
        return "找不到函数结尾"
    block = s[i:j]
    if "backStyle" in block:
        return "已存在"
    s = s[:i] + BACK_JS.strip() + s[j + 3:]
    p.write_text(s, encoding="utf8")
    return "OK"


def targets():
    out = [ROOT / "RuiC-card-skill-main" / "assets" / "web-template" / "app.js"]
    for d in ("demo-koi", "demo-birthday"):
        f = ROOT / d / "web" / "app.js"
        if f.exists():
            out.append(f)
    for sub in (ROOT / "birthday-set").glob("*"):
        if (sub / "app.js").exists():
            out.append(sub / "app.js")
    for d in ("birthday-build", "card-studio/projects"):
        for sub in (ROOT / d).glob("*"):
            f = sub / "web" / "app.js"
            if f.exists():
                out.append(f)
    return out


def main():
    files = targets()
    for f in files:
        print(f"{f.relative_to(ROOT)}  {patch_file(f)}")
    print(f"共处理 {len(files)} 个 app.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
