# -*- coding: utf-8 -*-
"""
生日收藏卡 · 查看器定制(仅作用于 demo-birthday/web, 不影响其他项目)
=====================================================================
1) 重画背板 backTexture(): 深蓝黑 + 双线金框 + 四角星芒
   —— 大量留白, 预留 CARD # / 卡名 / 日期 / CREATED BY / OWNED BY / 祝福
   —— 提供年龄时, 以极淡的大号数字作为"专属水印"
2) 虹彩降饱和: 高级金属感, 不廉价
3) index.html: 去品牌化 + 注入 pose.js
4) pose.js: ?pose=front|tilt|holo|back 四态 + &embed=1 纯净卡片视图
5) style.css: 深色高级主题
6) showcase.html: 2x2 四态展示页
"""
from pathlib import Path

WEB = Path("demo-birthday/web")

BACK_NEW = r'''function backTexture() {
  const c = document.createElement("canvas");
  c.width = 1024;
  c.height = 1536;
  const ctx = c.getContext("2d");
  const star = (x, y, r, alpha, ratio) => {
    const k = ratio || 0.22;
    ctx.beginPath();
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r * k, y - r * k);
    ctx.lineTo(x + r, y);
    ctx.lineTo(x + r * k, y + r * k);
    ctx.lineTo(x, y + r);
    ctx.lineTo(x - r * k, y + r * k);
    ctx.lineTo(x - r, y);
    ctx.lineTo(x - r * k, y - r * k);
    ctx.closePath();
    ctx.fillStyle = "rgba(222,201,160," + alpha + ")";
    ctx.fill();
  };
  const tracked = (text, cx, y, fnt, tracking, color) => {
    ctx.font = fnt;
    ctx.fillStyle = color;
    const chars = [...String(text)];
    const w = chars.reduce((s, ch) => s + ctx.measureText(ch).width, 0) + tracking * (chars.length - 1);
    let x = cx - w / 2;
    for (const ch of chars) { ctx.fillText(ch, x, y); x += ctx.measureText(ch).width + tracking; }
  };
  const field = (label, y, value) => {
    tracked(label, 512, y, "12px 'Segoe UI', Arial", 3.2, "rgba(139,132,116,.92)");
    if (value) {
      tracked(value, 512, y + 30, "17px 'Segoe UI', Arial", 1, "rgba(232,217,181,.94)");
    } else {
      ctx.strokeStyle = "rgba(222,201,160,.22)";
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(412, y + 26); ctx.lineTo(612, y + 26); ctx.stroke();
    }
  };
  const g = ctx.createLinearGradient(0, 0, 0, 1536);
  g.addColorStop(0, "#0e1526"); g.addColorStop(0.55, "#0a0f1c"); g.addColorStop(1, "#070a12");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 1024, 1536);
  ctx.globalAlpha = 0.055;
  for (let i = 0; i < 170; i++) {
    const y = Math.random() * 1536, x0 = Math.random() * 620, len = 140 + Math.random() * 320;
    ctx.strokeStyle = i % 2 ? "#8fa2c4" : "#c9b184";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(Math.min(1024, x0 + len), y); ctx.stroke();
  }
  ctx.globalAlpha = 1;
  ctx.beginPath(); ctx.arc(512, 800, 300, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(222,201,160,.07)"; ctx.lineWidth = 1; ctx.stroke();
  ctx.strokeStyle = "rgba(222,201,160,.80)"; ctx.lineWidth = 2; ctx.strokeRect(38, 38, 948, 1460);
  ctx.strokeStyle = "rgba(168,135,79,.50)"; ctx.lineWidth = 1; ctx.strokeRect(56, 56, 912, 1424);
  [[86, 86], [938, 86], [86, 1450], [938, 1450]].forEach(([x, y]) => star(x, y, 7, 0.78, 0.2));

  // 顶部: 主题 + 固定身份标识
  tracked(config.subtitle || "HAPPY BIRTHDAY", 512, 236, "600 24px 'Segoe UI', Arial", 11, "rgba(232,217,181,.92)");
  tracked(config.edition || "CARD #0001", 512, 300, "20px 'Segoe UI', Arial", 2.4, "rgba(222,201,160,.86)");
  ctx.strokeStyle = "rgba(222,201,160,.35)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(432, 336); ctx.lineTo(592, 336); ctx.stroke();

  // 年龄: 极淡大号数字(专属水印; 无年龄则不出现)
  const age = String(config.age || "").trim();
  if (age) {
    ctx.fillStyle = "rgba(222,201,160,.085)";
    ctx.font = "420px Palatino Linotype, Georgia, serif";
    ctx.textAlign = "center";
    ctx.fillText(age, 512, 800);
    ctx.textAlign = "left";
  }

  // 主标题区
  tracked(config.title || "YOUR DAY", 512, 906, "92px Palatino Linotype, Georgia, serif", 2, "rgba(244,236,218,1)");
  star(512, 946, 5, 0.8, 0.28);
  ctx.strokeStyle = "rgba(222,201,160,.40)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(392, 946); ctx.lineTo(486, 946); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(538, 946); ctx.lineTo(632, 946); ctx.stroke();
  tracked("A DAY WORTH KEEPING", 512, 990, "17px 'Segoe UI', Arial", 6, "rgba(222,201,160,.60)");

  // 收藏凭证区: 卡名 / 日期 / 祝福 / 归属(大量留白)
  ctx.strokeStyle = "rgba(222,201,160,.28)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(372, 1128); ctx.lineTo(652, 1128); ctx.stroke();
  tracked(config.title || "YOUR DAY", 512, 1180, "34px Palatino Linotype, Georgia, serif", 1.4, "rgba(240,232,214,.95)");
  tracked(config.technique || "", 512, 1222, "22px 'Segoe UI', Arial", 2, "rgba(222,201,160,.86)");
  if (config.wish) tracked(config.wish, 512, 1272, "italic 21px Palatino Linotype, Georgia, serif", 0.6, "rgba(214,200,168,.78)");
  field("CREATED BY", 1348, config.createdBy || "");
  field("OWNED BY", 1424, config.ownedBy || "");
  return canvasTexture(c);
}
'''

POSE_JS = r'''// 生日收藏卡 · 四态展示支持
// ?pose=front|tilt|holo|back   &embed=1 只显示卡片本体
const qs = new URLSearchParams(location.search);
const poseName = qs.get("pose");
const embed = qs.get("embed") === "1";
const POSES = {
  front: { x: -0.035, y: -0.15, foil: 0.45, finish: 0 },
  tilt:  { x: -0.105, y: -0.52, foil: 0.58, finish: 0 },
  holo:  { x: -0.42,  y: -1.02, foil: 0.80, finish: 0 },
  back:  { x: -0.02,  y: Math.PI, foil: 0.35, finish: 0 },
};
if (embed) {
  const s = document.createElement("style");
  s.textContent = `
    html,body{background:#080c16 !important;}
    .masthead,.artwork-bar,.footer,.stage-note,#about,#notice{display:none !important;}
    main{padding:0 !important;}
    .gallery{height:100svh !important;min-height:0 !important;max-height:none !important;}
    .stage{bottom:0 !important;}
    .tools,.parameter-panel{display:none !important;}
  `;
  document.head.appendChild(s);
}
(async () => {
  const t0 = Date.now();
  while (!(window.__holo && window.__holo.ready) && Date.now() - t0 < 20000) {
    await new Promise((r) => setTimeout(r, 90));
  }
  const holo = window.__holo;
  if (!holo || !holo.ready || !poseName) return;
  const p = POSES[poseName] || POSES.front;
  try {
    if (holo.uniforms) {
      if (holo.uniforms.uFoil) holo.uniforms.uFoil.value = p.foil;
      if (holo.uniforms.uFinish) holo.uniforms.uFinish.value = p.finish;
    }
  } catch (e) { /* 忽略 */ }
  const tick = () => {
    if (holo.root) { holo.root.rotation.x = p.x; holo.root.rotation.y = p.y; }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})();
'''

DARK_CSS = """
/* ================= 生日收藏卡 · 深色高级主题(项目专用) ================= */
:root{--ink:#f0e8d6;--paper:#080c16;--line:#222b3f;--muted:#8b8474;}
html,body{background:#080c16;color:#f0e8d6;}
.masthead{border-color:#1c2436;background:#080c16;}
.wordmark-cn,.wordmark-en{color:#e9dcbe;}
.collection-label{color:#8b8474;}
.icon-button{color:#cbb98f;border-color:#2a3448;background:transparent;}
.icon-button:hover{background:#141c2b;}
.artwork-bar{border-color:#1c2436;}
.artwork-title h1,.title-line h1{color:#f4ecda;font-family:Georgia,"Palatino Linotype",serif;}
.title-line>span,#subtitle{color:#cbb98f;}
.artwork-title p,#description{color:#9c947f;}
.face-picker button{border-color:#2a3448;color:#cdbf9f;background:transparent;}
.face-picker button[aria-pressed="true"]{background:#1a2436;color:#f0e8d6;}
.finish-heading,.foil-row{color:#9c947f;}
.swatch{box-shadow:inset 0 0 0 1px #ffffff22;}
.swatch-name{color:#9c947f;}
.footer{border-color:#1c2436;color:#7e7867;}
.tools{background:#0f1728;border-color:#2a3448;box-shadow:0 10px 26px rgba(0,0,0,.5);}
.tools .icon-button .btn-label{color:#cbb98f;}
.tools .icon-button:hover{background:#1a2436;}
.parameter-panel{background:#0f1728;border:1px solid #2a3448;color:#e8dcc0;}
.parameter-panel .range-row,.panel-heading{color:#e8dcc0;}
input[type="range"]{background:#2a3448;}
dialog{background:#0f1728;color:#f0e8d6;}
dialog dt{color:#8b8474;}
"""

SHOWCASE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>YOUR DAY · 生日收藏卡 · 四态设计</title>
<style>
  :root { --gold:#dec9a0; --gold-dim:#a8874f; --bg:#070a12; }
  * { box-sizing:border-box; }
  body { margin:0; background:radial-gradient(120% 80% at 50% 0%,#101a2c 0%,#070a12 60%); color:#f0e8d6;
         font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif; }
  header { padding:34px 6vw 10px; }
  h1 { font-family:Georgia,"Palatino Linotype",serif; font-weight:400; letter-spacing:2px; margin:0 0 6px; font-size:30px; }
  h1 span { color:var(--gold); }
  .sub { color:#8b8474; font-size:13px; letter-spacing:3px; text-transform:uppercase; }
  .rule { height:1px; background:linear-gradient(90deg,transparent,var(--gold-dim),transparent); margin:22px 6vw 0; opacity:.6; }
  main { display:grid; grid-template-columns:repeat(2,1fr); gap:26px; padding:26px 6vw 60px; }
  .tile { background:linear-gradient(180deg,#0d1424,#080c16); border:1px solid #1c2436; border-radius:10px; padding:14px; }
  .tile .cap { display:flex; align-items:baseline; gap:10px; margin-bottom:10px; }
  .tile .idx { font-family:Georgia,serif; color:var(--gold); font-size:13px; letter-spacing:2px; }
  .tile .name { font-size:14px; color:#e8dcc0; letter-spacing:1px; }
  .tile .desc { margin-left:auto; font-size:11px; color:#8b8474; }
  iframe { width:100%; aspect-ratio:2/3; border:0; border-radius:6px; background:#080c16; display:block; }
  footer { padding:0 6vw 50px; color:#7e7867; font-size:12px; line-height:1.9; }
  footer b { color:#cbb98f; font-weight:400; }
  @media (max-width:760px){ main{grid-template-columns:1fr;} }
</style>
</head>
<body>
<header>
  <h1>YOUR <span>DAY</span></h1>
  <div class="sub">Birthday · Digital Collectible · Card #0001</div>
</header>
<div class="rule"></div>
<main>
  <div class="tile">
    <div class="cap"><span class="idx">01</span><span class="name">正面静止</span><span class="desc">Holo ≈ 0, 先是一张漂亮的收藏卡</span></div>
    <iframe src="./?pose=front&embed=1" title="正面静止"></iframe>
  </div>
  <div class="tile">
    <div class="cap"><span class="idx">02</span><span class="name">轻微倾斜</span><span class="desc">仅边缘出现金属光泽</span></div>
    <iframe src="./?pose=tilt&embed=1" title="轻微倾斜"></iframe>
  </div>
  <div class="tile">
    <div class="cap"><span class="idx">03</span><span class="name">大角度 Holo</span><span class="desc">虹彩反射 + 边缘高光 + 少量 sparkle</span></div>
    <iframe src="./?pose=holo&embed=1" title="大角度 Holo"></iframe>
  </div>
  <div class="tile">
    <div class="cap"><span class="idx">04</span><span class="name">背面设计</span><span class="desc">同一套金线语言 · 预留身份字段</span></div>
    <iframe src="./?pose=back&embed=1" title="背面设计"></iframe>
  </div>
</main>
<footer>
  <b>照片:</b>羽化融入卡面, 仅裁切/调色/暗部压制/局部景深, 未抠图未重绘 &nbsp;|&nbsp;
  <b>年龄:</b>配置提供时作为核心视觉, 未提供则不出现 &nbsp;|&nbsp;
  <b>层次:</b>背景 → 照片 → 前景星尘 → 卡框/文字 &nbsp;|&nbsp;
  <b>Holo:</b>is a material, not the artwork
</footer>
</body>
</html>
"""


def patch_back_and_spectrum():
    for name in ("app.bundle.js", "app.js"):
        p = WEB / name
        if not p.exists():
            continue
        s = p.read_text(encoding="utf8")
        i = s.find("function backTexture() {")
        j = s.find("function addShadow() {")
        if i >= 0 and j > i:
            s = s[:i] + BACK_NEW + s[j:]
            print("  背板已重画:", name)
        old_spec = ".66 + .25 * cos(6.28318 * (phase + vec3(0., .33, .67)))"
        new_spec = ".74 + .17 * cos(6.28318 * (phase + vec3(0., .33, .67)))"
        if old_spec in s:
            s = s.replace(old_spec, new_spec)
            print("  虹彩降饱和:", name)
        p.write_text(s, encoding="utf8")


def patch_index():
    p = WEB / "index.html"
    s = p.read_text(encoding="utf8")
    for a, b in [
        ("白相 · White Atelier", "YOUR DAY · 生日收藏卡"),
        ('<span class="wordmark-cn">白相', '<span class="wordmark-cn">YOUR DAY'),
        ("WHITE ATELIER", "DIGITAL COLLECTIBLE"),
        ("PERSONAL ART COLLECTION", "BIRTHDAY COLLECTIBLE"),
        ('<p class="dialog-mark">白相</p>', '<p class="dialog-mark">YOUR DAY</p>'),
        ('<h2 id="about-title">共生 / BOND</h2>', '<h2 id="about-title">YOUR DAY · 生日收藏卡</h2>'),
        ("<dd>用户提供的参考作品</dd>", "<dd>原始照片(仅裁切调色, 未抠图)</dd>"),
        ("<dd>个人艺术卡片习作</dd>", "<dd>生日专属数字收藏卡</dd>"),
        ("光影之间，自有回响。", "A DAY WORTH KEEPING."),
    ]:
        s = s.replace(a, b)
    if "pose.js" not in s:
        s = s.replace("</body>", '  <script type="module" src="./pose.js"></script>\n</body>')
    p.write_text(s, encoding="utf8")
    print("  index.html 已定制")


def main():
    (WEB / "pose.js").write_text(POSE_JS, encoding="utf8")
    (WEB / "showcase.html").write_text(SHOWCASE, encoding="utf8")
    patch_back_and_spectrum()
    patch_index()
    css = WEB / "style.css"
    s = css.read_text(encoding="utf8")
    if "深色高级主题" not in s:
        css.write_text(s + DARK_CSS, encoding="utf8")
        print("  style.css 深色主题已追加")
    print("查看器定制完成")


if __name__ == "__main__":
    main()
