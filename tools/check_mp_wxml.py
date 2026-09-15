# -*- coding: utf-8 -*-
"""
WXML 静态检查（专抓"不报错但没反应"的那类问题）
================================================
小程序的这几种错误都不会让页面崩, 只会**静默失效** —— 跑不起开发者工具就很难发现:

  1. bindtap 绑了一个 JS 里不存在的方法   → 点了没反应, 只在控制台留个警告
  2. 绑了 WXS 里不存在的函数              → 拖不动, 无声无息
  3. class 名拼错 / 样式没写               → 元素没样式, 看着"就是不对劲"
  4. 用了自定义组件但 .json 里没声明 usingComponents → 标签被当普通 view, 内容消失

用法: python tools/check_mp_wxml.py
"""
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
MP = ROOT / "miniprogram"

BIND = re.compile(r'(?:bind|catch|capture-bind|capture-catch|mut-bind)[:]?'
                  r'(?:tap|touchstart|touchmove|touchend|touchcancel|longpress|longtap|'
                  r'input|confirm|change|submit|error|load|scroll|scrolltolower|'
                  r'getuserinfo|chooseavatar|blur|focus|columnchange)\s*=\s*"([^"]+)"')
CLASS_ATTR = re.compile(r'class\s*=\s*"([^"]*)"')
WXS_TAG = re.compile(r'<wxs\s+module\s*=\s*"([^"]+)"\s+src\s*=\s*"([^"]+)"')
TAG = re.compile(r'<([a-z][a-z0-9-]*)[\s/>]')
QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")
BUILTIN_TAGS = {
    "view", "text", "image", "button", "input", "scroll-view", "swiper", "swiper-item",
    "block", "canvas", "navigator", "textarea", "form", "label", "picker", "slider",
    "switch", "checkbox", "radio", "icon", "progress", "rich-text", "video", "audio",
    "camera", "map", "web-view", "wxs", "template", "import", "include", "slot",
    "movable-area", "movable-view", "cover-view", "cover-image", "open-data",
    "official-account", "ad", "page-meta", "navigation-bar", "share-element",
}
problems = []
HOOKS = set()      # 由 wxs_selectors() 填: WXS 用 selectComponent 选的类名


def js_defines(js_text, name):
    """JS 里有没有这个方法/属性(Page/Component 的 methods 都算)"""
    return re.search(r'(^|[\s,{])' + re.escape(name) + r'\s*[:(]\s*(function|\()?', js_text) \
        or re.search(r'\b' + re.escape(name) + r'\s*:\s*', js_text)


def wxs_defines(wxs_text, name):
    if re.search(r'function\s+' + re.escape(name) + r'\s*\(', wxs_text):
        return True
    if re.search(r'(^|[\s,{])' + re.escape(name) + r'\s*:\s*', wxs_text):
        return True
    m = re.search(r'module\.exports\s*=\s*\{([^}]*)\}', wxs_text)
    if m and re.search(r'\b' + re.escape(name) + r'\b', m.group(1)):
        return True
    return False


def wxss_classes(*files):
    names = set()
    for f in files:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf8", errors="replace")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for m in re.finditer(r"\.([A-Za-z_][\w-]*)", text):
            names.add(m.group(1))
    return names


def class_tokens(raw):
    """从 class 属性里取出静态类名。
    只认三目结果里的字符串字面量 —— 条件部分里的字符串(比如 tipKind === 'warn')
    是判断值, 不是类名。
    返回 (静态类名集合, 动态前缀集合)：
      class="foil finish-{{finish}}" 里的 "finish-" 是动态前缀,
      静态没法知道最终类名, 但可以要求样式里存在 finish-* 这一族。
    """
    out = set()
    for chunk in re.split(r"\{\{.*?\}\}", raw):
        for tok in chunk.split():
            out.add(tok)
    for m in re.finditer(r"\{\{(.*?)\}\}", raw):
        expr = m.group(1)
        parts = re.split(r"[?:]", expr)
        for piece in parts[1:]:
            for q in QUOTED.finditer(piece):
                for tok in (q.group(1) or q.group(2) or "").split():
                    out.add(tok)

    # 与 {{...}} 直接相连(中间没空格)的片段 = 动态前缀/后缀
    marker = "\x00"
    flat = re.sub(r"\{\{.*?\}\}", marker, raw)
    prefixes = set()
    for m in re.finditer(r"[^\s" + marker + r"]*" + marker + r"[^\s" + marker + r"]*", flat):
        pieces = m.group(0).split(marker)
        for i, piece in enumerate(pieces):
            if piece and (i == 0 or i == len(pieces) - 1):
                prefixes.add(piece)
    out = {t for t in out if t and not t.startswith("{{") and "}" not in t}
    return out, prefixes


def wxs_selectors():
    """所有 .wxs 里用 selectComponent('.x') 选过的类 —— 这些是"钩子类",
    只要出现在 WXML 里就行, 不需要样式。"""
    hooks = set()
    for f in MP.rglob("*.wxs"):
        text = f.read_text(encoding="utf8", errors="replace")
        for m in re.finditer(r"selectComponent\(\s*['\"]\.([\w-]+)['\"]\s*\)", text):
            hooks.add(m.group(1))
    return hooks


def check_file(wxml):
    base = wxml.with_suffix("")
    js = base.with_suffix(".js")
    wxss = base.with_suffix(".wxss")
    cfg = base.with_suffix(".json")
    js_text = js.read_text(encoding="utf8", errors="replace") if js.exists() else ""
    wxml_text = wxml.read_text(encoding="utf8", errors="replace")
    rel = wxml.relative_to(ROOT)

    # 样式来源: 页面自己的 + 全局(组件用 apply-shared 也会吃到全局)
    defined = wxss_classes(wxss, MP / "app.wxss")

    # 1/2) 事件绑定
    wxs_modules = {}
    for m in WXS_TAG.finditer(wxml_text):
        mod, src = m.group(1), m.group(2)
        wxs_path = (wxml.parent / src).resolve()
        wxs_modules[mod] = wxs_path.read_text(encoding="utf8", errors="replace") \
            if wxs_path.exists() else None
        if wxs_modules[mod] is None:
            problems.append(f"{rel}: <wxs module=\"{mod}\" src=\"{src}\"> 文件不存在")

    for m in BIND.finditer(wxml_text):
        value = m.group(1).strip()
        inner = value
        mm = re.match(r"\{\{\s*(.*?)\s*\}\}", value)
        if mm:
            inner = mm.group(1)
        if "." in inner and not inner.startswith("this."):
            mod, fn = inner.split(".", 1)
            fn = fn.strip().rstrip("()")
            if mod in wxs_modules:
                if wxs_modules[mod] is None:
                    continue
                if not wxs_defines(wxs_modules[mod], fn):
                    problems.append(f"{rel}: 绑了 WXS 函数 {{{mod}.{fn}}}, 但那个文件里没有")
            continue
        fn = inner.rstrip("()").strip()
        if not fn or fn.startswith("(") or "?" in fn:
            continue
        if fn not in js_text:
            problems.append(f"{rel}: 绑了方法 {fn}(), 但 {js.name} 里找不到")
        elif not js_defines(js_text, fn):
            problems.append(f"{rel}: 绑了方法 {fn}(), 但 {js.name} 里看起来不是方法")

    # 3) class
    used = set()
    prefixes = set()
    for m in CLASS_ATTR.finditer(wxml_text):
        u, p = class_tokens(m.group(1))
        used |= u
        prefixes |= p
    # WXML 里可以写 <!-- check-mp-wxml: allow xxx yyy --> 明确说明"这个类不需要样式"
    allowed = set()
    for m in re.finditer(r"check-mp-wxml:\s*allow\s+([\w\s-]+?)\s*-->", wxml_text):
        allowed |= set(m.group(1).split())
    for name in sorted(used):
        if name in defined or name in HOOKS or name in allowed:
            continue
        if name in prefixes:
            continue                      # 动态前缀单独判
        if re.fullmatch(r"\{\{.*\}\}", name):
            continue
        problems.append(f"{rel}: class=\"{name}\" 在任何 wxss 里都没定义（拼错了？）")
    # 动态前缀: 要求样式里存在 "前缀*" 这一族(能抓住 finish- 写成 finsh- 这类错)
    for pre in sorted(prefixes):
        if pre in allowed or pre.endswith("-") is False:
            continue
        if not any(c.startswith(pre) for c in defined | HOOKS):
            problems.append(
                f"{rel}: class=\"{pre}{{{{...}}}}\" 拼出来的类名在 wxss 里找不到（前缀 \"{pre}\" 对不对？）")

    # 4) 自定义组件声明
    declared = set()
    if cfg.exists():
        try:
            declared = set((json.loads(cfg.read_text(encoding="utf8"))
                            .get("usingComponents") or {}).keys())
        except Exception as e:
            problems.append(f"{rel}: {cfg.name} 解析失败 {e}")
    for m in TAG.finditer(wxml_text):
        tag = m.group(1)
        if tag in BUILTIN_TAGS or tag in declared:
            continue
        if "-" in tag and tag not in BUILTIN_TAGS:
            problems.append(f"{rel}: 用了 <{tag}>, 但 {cfg.name} 的 usingComponents 里没声明")


def main():
    global HOOKS
    HOOKS = wxs_selectors()
    files = sorted(MP.rglob("*.wxml"))
    for f in files:
        check_file(f)
    print(f"检查了 {len(files)} 个 wxml"
          + (f"（其中 {len(HOOKS)} 个类名是 WXS 选择钩子, 不要求有样式）" if HOOKS else ""))
    if problems:
        print(f"\n❌ 发现 {len(problems)} 个问题:")
        for p in problems:
            print("  -", p)
        return 1
    print("✅ 事件绑定、class、自定义组件声明都没问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
