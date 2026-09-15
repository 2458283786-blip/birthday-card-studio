# -*- coding: utf-8 -*-
"""
小程序 require 一致性检查（因为跑不了小程序, 这是最接近的静态验证）
==================================================================
专抓这类 bug：某页 require 了 { getCard }，但那个模块已经不导出 getCard 了。
这种错误不会在语法检查里暴露，只会在运行时抛 "xxx is not a function",
然后被 Promise 吞掉 —— 表现成"页面空白/显示空态", 极难排查。

用法: python tools/check_mp_requires.py
"""
import re
import sys
from pathlib import Path

try:                       # 控制台可能是 GBK, 打印符号会崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
MP = ROOT / "miniprogram"

REQUIRE = re.compile(
    r"(?:const|let|var)\s*(?P<names>\{[^}]*\}|[A-Za-z_$][\w$]*)\s*=\s*"
    r"require\(\s*['\"](?P<path>[^'\"]+)['\"]\s*\)"
)
EXPORTS = re.compile(r"module\.exports\s*=\s*\{")


def exported_names(src):
    """把 module.exports = { ... } 里的名字抓出来(只做浅层解析, 够用)。"""
    m = EXPORTS.search(src)
    if not m:
        return None                      # 不是对象字面量导出(例如 module.exports = fn)
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                body = src[i + 1:j]
                break
    else:
        return None
    names = set()
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key = part.split(":")[0].strip()
        else:
            key = part.strip()
        key = key.lstrip(".").strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]*", key):
            names.add(key)
    return names


def resolve(base_dir, spec):
    if not spec.startswith("."):
        return None                       # 外部依赖(wx-server-sdk 等), 跳过
    target = (base_dir / spec).resolve()
    for cand in (target, target.with_suffix(".js"), target / "index.js"):
        if cand.is_file():
            return cand
    return False                          # 相对路径但文件不存在


def main():
    problems = []
    checked = 0
    for f in sorted(MP.rglob("*.js")):
        src = f.read_text(encoding="utf8", errors="replace")
        for m in REQUIRE.finditer(src):
            checked += 1
            spec = m.group("path")
            names_raw = m.group("names").strip()
            target = resolve(f.parent, spec)
            rel = f.relative_to(ROOT)
            if target is None:
                continue
            if target is False:
                problems.append(f"{rel}: require('{spec}') —— 文件不存在")
                continue
            if not names_raw.startswith("{"):
                continue
            wanted = [n.strip().split(":")[0].strip().lstrip(".")
                      for n in names_raw.strip("{}").split(",") if n.strip()]
            exported = exported_names(target.read_text(encoding="utf8", errors="replace"))
            if exported is None:
                continue
            for name in wanted:
                if name and name not in exported:
                    problems.append(
                        f"{rel}: 从 {target.name} 取了 {{{name}}}，但它没有导出这个"
                    )

    print(f"检查了 {checked} 处 require")
    if problems:
        print(f"\n❌ 发现 {len(problems)} 个问题:")
        for p in problems:
            print("  -", p)
        return 1
    print("✅ 所有 require 的名字都存在")
    return 0


if __name__ == "__main__":
    sys.exit(main())
