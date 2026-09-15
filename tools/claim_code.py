# -*- coding: utf-8 -*-
"""
一次性导入码（短码）生成与校验
================================
用法:
  python tools/claim_code.py                 # 打 5 个码看看
  python tools/claim_code.py --write-mock    # 给两张示例卡各发一个"本地演示码"
  python tools/claim_code.py --check K7M2-9QX4

码的形态:
  8 位, 展示成 XXXX-XXXX, 输入时忽略横线并自动转大写。
  字符表去掉 0 O 1 I 这些看着像的, 只剩 32 个字符 → 7 位随机 + 1 位校验位。
  校验位的作用: 客户输错一位, 小程序不用联网就能立刻发现, 不会白跑一趟服务器。

算法必须和小程序端 utils/claimcode.js 完全一致(改动这里必须同步改那边)。
"""
import argparse
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOCK_JS = ROOT / "miniprogram" / "data" / "cards" / "mockcodes.js"

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"   # 32 个, 无 0 O 1 I
BODY_LEN = 7
CODE_LEN = BODY_LEN + 1


def normalize(code):
    """去掉横线空格, 转大写。"""
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def check_char(body):
    acc = 0
    for i, ch in enumerate(body):
        idx = ALPHABET.find(ch)
        if idx < 0:
            return ""
        acc = (acc + idx * (i + 1)) % len(ALPHABET)
    return ALPHABET[acc]


def make_code():
    body = "".join(secrets.choice(ALPHABET) for _ in range(BODY_LEN))
    return body + check_char(body)


def verify_code(code):
    s = normalize(code)
    if len(s) != CODE_LEN:
        return False
    if any(ch not in ALPHABET for ch in s):
        return False
    return check_char(s[:BODY_LEN]) == s[BODY_LEN]


def pretty(code):
    s = normalize(code)
    return f"{s[:4]}-{s[4:]}" if len(s) == CODE_LEN else s


def write_mock(cards, out=MOCK_JS):
    """
    本地演示码: 不连云开发也能把"输入码 → 卡片出现 → 再输一次提示已被领取"整条流程走完。
    正式环境的码由云开发登记处下发, 与这个文件无关。
    """
    codes = {make_code(): cid for cid in cards}
    lines = [
        "// 由 tools/claim_code.py --write-mock 生成, 不要手改",
        "// 仅用于本地演示(mode: 'mock'): 不连云开发也能走完导入流程。",
        "// 正式环境的导入码由云开发登记处下发, 与这个文件无关。",
        "module.exports = {",
    ]
    for code, cid in codes.items():
        lines.append(f"  {json.dumps(code)}: {json.dumps(cid)},")
    lines += ["};", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf8")
    return out, codes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", help="校验一个码")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--write-mock", action="store_true",
                    help="给示例卡生成本地演示码(写 miniprogram/data/cards/mockcodes.js)")
    ap.add_argument("--cards", nargs="*", default=["CARD-0001", "CARD-QR01"])
    args = ap.parse_args()

    if args.check:
        ok = verify_code(args.check)
        print(f"{pretty(args.check)}  {'✅ 有效' if ok else '❌ 无效'}")
        return 0 if ok else 1

    if args.write_mock:
        out, codes = write_mock(args.cards)
        print(f"已写入 {out.relative_to(ROOT)}")
        for code, cid in codes.items():
            print(f"  本地演示码 {pretty(code)}  →  {cid}")
        return 0

    print("示例导入码(展示形式, 输入时横线可省略):")
    for _ in range(args.count):
        c = make_code()
        print(f"  {pretty(c)}   {'校验通过' if verify_code(c) else '校验失败!'}")
    bad = "AAAA-AAAA"
    print(f"\n防错演示: {pretty(bad)} → {'有效' if verify_code(bad) else '无效(校验位拦下)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
