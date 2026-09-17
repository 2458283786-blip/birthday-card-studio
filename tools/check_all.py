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

⚠️ 在 Windows 的 PowerShell 里跑, 请把输出重定向到文件再看:
      python tools/check_all.py > out.txt 2>&1; Get-Content out.txt
   直接接管道( | Select-String ... )会打断子进程(node)的输出,
   表现为"某个测试失败"的假故障 —— 不是代码坏了。
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


def ok_or_flaky(code, out):
    """node 子进程偶发非 0 退出(管道问题, 见文件头说明) → 只要结果全通过就算通过。"""
    if code == 0:
        return True
    import re as _re
    m = _re.search(r"结果:\s*\d+\s*通过\s*/\s*(\d+)\s*失败", out or "")
    return bool(m) and int(m.group(1)) == 0

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

    # 1b) WXML 静态检查
    title("1b. WXML（事件绑定 / class / 自定义组件声明）")
    code, out = run([sys.executable, str(TOOLS / "check_mp_wxml.py")])
    print(out.rstrip())
    if code != 0:
        fails.append("WXML 检查")

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
    title("3. JSON 合法性 + 编码(不能有 BOM)")
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
    # BOM 会让小程序编译器偶尔犯迷糊, 顺手扫一遍
    bom = [f for f in MP.rglob("*")
           if f.is_file() and f.suffix in (".wxml", ".wxss", ".js", ".json", ".wxs")
           and f.read_bytes().startswith(b"\xef\xbb\xbf")]
    if bom:
        for f in bom:
            print(f"  ❌ {f.relative_to(ROOT)} 带 UTF-8 BOM")
        fails.append("BOM")
    else:
        print("  ✅ 没有文件带 BOM")

    # 3b) 卡牌数学(两份实现是否一致 + 手算参考值)
    title("3b. 卡牌数学（视差 / 材质门控, cardmath.js ↔ holo.wxs）")
    code, out = run(["node", str(TOOLS / "test_cardmath.js")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-2:]:
        print("  " + line)
    if not ok_or_flaky(code, out):
        print(out)
        fails.append("卡牌数学测试")

    # 4) 数据层测试
    title("4. 导入流程数据层测试（Node 桩 wx, 跑真实代码）")
    code, out = run(["node", str(TOOLS / "test_mp_datalayer.js")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-3:]:
        print("  " + line)
    if not ok_or_flaky(code, out):
        print(out)
        fails.append("数据层测试")

    # 4b) 云函数测试
    title("4b. 云函数测试（先到先得 / 防多领, 跑真实云函数代码）")
    code, out = run(["node", str(TOOLS / "test_cloud_claim.js")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-3:]:
        print("  " + line)
    if not ok_or_flaky(code, out):
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
    if not ok_or_flaky(code, out):
        print(out)
        fails.append("真发布路径测试")

    # 4e) 素材缓存
    title("4e. 素材缓存（离线可看 / 秒开 / 失败不影响显示）")
    code, out = run(["node", str(TOOLS / "test_cache.js")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-2:]:
        print("  " + line)
    if not ok_or_flaky(code, out):
        print(out)
        fails.append("素材缓存测试")

    # 4f) 自由文本转义(寄语里的引号/换行/emoji 会不会把写库语句拼坏)
    title("4f. 内容转义（丑字段写进云数据库不能变形）")
    code, out = run([sys.executable, str(TOOLS / "test_publish_escaping.py")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-2:]:
        print("  " + line)
    if code != 0:
        print(out)
        fails.append("内容转义测试")

    # 5) 打包产物
    title("5. 打包器（含「工作台改了我不认识」的探测）")
    code, out = run([sys.executable, str(TOOLS / "test_build_packages.py")])
    tail = [l for l in out.strip().splitlines() if l.strip()]
    for line in tail[-2:]:
        print("  " + line)
    if code != 0:
        print(out)
        fails.append("打包器测试")

    title("5b. 打包产物完整性与体积")
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


    # ---------------------------------------------------------------- 6) V2 生成链路回归
    title("6. V2 生成链路(语言 / 分层 / 评审 / schema)")
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "card-studio"))
        sys.path.insert(0, str(ROOT / "card-studio" / "dl2"))
        import design
        import art_director
        import photodna
        import visual_critic
        import card_schema

        # 找一张可用于测试的照片(优先小图)
        photo = None
        for cand in sorted((ROOT / "card-studio" / "projects").glob("card-*/_upload.png")) + \
                    sorted((ROOT / "card-studio" / "projects").glob("card-*/assets/source.png")):
            photo = cand
            break
        if photo is None:
            print("  ⚠️  找不到测试照片(先在工作台生成一张卡), 跳过 V2 回归")
        else:
            # 缩到小画布跑(快) —— 只验证代码路径, 不验证观感
            W0, H0 = design.W, design.H
            design.W, design.H = 256, 384
            dna, _ = photodna.analyze(photo)
            ranked = art_director.score_languages(dna)
            ok_rank = (len(ranked) == 5 and all(0.0 <= r["score"] <= 1.0 for r in ranked)
                       and all(r["lang"] for r in ranked))
            print(f"  {'✅' if ok_rank else '❌'} 语言打分: {len(ranked)} 套, 分数区间 0~1"
                  f" | 最高 {ranked[0]['lang']}={ranked[0]['score']:.2f}")
            if not ok_rank:
                fails.append("V2 语言打分")

            langs = ("portrait", "cyber", "editorial", "memory", "cinema")
            bad = []
            for lang in langs:
                try:
                    out, spec = design.build(str(photo), {"name": "T", "subtitle": "S",
                                                          "edition": "CARD #0001",
                                                          "technique": "2026.01.01"},
                                             lang=lang, out_dir=str(ROOT / "dl2" / "out" / "_regress"))
                    from PIL import Image as _I
                    im = _I.open(out)
                    if im.size[0] * 3 != im.size[1] * 2 or im.size[0] < 200:
                        bad.append(f"{lang}(尺寸 {im.size})")
                except Exception as e:
                    bad.append(f"{lang}({type(e).__name__})")
            print(f"  {'✅' if not bad else '❌'} 五套语言渲染: "
                  f"{'全部通过' if not bad else '失败 ' + ', '.join(bad)}")
            if bad:
                fails.append("V2 语言渲染")

            full, spec = design.build(str(photo), {"name": "T", "subtitle": "S",
                                                   "edition": "CARD #0001",
                                                   "technique": "2026.01.01"},
                                      lang="portrait", out_dir=str(ROOT / "dl2" / "out" / "_regress"),
                                      layers_dir=str(ROOT / "dl2" / "out" / "_regress" / "L"))
            lay = sorted(f.name for f in (ROOT / "dl2" / "out" / "_regress" / "L").glob("*.png"))
            ok_lay = all(n in lay for n in ("background.png", "subject.png", "text.png"))
            print(f"  {'✅' if ok_lay else '❌'} PORTRAIT 分层输出: {lay}")
            if not ok_lay:
                fails.append("V2 分层输出")
            design.W, design.H = W0, H0

            # 评审(只跑程序侧, 不调 AI) —— 需要一个含 assets/front.png 的项目
            target = None
            for cand in sorted((ROOT / "card-studio" / "projects").glob("card-*")):
                if (cand / "assets" / "front.png").exists():
                    target = cand
                    if (cand / "assets" / "text.png").exists():
                        break
            if target is None:
                print("  ⚠️  没有含 assets/front.png 的项目, 跳过评审回归")
            else:
                rep = visual_critic.program_checks(target)
                ok_rep = bool(rep.get("ok")) and len(rep.get("checks", [])) >= 3
                print(f"  {'✅' if ok_rep else '❌'} Visual Critic 程序检查: "
                      f"{len(rep.get('checks', []))} 项 ({target.name})")
                if not ok_rep:
                    fails.append("V2 评审")

        # schema v2 超集
        cj = card_schema.build_card_json(ROOT / "card-studio" / "projects" / "card-mu2o5m1y",
                                         "CARD #0001")
        need = ("schemaVersion", "occasion", "designLanguage", "content", "metadata", "collection")
        miss = [k for k in need if k not in cj]
        ok_cj = (cj.get("schemaVersion") == "2.0") and not miss and "note" in (cj.get("content") or {})
        print(f"  {'✅' if ok_cj else '❌'} card.json v2 超集: schema={cj.get('schemaVersion')} "
              f"{'缺 ' + ','.join(miss) if miss else '字段齐'}")
        if not ok_cj:
            fails.append("V2 schema")

        # 服务在线时的接口冒烟(不在线不算失败)
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:4399/api/ai-status", timeout=4) as r:
                st = json.loads(r.read().decode("utf8"))
            print(f"  ✅ 工坊在线: AI={'已配' if st.get('available') else '未配'}(model={st.get('model')})")
        except Exception:
            print("  ⚠️  工坊未启动, 跳过接口冒烟(不影响结论)")
    except Exception as e:
        print(f"  ❌ V2 回归异常: {type(e).__name__}: {e}")
        fails.append("V2 回归异常")

    print()
    print()
    if fails:
        print("❌ 自检未通过: " + "、".join(fails))
        return 1
    print("✅ 自检全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
