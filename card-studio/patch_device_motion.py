# -*- coding: utf-8 -*-
"""
Device Motion(陀螺仪)补丁 + 查看器工具条修复
==========================================
1. 新增陀螺仪交互: 手机倾斜驱动卡片视角; iOS 需用户手势授权; 不支持/被拒 → 自动回落 Touch Drag
   (文档 §3 保留能力 / §16 交互项 / §87 回退链)
2. 工具条: 新增「陀螺仪」按钮(模板与所有项目的 index.html)
3. 顺手修: 图标名 kebab-case → PascalCase 归一(之前工具条图标其实没渲染)
4. 顺手修: 自动/暂停按钮 replaceChildren 会把文字标签吃掉 → 现在保留标签

只改 app.js(单一来源)与 index.html; 之后由 rebuild_bundles.py 重建 bundle。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------- app.js ----------------
P1_OLD = """    const name = el.getAttribute("data-lucide");
    const tree = icons[name];"""
P1_NEW = """    const name = el.getAttribute("data-lucide");
    // 图标键是 PascalCase("Rotate3d"), 页面写 kebab-case("rotate-3d"), 归一后再取
    const pascal = name.replace(/(^|-)([a-z0-9])/g, (_m, _p, c) => c.toUpperCase());
    const tree = icons[name] || icons[pascal];"""

P2_OLD = """  $("auto").replaceChildren();
  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", auto ? "pause" : "play");
  $("auto").append(icon);
  refreshIcons();"""
P2_NEW = """  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", auto ? "pause" : "play");
  const label = document.createElement("span");
  label.className = "btn-label";
  label.textContent = auto ? "暂停" : "自动";
  $("auto").replaceChildren(icon, label);
  refreshIcons();"""

P3_OLD = """    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", value ? "pause" : "play");
    b.replaceChildren(icon);
    refreshIcons();"""
P3_NEW = """    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", value ? "pause" : "play");
    const label = document.createElement("span");
    label.className = "btn-label";
    label.textContent = value ? "暂停" : "自动";
    b.replaceChildren(icon, label);
    refreshIcons();"""

MOTION_JS = """// ---- Device Motion(陀螺仪): 增强交互; 不支持或被拒时自动回落 Touch Drag ----
let motionOn = false, motionState = "off";
const motionVals = { pitch: 0, roll: 0 };
function motionAllowed() {
  const it = (config && config.interaction) || {};
  return it.deviceMotion !== false && typeof window.DeviceOrientationEvent !== "undefined";
}
function onOrientation(e) {
  if (e.beta === null && e.gamma === null) return;
  const strength = Math.max(0, Math.min(1.5, Number((config?.parameters || {}).motionStrength ?? 0.75)));
  const beta = Number.isFinite(e.beta) ? e.beta : 45;
  const gamma = Number.isFinite(e.gamma) ? e.gamma : 0;
  motionVals.pitch = Math.max(-1, Math.min(1, (beta - 45) / 40)) * strength;
  motionVals.roll = Math.max(-1, Math.min(1, gamma / 40)) * strength;
  if (auto) setAuto(false);              // 陀螺仪接管时关掉自动巡游
}
function startMotion() {
  window.addEventListener("deviceorientation", onOrientation, true);
  motionOn = true;
  motionState = "on";
  syncMotionButton();
}
function stopMotion() {
  window.removeEventListener("deviceorientation", onOrientation, true);
  motionOn = false;
  motionState = "off";
  motionVals.pitch = 0;
  motionVals.roll = 0;
  syncMotionButton();
}
async function enableMotion() {
  if (!motionAllowed()) {
    motionState = "unsupported";
    syncMotionButton();
    notice("此设备/浏览器不支持陀螺仪, 可继续拖拽卡片");
    return false;
  }
  const DOE = window.DeviceOrientationEvent;
  if (typeof DOE.requestPermission === "function") {
    try {
      const res = await DOE.requestPermission();
      if (res !== "granted") {
        motionState = "denied";
        syncMotionButton();
        notice("未授权陀螺仪, 仍可用拖拽");
        return false;
      }
    } catch (err) {
      motionState = "denied";
      syncMotionButton();
      notice("陀螺仪授权失败, 仍可用拖拽");
      return false;
    }
  }
  startMotion();
  notice("陀螺仪已开启: 倾斜手机看层次");
  return true;
}
function syncMotionButton() {
  const b = $("motion");
  if (!b) return;
  b.disabled = false;
  b.setAttribute("aria-pressed", String(motionOn));
  b.title = motionState === "unsupported" ? "本设备不支持陀螺仪"
    : (motionOn ? "关闭陀螺仪" : "开启陀螺仪");
  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", motionOn ? "rotate-ccw" : "rotate-3d");
  const label = document.createElement("span");
  label.className = "btn-label";
  label.textContent = motionOn ? "关闭陀螺仪" : "陀螺仪";
  b.replaceChildren(icon, label);
  refreshIcons();
}
function wireMotionButton() {
  const b = $("motion");
  if (!b) return;
  syncMotionButton();
  b.onclick = () => (motionOn ? stopMotion() : enableMotion());
}
"""

P4_OLD = "function animate(now) {"
P4_NEW = MOTION_JS + "function animate(now) {"

P5_OLD = """  if (auto) {
    targetY = Math.sin(elapsed * 0.42) * 0.23 - 0.055;
    targetX = Math.sin(elapsed * 0.53) * 0.055 - 0.018;
  }"""
P5_NEW = P5_OLD + """
  if (motionOn && !dragging) {          // 陀螺仪优先于自动巡游
    const motionBase = flipped ? Math.PI : 0;
    targetY = motionBase + motionVals.roll * 0.60;
    targetX = -motionVals.pitch * 0.34;
  }"""

P6_OLD = """    if (sway && now - lastMove > 1500) {
      const t = now / 1000;
      tx = Math.sin(t * 0.7) * 0.07 + 0.05;
      ty = Math.sin(t * 0.55) * 0.11 - 0.18;
    }"""
P6_NEW = P6_OLD + """
    if (motionOn) {                     // 陀螺仪(CSS-3D 回退路径)
      tx = -motionVals.pitch * 0.30;
      ty = motionVals.roll * 0.45;
    }"""

P7_OLD = """  $("auto").disabled = false;
  $("auto").onclick = () => setAutoUI(!sway);"""
P7_NEW = P7_OLD + "\n  wireMotionButton();"

P8_OLD = """  $("auto").onclick = () => {
    if (flipped) flip(false);
    setAuto(!auto);
  };"""
P8_NEW = P8_OLD + "\n  wireMotionButton();"

APP_REPL = [
    (P1_OLD, P1_NEW, "PascalCase", "图标名归一"),
    (P2_OLD, P2_NEW, 'label.textContent = auto ? "暂停" : "自动";', "自动按钮保留标签"),
    (P3_OLD, P3_NEW, 'label.textContent = value ? "暂停" : "自动";', "回退路径按钮保留标签"),
    (P4_OLD, P4_NEW, "function motionAllowed()", "陀螺仪模块"),
    (P5_OLD, P5_NEW, "陀螺仪优先于自动巡游", "WebGL 渲染循环接入"),
    (P6_OLD, P6_NEW, "CSS-3D 回退路径", "回退路径接入"),
    (P7_OLD, P7_NEW, "wireMotionButton();\n}\nconst fallbackFinish", "回退路径接线"),
    (P8_OLD, P8_NEW, "wireMotionButton();\n  $(\"flip\").onclick = () => flip();", "WebGL 路径接线"),
]

# ---------------- index.html ----------------
BTN_ANCHOR = """          <button
            class="icon-button"
            id="flip\""""
BTN_NEW = """          <button
            class="icon-button"
            id="motion"
            aria-label="陀螺仪"
            title="陀螺仪(手机倾斜控制)"
            aria-pressed="false"
            disabled
          >
            <i data-lucide="rotate-3d"></i><span class="btn-label">陀螺仪</span>
          </button>
          <button
            class="icon-button"
            id="flip\""""


def patch_app(p):
    s = p.read_text(encoding="utf8")
    out = []
    for old, new, marker, label in APP_REPL:
        if marker in s:
            out.append(f"{label}:已存在")
            continue
        n = s.count(old)
        if n != 1:
            out.append(f"{label}:锚点{n}跳过")
            continue
        s = s.replace(old, new)
        out.append(f"{label}:OK")
    p.write_text(s, encoding="utf8")
    return out


def patch_html(p):
    s = p.read_text(encoding="utf8")
    if 'id="motion"' in s:
        return "已存在"
    if BTN_ANCHOR not in s:
        return "锚点缺失"
    p.write_text(s.replace(BTN_ANCHOR, BTN_NEW, 1), encoding="utf8")
    return "OK"


def web_dirs():
    out = [ROOT / "RuiC-card-skill-main" / "assets" / "web-template"]
    for d in ("demo-koi", "demo-birthday"):
        w = ROOT / d / "web"
        if w.is_dir():
            out.append(w)
    for sub in (ROOT / "birthday-set").glob("*"):
        if (sub / "app.js").exists():
            out.append(sub)
    for d in ("birthday-build", "card-studio/projects"):
        for sub in (ROOT / d).glob("*"):
            if (sub / "web").is_dir():
                out.append(sub / "web")
    return out


def main():
    for w in web_dirs():
        app = w / "app.js"
        if app.exists():
            print(f"{w.relative_to(ROOT)}  app.js: " + "  ".join(patch_app(app)))
        html = w / "index.html"
        if html.exists():
            print(f"{w.relative_to(ROOT)}  index.html: {patch_html(html)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
