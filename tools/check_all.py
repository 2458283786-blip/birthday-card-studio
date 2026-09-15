# -*- coding: utf-8 -*-
"""
一键自检（改完小程序代码就跑这个）
====================================
开发者工具我这边跑不起来（命令行启动会超时），所以把能自动验的全放这里：

  1. require 一致性      —— 页面从模块里取的名字，那个模块真的导出了吗（这类错只在运行时炸）
  2. JS / WXS 语法       —— 全部文件
  3. JSON 合法性         —— app.json / project.config.json / 各 package.json
  4. 导入流程数据层测试   —— 用 Node 桩掉 wx, 跑真实的小程序数据层（认领/先到先得/本人重进）
  5. 打包产物完整性      —— 每张卡的素材齐不齐、体积有没有超主包上限

用法: python tools/check_all.py
"""
import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
MP = ROOT / "miniprogram"

fails = []


def title(text):
    print(f"\n=== {text} ===")


def run(cmd, cwd=ROOT):
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    # 0) 工具脚本自身的语法(免得自检脚本自己是坏的)
    title("0. Python 工具脚本语法")
    pybad = []
    for f in sorted(TOOLS.glob("*.py")):
        p = subprocess.run([sys.executable, "-m", "py_compile", str(f)],
                           capture_output=True, text=True,
                           encoding="utf8", errors="replace")
        if p.returncode != 0:
            pybad.append((f, p.stderr))
    if pybad:
        for f, err in pybad:
            print(f"  ❌ {f.name}: {(err or '').strip().splitlines()[-1][:140]}")
        fails.append("Python 语法")
    else:
        print(f"  ✅ {len(list(TOOLS.glob('*.py')))} 个脚本正常")

    # 1) require 一致性
    title("1. require 一致性")
    code, out = run([sys.executable, str(TOOLS / "check_mp_requires.py")])
    print(out.rstrip())
    if code != 0:
        fails.append("require 一致性")

    # 2) JS / WXS 语法
    title("2. JS / WXS 语法")
    js_files = sorted(MP.rglob("*.js"))
    bad = []
    for f in js_files:
        p = subprocess.run(["node", "--check", str(f)], capture_output=True,
                           text=True, encoding="utf8", errors="replace")
        if p.returncode != 0:
            bad.append((f, p.stderr))
    for f in sorted(MP.rglob("*.wxs")):
        # node 不认识 .wxs 扩展名, 用 Function() 只解析不执行
        script = ("const fs=require('fs');"
                  f"new Function(fs.readFileSync({json.dumps(str(f))},'utf8'));")
        p = subprocess.run(["node", "-e", script], capture_output=True,
                           text=True, encoding="utf8", errors="replace")
        if p.returncode != 0:
            bad.append((f, p.stderr))
    if bad:
        for f, err in bad:
            print(f"  ❌ {f.relative_to(ROOT)}")
            print("     " + (err or "").strip().splitlines()[-1][:160])
        fails.append("语法")
    else:
        print(f"  ✅ {len(js_files)} 个 JS + WXS 全部通过")

    # 3) JSON
    title("3. JSON 合法性")
    jbad = []
    for f in list(MP.rglob("*.json")) + [ROOT / "mp-secret.example.json"]:
        try:
            json.loads(f.read_text(encoding="utf8"))
        except Exception as e:
            jbad.append((f, e))
    if jbad:
        for f, e in jbad:
            print(f"  ❌ {f.relative_to(ROOT)}: {e}")
        fails.append("JSON")
    else:
        print("  ✅ 全部 JSON 正常")

    # 4) 数据层测试
    title("4. 导入流程数据层测试（Node 桩 wx, 跑真实代码）")
    code, out = run(["node", str(TOOLS / "test_mp_datalayer.js")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-3:]:
        print("  " + line)
    if code != 0:
        print(out)
        fails.append("数据层测试")

    # 4b) 云函数测试
    title("4b. 云函数测试（先到先得 / 防多领, 跑真实云函数代码）")
    code, out = run(["node", str(TOOLS / "test_cloud_claim.js")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-3:]:
        print("  " + line)
    if code != 0:
        print(out)
        fails.append("云函数测试")

    # 4c) 端到端契约测试(需要一份发布记录当夹具)
    title("4c. 端到端契约（工作台发布记录 → 云函数 → 小程序视图）")
    fixtures = list((ROOT / "publish").glob("*/record.json")) \
        if (ROOT / "publish").exists() else []
    if not fixtures:
        print("  ⏭  跳过: 还没有发布记录, 先跑")
        print("     python tools/publish_to_mp.py CARD-0001 --dry-run")
    else:
        code, out = run(["node", str(TOOLS / "test_cloud_e2e.js")])
        tail = [l for l in out.strip().splitlines() if l.strip()]
        for line in tail[-3:]:
            print("  " + line)
        if code != 0:
            print(out)
            fails.append("端到端契约测试")

    # 4d) 真发布路径(本地假服务器冒充微信接口)
    title("4d. 真发布路径（上传素材 + 写数据库, 用本地假服务器验证）")
    code, out = run([sys.executable, str(TOOLS / "test_publish_upload.py")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-2:]:
        print("  " + line)
    if code != 0:
        print(out)
        fails.append("真发布路径测试")

    # 5) 打包产物
    title("5. 打包产物完整性与体积")
    pkgs = MP / "data" / "packages"
    manifest_file = MP / "data" / "cards" / "manifest.js"
    if not manifest_file.exists():
        print("  ❌ 没有 manifest.js, 先跑 python tools/build_mp_packages.py")
        fails.append("打包产物")
    else:
        # 用 node 去 require 这个模块再转成 JSON —— 比在 Python 里手工解析 JS 靠谱
        code, out = run(["node", "-e",
                         "console.log(JSON.stringify("
                         "require('./miniprogram/data/cards/manifest.js').cards))"])
        if code != 0:
            print("  ❌ 读不出 manifest.js")
            print("  " + out.strip()[:300])
            fails.append("打包产物")
            cards = []
        else:
            cards = json.loads(out.strip().splitlines()[-1])
        total = sum(f.stat().st_size for f in MP.rglob("*") if f.is_file())
        for c in cards:
            miss = []
            for rel in [c["front"]] + ([c["back"]] if c["back"] else []) \
                    + list(c["layers"].values()):
                if not (MP / rel.lstrip("/")).exists():
                    miss.append(rel)
            flag = "✅" if not miss else "❌"
            print(f"  {flag} {c['displayId']:12s} 分层{len(c['layers'])} "
                  f"背面={'有' if c['back'] else '无'} "
                  f"{'' if not miss else '缺: ' + ', '.join(miss)}")
            if miss:
                fails.append(f"{c['displayId']} 素材缺失")
        print(f"  小程序目录合计 {total / 1024:.0f} KB / 主包上限 2048 KB")
        if total > 2048 * 1024:
            print("  ❌ 超过主包上限, 需要分包")
            fails.append("体积超限")

    print()
    if fails:
        print("❌ 自检未通过: " + "、".join(fails))
        return 1
    print("✅ 自检全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
