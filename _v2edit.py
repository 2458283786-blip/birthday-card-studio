# -*- coding: utf-8 -*-
"""
apply_config_edits: V2 卡专用路径
================================
V2 卡(designLanguage 有值 / _provenance.template == "v2")不能用旧模板渲染器重画
旧路径会把 backStyle=night 当模板跑 birthday_system → 覆盖 V2 卡面。
做法:
  * 文本字段变了(姓名/副标题/日期/编号/卡名) → 调 dl2/build_card.py 按 designLanguage 重出
  * 只改了材质/光泽/景深/底色等 → 只更新配置并同步 web 副本(秒回, 不重渲染)
"""
from pathlib import Path

P = Path("card-studio/apply_config_edits.py")
s = P.read_text(encoding="utf8")

old = '''    tpl = (cfg.get("_provenance") or {}).get("template") or cfg.get("backStyle") or "studio"
    image = find_image(project)
    print(f"[编辑] 模板={tpl} 改动字段={changed or '无'} 图片={image.name if image else '缺失'}")
'''
new = '''    tpl = (cfg.get("_provenance") or {}).get("template") or cfg.get("backStyle") or "studio"
    image = find_image(project)
    print(f"[编辑] 模板={tpl} 改动字段={changed or '无'} 图片={image.name if image else '缺失'}")

    # ---- V2 卡: 用 dl2/build_card.py 重出, 不碰旧模板渲染器 ----
    lang = str(cfg.get("designLanguage") or "").strip()
    is_v2 = bool(lang) or tpl == "v2"
    if is_v2:
        text_keys = {"name", "title", "subtitle", "technique", "edition", "date"}
        need_redraw = bool(text_keys & set(edits.keys()))
        if not need_redraw:
            print("[编辑] V2 卡且只改了外观参数 → 仅更新配置(无需重渲染)")
            return 0
        if not lang:
            lang = "portrait"
        print(f"[编辑] V2 卡文本变化 → 按 {lang} 重出")
        r = subprocess.run([sys.executable, "-u", str(HERE / "dl2" / "build_card.py"),
                            str(project), "--lang", lang,
                            "--viewer-from", str(PROJECTS_REF)], cwd=str(ROOT))
        # 静态预览缩略图
        subprocess.run([sys.executable, "-u", str(HERE / "make_static_card.py"), str(project)],
                       cwd=str(ROOT), capture_output=True)
        return r.returncode
'''
if old in s and "V2 卡且只改了外观参数" not in s:
    s = s.replace(old, new, 1)
    # PROJECTS_REF 常量
    if "PROJECTS_REF" not in s:
        s = s.replace("ROOT = ", "PROJECTS_REF = None\nROOT = ", 1)
    P.write_text(s, encoding="utf8")
    print("V2 路径: OK")
else:
    print("未命中/已存在")
