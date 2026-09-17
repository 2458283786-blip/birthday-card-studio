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
                    effectsDepth=0.58, effectsScale=1.04, foil=0.50),
        material=dict(regions=dict(frame="pearl", text="matte", subject="matte", background="pearl"),
                      amounts=dict(frame=0.45, subject=0.0, background=0.28))),
    "soft": dict(
        theme="light", page_bg="#f7f2ea", ink="#5b5248", accent="#c8a97e",
        params=dict(subjectScale=1.0, subjectDepth=0.30, backgroundDepth=-0.24,
                    effectsDepth=0.55, effectsScale=1.03, foil=0.38),
        material=dict(regions=dict(frame="pearl", text="matte", subject="matte", background="pearl"),
                      amounts=dict(frame=0.35, subject=0.0, background=0.22))),
    "pop": dict(
        theme="light", page_bg="#fffdf6", ink="#141414", accent="#2b4cff",
        params=dict(subjectScale=1.0, subjectDepth=0.36, backgroundDepth=-0.30,
                    effectsDepth=0.66, effectsScale=1.06, foil=0.60),
        material=dict(regions=dict(frame="gloss", text="gloss", subject="matte", background="matte"),
                      amounts=dict(frame=0.5, text=0.4, subject=0.0, background=0.0))),
    "night": dict(
        theme="dark", page_bg="#080c16", ink="#f0e8d6", accent="#dec9a0",
        params=dict(subjectScale=1.0, subjectDepth=0.34, backgroundDepth=-0.30,
                    effectsDepth=0.62, effectsScale=1.05, foil=0.52, textDepth=0.55),
        material=dict(regions=dict(frame="pearl", text="matte", subject="pearl", background="pearl"),
                      amounts=dict(frame=0.5, subject=0.35, background=0.35))),
    # 立体画框: 大层距 + 暖金箔光扫 + 浮雕投影
    "diorama": dict(
        theme="dark", page_bg="#06090f", ink="#f2e8d5", accent="#e8c98a", finish="gold",
        params=dict(subjectScale=1.0, subjectDepth=0.55, backgroundDepth=-0.34,
                    effectsDepth=0.88, effectsScale=1.06, foil=0.88),
        material=dict(regions=dict(frame="foil", text="foil", subject="matte", background="pearl"),
                      amounts=dict(frame=0.95, text=0.7, subject=0.0, background=0.4))),
}

BASE_CFG = {
    "title": "",
    "subtitle": "HAPPY BIRTHDAY",
    "tagline": "",
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
  c.width = 1024; c.height = 1536;
  const ctx = c.getContext("2d");
  const gold = "rgb(222,201,160)", cream = "rgb(240,236,228)", faint = "rgba(230,224,212,.72)";

  // —— 近黑底: 竖向渐变 + 径向暗角(与离线成图同一套观感) ——
  const g = ctx.createLinearGradient(0, 0, 0, 1536);
  g.addColorStop(0.00, "#0c0d11");
  g.addColorStop(0.45, "#111218");
  g.addColorStop(1.00, "#0a0b0f");
  ctx.fillStyle = g; ctx.fillRect(0, 0, 1024, 1536);
  const rg = ctx.createRadialGradient(512, 690, 140, 512, 690, 940);
  rg.addColorStop(0, "rgba(255,255,255,.045)");
  rg.addColorStop(1, "rgba(0,0,0,.55)");
  ctx.fillStyle = rg; ctx.fillRect(0, 0, 1024, 1536);

  // —— 极细内框 + 四角短线 ——
  ctx.strokeStyle = "rgba(222,201,160,.26)"; ctx.lineWidth = 1;
  ctx.strokeRect(34.5, 34.5, 1024 - 69, 1536 - 69);
  ctx.strokeStyle = "rgba(222,201,160,.40)";
  [[34.5, 34.5, 1, 1], [989.5, 34.5, -1, 1], [34.5, 1501.5, 1, -1], [989.5, 1501.5, -1, -1]]
    .forEach(function (p) {
      ctx.beginPath();
      ctx.moveTo(p[0], p[1]); ctx.lineTo(p[0] + p[2] * 34, p[1]);
      ctx.moveTo(p[0], p[1]); ctx.lineTo(p[0], p[1] + p[3] * 34);
      ctx.stroke();
    });

  // —— 助手: 字距排版 / 字号自适应 ——
  const tracked = (text, cx, y, fnt, tracking, color) => {
    ctx.font = fnt; ctx.fillStyle = color;
    const chars = [...String(text)];
    const w = chars.reduce((s, ch) => s + ctx.measureText(ch).width, 0) + tracking * (chars.length - 1);
    let x = cx - w / 2;
    for (const ch of chars) { ctx.fillText(ch, x, y); x += ctx.measureText(ch).width + tracking; }
  };
  const fitText = (text, weight, fam, size, maxW, tracking, minSize) => {
    let t = String(text == null ? "" : text), sz = size;
    const fontOf = (px) => (weight ? weight + " " : "") + px + "px " + fam;
    const wid = (str, px) => {
      ctx.font = fontOf(px);
      return ctx.measureText(str).width + tracking * Math.max(0, [...str].length - 1);
    };
    while (sz > (minSize || 12) && wid(t, sz) > maxW) sz -= 1;
    const full = t;
    while (t.length > 3 && wid(t + "\u2026", sz) > maxW) t = t.slice(0, -1);
    return { font: fontOf(sz), text: t === full ? t : t + "\u2026" };
  };

  const SERIF = "'Palatino Linotype', 'Microsoft YaHei', Georgia, serif";
  const SANS = "'Segoe UI', 'Microsoft YaHei', Arial, sans-serif";
  const SCRIPT = "'Segoe Script', Inkfree, 'Microsoft YaHei', cursive";

  // —— 上: CARD # → 细线 → 日期 ——
  let y = 268;
  if (config.edition) {
    const t = fitText(config.edition, "", SERIF, 38, 620, 3.4, 16);
    tracked(t.text, 512, y, t.font, 3.4, gold);
  }
  y += 46;
  ctx.strokeStyle = "rgba(222,201,160,.28)"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(512 - 92, y); ctx.lineTo(512 + 92, y); ctx.stroke();
  if (config.technique) {
    const t = fitText(config.technique, "", SANS, 21, 560, 2.6, 12);
    tracked(t.text, 512, y + 34, t.font, 2.6, "rgba(240,236,228,.78)");
  }

  // —— 中: 手写签名 ——
  let script = String(config.collection || "Digital Collectible Card").trim();
  if (script === script.toUpperCase()) {
    script = script.split(/\s+/).map(function (w) {
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    }).join(" ");
  }
  if (script) {
    let sz = script.length <= 24 ? 74 : 58;
    ctx.font = sz + "px " + SCRIPT;
    while (ctx.measureText(script).width > 660 && sz > 30) { sz -= 2; ctx.font = sz + "px " + SCRIPT; }
    ctx.fillStyle = "rgba(0,0,0,.5)"; ctx.textAlign = "center";
    ctx.fillText(script, 514, 768 + 2);
    ctx.fillStyle = "rgba(222,201,160,.88)";
    ctx.fillText(script, 512, 768);
    ctx.textAlign = "left";
  }

  // —— 细线 + 左右双栏归属 ——
  ctx.strokeStyle = "rgba(222,201,160,.20)";
  ctx.beginPath(); ctx.moveTo(512 - 150, 960); ctx.lineTo(512 + 150, 960); ctx.stroke();
  const created = String(config.createdBy || "").replace(/^@/, "");
  const owned = String(config.ownedBy || "").replace(/^@/, "");
  if (created) {
    const t = fitText("Created by @" + created, "", SANS, 16, 340, 2.2, 11);
    tracked(t.text, 512 * 0.56, 1020, t.font, 2.2, "rgba(240,236,228,.68)");
  }
  if (owned) {
    const t = fitText("Owned by @" + owned, "", SANS, 16, 340, 2.2, 11);
    tracked(t.text, 512 * 1.44, 1020, t.font, 2.2, "rgba(240,236,228,.68)");
  }

  // —— 底部: 居中二维码 ——
  const qr = config.qr || {};
  if (qr.enabled && Array.isArray(qr.matrix) && qr.matrix.length) {
    const m = qr.matrix, n = m.length, side = 164, pad = 12;
    const x0 = Math.round(512 - side / 2), y0 = Math.round(1536 * 0.735);
    ctx.fillStyle = "rgba(255,255,255,.94)";
    ctx.beginPath();
    const r = 10;
    ctx.moveTo(x0 - pad + r, y0 - pad);
    ctx.arcTo(x0 + side + pad, y0 - pad, x0 + side + pad, y0 + side + pad, r);
    ctx.arcTo(x0 + side + pad, y0 + side + pad, x0 - pad, y0 + side + pad, r);
    ctx.arcTo(x0 - pad, y0 + side + pad, x0 - pad, y0 - pad, r);
    ctx.arcTo(x0 - pad, y0 - pad, x0 + side + pad, y0 - pad, r);
    ctx.closePath(); ctx.fill();
    const cell = side / n;
    ctx.fillStyle = "rgb(12,12,14)";
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        if (m[i][j]) ctx.fillRect(x0 + j * cell, y0 + i * cell, Math.ceil(cell), Math.ceil(cell));
      }
    }
  }
  return canvasTexture(c);
}'''

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
    <div class="cap"><b>Birthday / {tpl.title()}</b><span>{'明亮开心 · 主力款' if tpl=='celebration' else '温柔浪漫' if tpl=='soft' else '年轻大胆' if tpl=='pop' else '高级安静 · 高级款' if tpl=='night' else '立体画框 · 备选款'}</span></div>
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
        "material": t.get("material", {}),
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

    # 用 esbuild 从 app.js 重建 app.bundle.js, 保证页面跑的就是我们改过的 shader
    try:
        import rebuild_bundles
        rebuild_bundles.build(web)
        log(f"{tpl} bundle 已重建")
    except Exception as e:
        log(f"{tpl} bundle 重建跳过({type(e).__name__})")

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
