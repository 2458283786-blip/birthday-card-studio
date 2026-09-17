# -*- coding: utf-8 -*-
"""
安全替换工具(护栏) —— 批量改 JS 函数体专用
=========================================
背景: 之前两次事故都是"用脆弱模式(\n}\n)找函数结尾"导致**误删后续函数**
      (renderIconNode / refreshIcons / addShadow 被吃掉 → 查看器报错白屏)。

本工具的规则:
  1. **括号配平**定位函数结尾(会跳过字符串/模板串, 不靠模式匹配)
  2. 写入前记录函数清单, 写入后比对: 数量或名称集合变化 → **拒绝写入**
  3. 支持 dry-run, 并打印每个文件的 before/after 摘要

用法:
  python tools/safe_replace.py <app.js 或目录> --func backTexture --file new_body.js [--dry]
  python tools/safe_replace.py <目录> --check              # 只体检: 列出缺失的关键函数

注: new_body.js 里放**替换后的完整函数文本**(含 function xxx() { ... })。
"""
import argparse
import re
import sys
from pathlib import Path

KEY_FUNCS = ["addShadow", "renderIconNode", "refreshIcons", "backTexture", "canvasTexture"]


def decls(src):
    return (sorted(set(re.findall(r"^(?:async\s+)?function\s+(\w+)", src, re.M))),
            sorted(set(re.findall(r"^const\s+(\w+)\s*=\s*\(", src, re.M))))


def func_end(src, start):
    """从函数体第一个 '{' 起做括号配平, 返回结束下标(跳过字符串与注释)。"""
    i = src.index("{", start)
    depth, n, quote = 0, len(src), None
    while i < n:
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif src.startswith("//", i):
            i = src.find("\n", i)
            if i < 0:
                break
            continue
        elif src.startswith("/*", i):
            i = src.find("*/", i) + 2
            continue
        elif ch in "\"'`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("括号不配平")


def targets(root):
    root = Path(root)
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("app.js") if "node_modules" not in str(p))


def check(root):
    bad = 0
    for f in targets(root):
        s = f.read_text(encoding="utf8", errors="replace")
        miss = [fn for fn in KEY_FUNCS if ("function " + fn) not in s]
        if miss:
            bad += 1
            print(f"  {f}: 缺少 {miss}")
    print("体检完成:", "全部完整" if bad == 0 else f"{bad} 个文件有问题")
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="app.js 或目录")
    ap.add_argument("--func", default=None, help="要替换的函数名")
    ap.add_argument("--file", default=None, help="替换后的完整函数文本文件")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--check", action="store_true", help="只体检")
    a = ap.parse_args()
    if a.check or not a.func:
        return check(a.target)
    if not a.file:
        print("需要 --file(替换后的函数文本)")
        return 2
    new_body = Path(a.file).read_text(encoding="utf8").strip()
    if ("function " + a.func) not in new_body:
        print("新函数文本里找不到 function " + a.func)
        return 2

    done = refused = 0
    for f in targets(a.target):
        s = f.read_text(encoding="utf8")
        k = s.find("function " + a.func + "(")
        if k < 0:
            print(f"  跳过(无 {a.func}): {f}")
            continue
        try:
            end = func_end(s, k)
        except ValueError as e:
            print(f"  跳过({e}): {f}")
            continue
        before = decls(s)
        s2 = s[:k] + new_body + s[end:]
        after = decls(s2)
        if before[0] != after[0] or before[1] != after[1]:
            print(f"  [护栏拦截] 函数清单会变化: {f}")
            refused += 1
            continue
        if not a.dry:
            f.write_text(s2, encoding="utf8")
        done += 1
    print(f"替换完成 {done} 个文件; 护栏拦截 {refused} 个" + ("(dry-run)" if a.dry else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
