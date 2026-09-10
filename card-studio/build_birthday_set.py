# -*- coding: utf-8 -*-
"""
Birthday 系列 · 四套模板批量构建
=================================
同一张照片 × 四套模板 → 四张数字收藏卡(共用 3D / Parallax / Holo 技术)

每套做:
  1. 写 card-config.json(文案 + 主题色 + 层深参数 + backStyle)
  2. birthday_system.py 生成五层素材
  3. run_pipeline.py 建 Blender 工程 + 导出 GLB + 组装网页
  4. 注入: 四态 pose.js / 深色或浅色页面主题 / 支持四种风格的背板
  5. 复制到 birthday-set/<模板>/, 并生成总览页 + 本地服务(4185)

用法: python card-studio/build_birthday_set.py [照片路径]
"""
import json, shutil, subprocess, sys
from pathlib import Path

STUDIO = Path(__file__).resolve().parent
ROOT = STUDIO.parent
SET = ROOT / "birthday-set"
BLENDER = ROOT / "demo-koi" / "tools" / "blender-4.5.13-windows-x64" / "blender.exe"
PHOTO_DEFAULT = ROOT / "demo-birthday" / "assets" / "source.png"


def log(m):
    print("[构建] " + m, flush=True)

TEMPLATES = {
    "celebration": dict(
        theme="light", page_bg="#fbf6ec", ink="#3a342c", accent="#e8796a",
        params=dict(subjectScale=1.0, subjectDepth=0.32, backgroundDepth=-0.26,
                    effectsDepth=0.58, effectsScale=1.04, foil=0.50)),
    "soft": dict(
        theme="light", page_bg="#f7f2ea", ink="#5b5248", accent="#c8a97e",
        params=dict(subjectScale=1.0, subjectDepth=0.30, backgroundDepth=-0.24,
                    effectsDepth=0.55, effectsScale=1.03, foil=0.38)),
    "pop": dict(
        theme="light", page_bg="#fffdf6", ink="#141414", accent="#2b4cff",
        params=dict(subjectScale=1.0, subjectDepth=0.36, backgroundDepth=-0.30,
                    effectsDepth=0.66, effectsScale=1.06, foil=0.60)),
    "night": dict(
        theme="dark", page_bg="#080c16", ink="#f0e8d6", accent="#dec9a0",
        params=dict(subjectScale=1.0, subjectDepth=0.34, backgroundDepth=-0.30,
                    effectsDepth=0.62, effectsScale=1.05, foil=0.52)),
    # 立体画框: 大层距 + 暖金箔光扫 + 浮雕投影
    "diorama": dict(
        theme="dark", page_bg="#06090f", ink="#f2e8d5", accent="#e8c98a", finish="gold",
        params=dict(subjectScale=1.0, subjectDepth=0.55, backgroundDepth=-0.34,
                    effectsDepth=0.88, effectsScale=1.06, foil=0.88)),
}

BASE_CFG = {
    "title": "YOUR DAY",
    "subtitle": "HAPPY BIRTHDAY",
    "tagline": "A DAY WORTH KEEPING",
    "technique": "2026.09.09",
    "edition": "CARD #0001",
    "collection": "BIRTHDAY COLLECTIBLE",
    "description": "生日专属数字收藏卡",
    "age": "20",
    "name": "",
    "createdBy": "",
    "ownedBy": "",
    "wish": "MAY EVERY YEAR BE KIND TO YOU",
}

POSE_JS = r'''// Birthday 系列 · 四态展示 + 纯净视图
// ?pose=front|tilt|holo|back   &embed=1 只显示卡片本体
const qs = new URLSearchParams(location.search);
const poseName = qs.get("pose");
const embed = qs.get("embed") === "1";
const POSES = {
  front: { x: -0.035, y: -0.15, foil: null, finish: 0 },
  tilt:  { x: -0.105, y: -0.52, foil: null, finish: 0 },
  holo:  { x: -0.42,  y: -1.02, foil: 0.82, finish: 0 },
  back:  { x: -0.02,  y: Math.PI, foil: 0.38, finish: 0 },
};
if (embed) {
  const s = document.createElement("style");
  s.textContent = `
    html,body{background:var(--page-bg,#080c16) !important;}
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
      if (p.foil != null && holo.uniforms.uFoil) holo.uniforms.uFoil.value = p.foil;
      if (holo.uniforms.uFinish) holo.uniforms.uFinish.value = p.finish;
    }
  } catch (e) { /* ignore */ }
  const tick = () => {
    if (holo.root) { holo.root.rotation.x = p.x; holo.root.rotation.y = p.y; }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})();
'''

# 统一结构 + 四种风格的背板
BACK_JS = r'''function backTexture() {
  const c = document.createElement("canvas");
  c.width = 1024;
  c.height = 1536;
  const ctx = c.getContext("2d");
  const S = {
    celebration: { bg1:"#fbf6ec", bg2:"#f6ecda", ink:"#3a342c", gold:"#c4964a", a1:"#e8796a", a2:"#f6d27a", frame:"thin" },
    soft:        { bg1:"#f7f2ea", bg2:"#efe7da", ink:"#5b5248", gold:"#d8c3a0", a1:"#e8d2ce", a2:"#d8c3a0", frame:"double" },
    pop:         { bg1:"#fffdf6", bg2:"#fff8e6", ink:"#141414", gold:"#ffd400", a1:"#2b4cff", a2:"#ff4b3e", frame:"bold" },
    night:       { bg1:"#0e1526", bg2:"#070a12", ink:"#f0e8d6", gold:"#dec9a0", a1:"#a8874f", a2:"#d9a6a0", frame:"double" },
    diorama:     { bg1:"#0c1424", bg2:"#05070d", ink:"#f2e8d5", gold:"#e8c98a", a1:"#a8763a", a2:"#c4523f", frame:"double" },
  }[config.backStyle || "night"];
  const dark = ["night", "diorama"].includes(config.backStyle || "night");
  const star = (x, y, r, alpha) => {
    const k = 0.22;
    ctx.beginPath();
    ctx.moveTo(x, y - r); ctx.lineTo(x + r * k, y - r * k); ctx.lineTo(x + r, y);
    ctx.lineTo(x + r * k, y + r * k); ctx.lineTo(x, y + r); ctx.lineTo(x - r * k, y + r * k);
    ctx.lineTo(x - r, y); ctx.lineTo(x - r * k, y - r * k); ctx.closePath();
    ctx.fillStyle = "rgba(" + alpha + ")"; ctx.fill();
  };
  const tracked = (text, cx, y, fnt, tracking, color) => {
    ctx.font = fnt; ctx.fillStyle = color;
    const chars = [...String(text)];
    const w = chars.reduce((s, ch) => s + ctx.measureText(ch).width, 0) + tracking * (chars.length - 1);
    let x = cx - w / 2;
    for (const ch of chars) { ctx.fillText(ch, x, y); x += ctx.measureText(ch).width + tracking; }
  };
  const field = (label, y, value) => {
    tracked(label, 512, y, "12px 'Segoe UI', Arial", 3.2, "rgba(" + (S.frame === "bold" ? "20,20,20,.62" : "139,132,116,.92") + ")");
    if (value) tracked(value, 512, y + 30, "17px 'Segoe UI', Arial", 1, "rgba(" + (dark ? "232,217,181,.94" : "58,52,44,.9") + ")");
    else {
      ctx.strokeStyle = "rgba(" + (dark ? "222,201,160,.22" : "58,52,44,.25") + ")";
      ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(412, y + 26); ctx.lineTo(612, y + 26); ctx.stroke();
    }
  };
  const g = ctx.createLinearGradient(0, 0, 0, 1536);
  g.addColorStop(0, S.bg1); g.addColorStop(1, S.bg2);
  ctx.fillStyle = g; ctx.fillRect(0, 0, 1024, 1536);
  // 风格化底纹
  if (config.backStyle === "pop") {
    ctx.fillStyle = S.a1; ctx.fillRect(0, 1330, 1024, 206);
    ctx.fillStyle = S.gold; ctx.fillRect(0, 0, 1024, 46);
    ctx.fillStyle = S.a2; ctx.fillRect(740, 46, 284, 18);
  } else if (config.backStyle === "celebration") {
    const rg = ctx.createRadialGradient(190, 220, 20, 190, 220, 430);
    rg.addColorStop(0, "rgba(246,210,122,.55)"); rg.addColorStop(1, "rgba(246,210,122,0)");
    ctx.fillStyle = rg; ctx.fillRect(0, 0, 1024, 900);
    const rg2 = ctx.createRadialGradient(870, 1240, 20, 870, 1240, 420);
    rg2.addColorStop(0, "rgba(232,121,106,.38)"); rg2.addColorStop(1, "rgba(232,121,106,0)");
    ctx.fillStyle = rg2; ctx.fillRect(400, 800, 624, 736);
  } else if (dark) {
    ctx.globalAlpha = 0.055;
    for (let i = 0; i < 150; i++) {
      const y = Math.random() * 1536;
      ctx.strokeStyle = i % 2 ? "#8fa2c4" : "#c9b184"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(Math.random() * 600, y); ctx.lineTo(Math.random() * 400 + 300, y); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.beginPath(); ctx.arc(512, 760, 300, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(222,201,160,.07)"; ctx.lineWidth = 1; ctx.stroke();
  }
  // 边框
  if (S.frame === "bold") {
    ctx.strokeStyle = S.ink; ctx.lineWidth = 4; ctx.strokeRect(26, 26, 972, 1484);
  } else if (S.frame === "thin") {
    ctx.strokeStyle = "rgba(58,52,44,.85)"; ctx.lineWidth = 2; ctx.strokeRect(30, 30, 964, 1476);
    star(62, 62, 8, "232,121,106,.9"); star(962, 1474, 8, "246,210,122,.95");
  } else {
    ctx.strokeStyle = "rgba(" + (dark ? "222,201,160,.80" : "216,195,160,.95") + ")";
    ctx.lineWidth = 2; ctx.strokeRect(38, 38, 948, 1460);
    ctx.strokeStyle = "rgba(" + (dark ? "168,135,79,.50" : "216,195,160,.7") + ")";
    ctx.lineWidth = 1; ctx.strokeRect(56, 56, 912, 1424);
    [[86, 86], [938, 86], [86, 1450], [938, 1450]].forEach(([x, y]) => star(x, y, 7, "222,201,160,.78"));
  }
  const inkC = S.ink, goldC = S.gold;
  // 顶部: 主题 + 固定身份
  tracked(config.subtitle || "HAPPY BIRTHDAY", 512, 250,
          (config.backStyle === "pop" ? "800 26px Bahnschrift, Arial Black" : "600 24px 'Segoe UI', Arial"),
          10, inkC);
  tracked(config.edition || "CARD #0001", 512, 312, "20px 'Segoe UI', Arial", 2.4, goldC);
  ctx.strokeStyle = "rgba(" + (dark ? "222,201,160,.35" : "58,52,44,.28") + ")";
  ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(432, 348); ctx.lineTo(592, 348); ctx.stroke();
  // 年龄水印
  const age = String(config.age || "").trim();
  if (age) {
    ctx.fillStyle = (dark ? "rgba(222,201,160,.085)"
      : config.backStyle === "pop" ? "rgba(20,20,20,.07)"
      : config.backStyle === "celebration" ? "rgba(232,121,106,.12)" : "rgba(216,195,160,.22)");
    ctx.font = (config.backStyle === "pop" ? "300px Bahnschrift, Arial Black" : "320px Palatino Linotype, Georgia, serif");
    ctx.textAlign = "center"; ctx.fillText(age, 512, 880); ctx.textAlign = "left";
  }
  tracked(config.title || "YOUR DAY", 512, 900,
          (config.backStyle === "pop" ? "800 86px Bahnschrift, Arial Black"
            : config.backStyle === "celebration" ? "84px Palatino Linotype, Georgia, serif"
            : "92px Palatino Linotype, Georgia, serif"), 2, inkC);
  star(512, 940, 5, (dark ? "222,201,160,.8" : "58,52,44,.5"));
  ctx.strokeStyle = "rgba(" + (dark ? "222,201,160,.40" : "58,52,44,.30") + ")";
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(392, 940); ctx.lineTo(486, 940); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(538, 940); ctx.lineTo(632, 940); ctx.stroke();
  if (config.tagline) tracked(config.tagline, 512, 982, "16px 'Segoe UI', Arial", 5.5, "rgba(" + (dark ? "222,201,160,.6" : "58,52,44,.62") + ")");
  // 收藏凭证区
  ctx.strokeStyle = "rgba(" + (dark ? "222,201,160,.28" : "58,52,44,.22") + ")";
  ctx.beginPath(); ctx.moveTo(372, 1132); ctx.lineTo(652, 1132); ctx.stroke();
  field("CARD NAME", 1150, config.name || "");
  if (config.technique) tracked(config.technique, 512, 1236, "22px 'Segoe UI', Arial", 2, goldC);
  if (config.wish) tracked(config.wish, 512, 1278, "italic 21px Palatino Linotype, Georgia, serif", 0.6,
                           "rgba(" + (dark ? "214,200,168,.78" : "58,52,44,.70") + ")");
  if (config.name) tracked("FOR " + String(config.name).toUpperCase(), 512, 1316, "16px 'Segoe UI', Arial", 4, inkC);
  field("CREATED BY", 1356, config.createdBy || "");
  field("OWNED BY", 1432, config.ownedBy || "");
  return canvasTexture(c);
}
'''

SERVER_JS = r'''import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 4185);
const types = { ".html":"text/html; charset=utf-8", ".js":"text/javascript; charset=utf-8",
  ".mjs":"text/javascript; charset=utf-8", ".css":"text/css; charset=utf-8",
  ".json":"application/json; charset=utf-8", ".png":"image/png", ".jpg":"image/jpeg",
  ".glb":"model/gltf-binary", ".svg":"image/svg+xml" };
http.createServer(async (req, res) => {
  try {
    let url = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
    let file = path.resolve(root, "." + url);
    if (file !== root && !file.startsWith(root + path.sep)) { res.writeHead(403); return res.end("Forbidden"); }
    if ((await stat(file)).isDirectory()) file = path.join(file, "index.html");
    const data = await readFile(file);
    res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream", "Cache-Control": "no-cache" });
    res.end(data);
  } catch { res.writeHead(404); res.end("Not found"); }
}).listen(port, "127.0.0.1", () => console.log("Birthday 系列: http://127.0.0.1:" + port));
'''


def page_theme(tpl, t):
    if t["theme"] == "dark":
        return f"""
/* {tpl} · 深色页面主题 */
:root{{--ink:#f0e8d6;--paper:{t['page_bg']};--line:#222b3f;--muted:#8b8474;}}
html,body{{background:{t['page_bg']};color:#f0e8d6;}}
.masthead{{border-color:#1c2436;background:{t['page_bg']};}}
.wordmark-cn,.wordmark-en{{color:#e9dcbe;}}
.artwork-title h1,.title-line h1{{color:#f4ecda;font-family:Georgia,"Palatino Linotype",serif;}}
.title-line>span,#subtitle{{color:{t['accent']};}}
.artwork-title p,#description{{color:#9c947f;}}
.icon-button{{color:#cbb98f;border-color:#2a3448;background:transparent;}}
.artwork-bar,.footer{{border-color:#1c2436;color:#7e7867;}}
.tools{{background:#0f1728;border-color:#2a3448;}}
.tools .icon-button .btn-label{{color:#cbb98f;}}
.parameter-panel{{background:#0f1728;border:1px solid #2a3448;color:#e8dcc0;}}
.face-picker button{{border-color:#2a3448;color:#cdbf9f;background:transparent;}}
.face-picker button[aria-pressed="true"]{{background:#1a2436;color:#f0e8d6;}}
"""
    return f"""
/* {tpl} · 浅色页面主题 */
:root{{--ink:{t['ink']};--paper:{t['page_bg']};--line:#e2dccf;--muted:#8d857a;}}
html,body{{background:{t['page_bg']};color:{t['ink']};}}
.masthead{{border-color:#e6e0d3;background:{t['page_bg']};}}
.wordmark-cn,.wordmark-en{{color:{t['ink']};}}
.collection-label{{color:{t['accent']};}}
.artwork-title h1,.title-line h1{{color:{t['ink']};}}
.title-line>span,#subtitle{{color:{t['accent']};}}
.tools{{background:#ffffff;border-color:#e6e0d3;}}
.tools .icon-button .btn-label{{color:{t['ink']};}}
.parameter-panel{{background:#ffffff;border:1px solid #eee8dc;}}
.face-picker button[aria-pressed="true"]{{background:{t['ink']};color:#fff;}}
"""


def card_page(base, tpl, t):
    """每张卡自带的四态展示页"""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Birthday / {tpl.title()} · 四态</title>
<style>
 body{{margin:0;background:{t['page_bg']};color:{t['ink']};
      font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;}}
 header{{padding:30px 5vw 8px;}}
 h1{{margin:0;font-family:Georgia,"Palatino Linotype",serif;font-weight:400;letter-spacing:2px;font-size:26px;}}
 .sub{{font-size:12px;letter-spacing:3px;color:{t['accent']};text-transform:uppercase;margin-top:6px;}}
 main{{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;padding:22px 5vw 50px;}}
 .tile{{border:1px solid rgba(128,128,128,.25);border-radius:10px;padding:10px;}}
 .cap{{font-size:12px;margin-bottom:8px;display:flex;gap:8px;align-items:baseline;}}
 .cap b{{color:{t['accent']};font-weight:500;letter-spacing:1px;}}
 iframe{{width:100%;aspect-ratio:2/3;border:0;border-radius:6px;background:{t['page_bg']};display:block;}}
 footer{{padding:0 5vw 44px;font-size:12px;color:{t['accent']};opacity:.85;}}
 @media (max-width:900px){{main{{grid-template-columns:repeat(2,1fr);}}}}
</style></head>
<body>
<header><h1>Birthday / {tpl.title()}</h1>
<div class="sub">Digital Collectible · Card #0001</div></header>
<main>
 <div class="tile"><div class="cap"><b>01</b>正面静止</div><iframe src="./?pose=front&embed=1"></iframe></div>
 <div class="tile"><div class="cap"><b>02</b>轻微倾斜</div><iframe src="./?pose=tilt&embed=1"></iframe></div>
 <div class="tile"><div class="cap"><b>03</b>大角度 Holo</div><iframe src="./?pose=holo&embed=1"></iframe></div>
 <div class="tile"><div class="cap"><b>04</b>背面设计</div><iframe src="./?pose=back&embed=1"></iframe></div>
</main>
<footer>照片为原始照片(仅裁切/调色/暗部/渐变融入, 未抠图未重绘) · Holo is a material, not the artwork</footer>
</body></html>
"""


def gallery():
    tiles = []
    for tpl, t in TEMPLATES.items():
        tiles.append(f"""
  <div class="tile">
    <div class="cap"><b>Birthday / {tpl.title()}</b><span>{'明亮开心' if tpl=='celebration' else '温柔浪漫' if tpl=='soft' else '年轻大胆' if tpl=='pop' else '高级安静'}</span></div>
    <iframe src="./{tpl}/?pose=front&embed=1" title="{tpl}"></iframe>
    <div class="links"><a href="./{tpl}/">打开卡片</a><a href="./{tpl}/showcase.html">四态展示</a></div>
  </div>""")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Birthday 系列 · 四套模板</title>
<style>
 body{{margin:0;background:radial-gradient(120% 80% at 50% 0%,#101a2c 0%,#070a12 60%);color:#f0e8d6;
      font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;}}
 header{{padding:36px 5vw 6px;}}
 h1{{margin:0;font-family:Georgia,"Palatino Linotype",serif;font-weight:400;letter-spacing:2px;font-size:30px;}}
 h1 span{{color:#dec9a0;}}
 .sub{{color:#8b8474;font-size:13px;letter-spacing:3px;text-transform:uppercase;margin-top:8px;}}
 .rule{{height:1px;background:linear-gradient(90deg,transparent,#a8874f,transparent);margin:20px 5vw 0;opacity:.6;}}
 main{{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;padding:24px 5vw 40px;}}
 .tile{{background:linear-gradient(180deg,#0d1424,#080c16);border:1px solid #1c2436;border-radius:12px;padding:12px;}}
 .cap{{display:flex;justify-content:space-between;align-items:baseline;font-size:13px;margin-bottom:10px;}}
 .cap b{{color:#dec9a0;font-weight:500;letter-spacing:1px;}}
 .cap span{{color:#8b8474;font-size:11px;}}
 iframe{{width:100%;aspect-ratio:2/3;border:0;border-radius:6px;background:#080c16;display:block;}}
 .links{{display:flex;gap:14px;margin-top:10px;font-size:12px;}}
 .links a{{color:#cbb98f;text-decoration:none;border-bottom:1px solid #a8874f55;}}
 .links a:hover{{color:#f0e8d6;}}
 footer{{padding:0 5vw 56px;color:#7e7867;font-size:12px;line-height:2;}}
 footer b{{color:#cbb98f;font-weight:400;}}
 @media (max-width:1100px){{main{{grid-template-columns:repeat(2,1fr);}}}}
 @media (max-width:640px){{main{{grid-template-columns:1fr;}}}}
</style></head>
<body>
<header>
  <h1>Birthday <span>Collection</span></h1>
  <div class="sub">One photo · Four designs · One brand system</div>
</header>
<div class="rule"></div>
<main>{''.join(tiles)}
</main>
<footer>
  <b>统一:</b>卡牌比例 · Card ID 逻辑 · 背板信息体系 · 字体体系 · 边框逻辑 · Holo 交互 &nbsp;|&nbsp;
  <b>不同:</b>构图 · 字体比例 · 照片处理 · 排版位置 · 装饰方式 · 背景 · 年龄数字用法 · 光影语言<br />
  <b>照片:</b>四套均使用同一张原始照片, 未抠图 / 未重绘 / 未虚构人物
</footer>
</body></html>
"""


def build_one(tpl, t, photo):
    proj = ROOT / "birthday-build" / tpl
    (proj / "assets").mkdir(parents=True, exist_ok=True)
    cfg = dict(BASE_CFG)
    cfg.update({
        "appearance": {"finish": t.get("finish", "pearl"), "background": t["page_bg"]},
        "backStyle": tpl,
        "parameters": t["params"],
        "safeArea": {"scale": 1.0, "offset": [0.0, 0.0]},
    })
    (proj / "card-config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf8")

    subprocess.run([sys.executable, "-u", str(STUDIO / "birthday_system.py"), str(photo), str(proj), tpl], check=True)
    subprocess.run([sys.executable, "-u", str(ROOT / "RuiC-card-skill-main" / "scripts" / "run_pipeline.py"),
                    "--project", str(proj), "--blender", str(BLENDER),
                    "--skip-npm", "--skip-render"], check=True)

    web = proj / "web"
    # 网页定制
    (web / "pose.js").write_text(POSE_JS, encoding="utf8")
    (web / "showcase.html").write_text(card_page(web, tpl, t), encoding="utf8")
    css = (web / "style.css").read_text(encoding="utf8")
    if f"{tpl} · " not in css:
        (web / "style.css").write_text(css + page_theme(tpl, t), encoding="utf8")
    idx = (web / "index.html").read_text(encoding="utf8")
    for a, b in [("白相 · White Atelier", f"Birthday / {tpl.title()}"),
                 ('<span class="wordmark-cn">白相', '<span class="wordmark-cn">Birthday'),
                 ("WHITE ATELIER", "DIGITAL COLLECTIBLE"),
                 ("PERSONAL ART COLLECTION", "BIRTHDAY COLLECTIBLE"),
                 ('<p class="dialog-mark">白相</p>', '<p class="dialog-mark">Birthday</p>'),
                 ("<dd>用户提供的参考作品</dd>", "<dd>原始照片(仅裁切调色, 未抠图)</dd>")]:
        idx = idx.replace(a, b)
    if "pose.js" not in idx:
        idx = idx.replace("</body>", '  <script type="module" src="./pose.js"></script>\n</body>')
    (web / "index.html").write_text(idx, encoding="utf8")
    for name in ("app.bundle.js", "app.js"):
        p = web / name
        s = p.read_text(encoding="utf8")
        i, j = s.find("function backTexture() {"), s.find("function addShadow() {")
        if i >= 0 and j > i:
            s = s[:i] + BACK_JS + s[j:]
        old = ".66 + .25 * cos(6.28318 * (phase + vec3(0., .33, .67)))"
        if old in s:
            s = s.replace(old, ".74 + .17 * cos(6.28318 * (phase + vec3(0., .33, .67)))")
        p.write_text(s, encoding="utf8")

    dst = SET / tpl
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(web, dst)
    log(f"{tpl} 完成 → birthday-set/{tpl}")


def main():
    photo = Path(sys.argv[1]) if len(sys.argv) > 1 else PHOTO_DEFAULT
    only = [x.strip() for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else list(TEMPLATES)
    if not photo.exists():
        raise SystemExit(f"照片不存在: {photo}")
    if not BLENDER.exists():
        raise SystemExit(f"找不到 Blender: {BLENDER}")
    SET.mkdir(parents=True, exist_ok=True)
    for tpl, t in TEMPLATES.items():
        if tpl not in only:
            continue
        build_one(tpl, t, photo)
    (SET / "index.html").write_text(gallery(), encoding="utf8")
    (SET / "server.mjs").write_text(SERVER_JS, encoding="utf8")
    print("\n全部完成。启动: cd birthday-set && node server.mjs  →  http://127.0.0.1:4185")


if __name__ == "__main__":
    main()
