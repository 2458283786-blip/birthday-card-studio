import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
// Icons are inline data trees (icons.data.js) — zero sub-imports at runtime,
// so no ad/privacy blocker can kill the page by blocking an icon module.
import { ICON_TREES } from "./icons.data.js";
const icons = ICON_TREES;
const $ = (id) => document.getElementById(id);
const stage = $("stage");
const media = matchMedia("(prefers-reduced-motion: reduce)");
const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-6, 6, 6, -6, 0.1, 100);
camera.position.set(0, 0, 20);
const inverse = new THREE.Matrix4();
const reliefLayers = { subject: [], effects: [], text: [] };
let renderer,
  root,
  uniforms,
  config,
  shadow,
  lastTime = 0,
  elapsed = 0;
let auto = false,
  flipped = false,
  dragging = false,
  finish = "pearl",
  zoom = 1;
let targetX = -0.035,
  targetY = -0.15,
  lastPointer = { x: 0, y: 0 },
  noticeTimer;
const settings = [
  ["foil", "uFoil"],
  ["scale", "uScale"],
  ["depth", "uDepth"],
  ["bg-depth", "uBgDepth"],
];
const vertex = `
varying vec2 vUv;
void main() {
  vUv = vec2(uv.x, 1.0 - uv.y);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;
const common = `
precision highp float;
varying vec2 vUv;
uniform float uTime, uFoil, uScale, uDepth, uBgDepth, uFinish, uHasLine, uRelief, uSafeScale, uFxDepth, uHasFx;
uniform vec2 uFit, uSafeOffset;
// 分区材质: 0 哑光 / 1 珠光 / 2 金属箔 / 3 亮面
uniform vec4 uMatType, uMatAmt;
uniform float uTextDepth;   // 文字层自己的景深(0=固定在最前)
uniform vec3 uView;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
float inside(vec2 p) { return step(0.,p.x)*step(0.,p.y)*step(p.x,1.)*step(p.y,1.); }
vec2 parallax(vec2 uv, float depth) {
  return uv + uView.xy / max(abs(uView.z), .4) * depth * .20;
}
vec3 spectrum(float phase) {
  return .66 + .25 * cos(6.28318 * (phase + vec3(0., .33, .67)));
}
// Only "original" (uFinish ~ 2) disables the foil; pearl/silver/gold all use it.
float strength() { return abs(uFinish - 2.0) < 0.05 ? 0. : uFoil; }
vec3 film(vec2 uv) {
  float phase = uv.x * .85 + uv.y * .55 + uView.x * 1.5 - uView.y * .9;
  if (uFinish > 2.5) {
    // 烫金 (gold foil): warm gold laminate that shifts with the viewing angle.
    float hi = 0.5 + 0.5 * sin(phase * 6.28318);
    float glint = 0.5 + 0.5 * cos((phase + 0.25) * 6.28318);
    vec3 deep = vec3(.72, .50, .20);
    vec3 bright = vec3(1.00, .90, .60);
    return mix(deep, bright, hi * .7 + glint * .3);
  }
  vec3 color = spectrum(phase);
  return mix(color, vec3(dot(color,vec3(.2126,.7152,.0722))), step(.5,uFinish));
}
float sweep(vec2 uv) {
  return pow(.5+.5*sin((uv.x*.72+uv.y*.45+uView.x*1.2+uView.y*.6)*6.283),10.);
}
vec3 pearlFilm(vec2 uv) {
  float phase = uv.x*.85 + uv.y*.55 + uView.x*1.5 - uView.y*.9;
  return .74 + .17*cos(6.28318*(phase + vec3(0.,.33,.67)));
}
vec3 foilFilm(vec2 uv) {
  float phase = uv.x*.62 + uv.y*.38 + uView.x*2.2 - uView.y*1.3;
  float hi = .5+.5*sin(phase*6.28318*1.6);
  return mix(vec3(.62,.46,.22), vec3(1.,.94,.72), hi);
}
vec3 glossFilm(vec2 uv) {
  float phase = uv.x*.35 + uv.y*1.15 + uView.y*1.4;
  float s = pow(.5+.5*sin(phase*6.28318), 1.6);
  return mix(vec3(.84,.87,.90), vec3(1.), s);
}
vec3 styleFilm(vec2 uv, float type) {
  if (type > 2.5) return glossFilm(uv);
  if (type > 1.5) return foilFilm(uv);
  return pearlFilm(uv);
}
// 单个区域施加材质(amount=0 即哑光, 原样返回)
vec3 applyMat(vec3 col, vec2 uv, float type, float amount, float band, float boost) {
  if (amount <= 0.001) return col;
  vec3 f = styleFilm(uv, type);
  float lum = dot(col, vec3(.2126,.7152,.0722));
  col *= 1. - amount*.11*(1.-f)*(.2+band*.8);
  col += f*amount*band*boost*(.028+.06*(1.-lum));
  return col;
}
`;
const frontFragment =
  common +
  `
uniform sampler2D tSubject, tBackground, tText, tLine, tEffects;
void main() {
  vec2 uv = vUv;
  vec2 su = ((parallax(uv,uDepth)-.5)*uScale/uFit+.5)*uSafeScale+uSafeOffset;
  vec2 bu = parallax(uv,uBgDepth);
  vec4 subject = texture2D(tSubject,clamp(su,0.,1.));
  subject.a *= inside(su)*(1.-uRelief);
  vec3 bg = texture2D(tBackground,clamp(bu,0.,1.)).rgb;
  vec3 col = mix(bg,subject.rgb,subject.a);
  if (uFinish > 2.5) col = col * vec3(1.02, .95, .78) + vec3(.05, .012, 0.0);
  // Effects layer floats between the subject and the text: above the character,
  // below the typography, with its own mid-depth parallax.
  vec2 eu = parallax(uv,uFxDepth);
  vec4 fx = texture2D(tEffects,clamp(eu,0.,1.));
  col = mix(col,fx.rgb,fx.a*(1.-uRelief)*uHasFx);
  // ---- 分区材质(边框 / 文字 / 主体 / 底纹) ----
  float tilt = clamp((length(uView.xy) - 0.12) * 3.2, 0.0, 1.0);
  float gate = mix(0.15, 1.0, tilt);
  float band = sweep(uv);
  float goldBoost = uFinish > 2.5 ? 1.7 : 1.0;
  float edge = 1.-smoothstep(.015,.06,min(min(uv.x,1.-uv.x),min(uv.y,1.-uv.y)));
  vec2 tu = parallax(uv, uTextDepth);
  vec4 text = texture2D(tText, clamp(tu,0.,1.));
  text.a *= inside(tu);
  float wFrame = clamp(edge,0.,1.);
  float wText = clamp(text.a*(1.-uRelief),0.,1.)*(1.-wFrame);
  float wSub = clamp(subject.a,0.,1.)*(1.-wFrame)*(1.-wText);
  float wBg = clamp(1.-wFrame-wText-wSub,0.,1.);
  // 主体 / 底纹: 先按各自材质处理表面色
  vec3 cSub = applyMat(col, uv, uMatType.z, uMatAmt.z*gate, band, goldBoost);
  vec3 cBg = applyMat(col, uv, uMatType.w, uMatAmt.w*gate, band, goldBoost);
  col = cSub*wSub + cBg*wBg + col*(wFrame+wText);
  // 边框: 材质 + 边缘高光
  float aFrame = clamp(uMatAmt.x,0.,1.)*gate;
  vec3 fFrame = styleFilm(uv, uMatType.x);
  col = mix(col, fFrame*.75+.21, wFrame*aFrame*(uFinish > 2.5 ? .34 : .26));
  // sparkle / 线稿辉光: 用各区域里的最大强度
  float sparkAmt = max(max(uMatAmt.x,uMatAmt.y), max(uMatAmt.z,uMatAmt.w))*gate;
  vec2 cell = floor(uv*vec2(480.,720.));
  float flake = step(.9975,hash(cell))*pow(.5+.5*sin(hash(cell+8.)*30.+uView.x*20.+uTime*.6),10.);
  col += styleFilm(uv,uMatType.x)*flake*sparkAmt*.08;
  float line = (1.-smoothstep(.06,.25,texture2D(tLine,clamp(su,0.,1.)).r))*uHasLine;
  col += line*inside(su)*subject.a*band*sparkAmt*.035;
  // 文字: 自己的材质(可做烫金字)
  if (wText > 0.001) {
    vec3 cText = applyMat(text.rgb, tu, uMatType.y, uMatAmt.y*gate, band, goldBoost);
    col = mix(col, cText, wText);
  }
  gl_FragColor = vec4(pow(clamp(col,0.,1.),vec3(2.2)),1.);
  #include <colorspace_fragment>
}
`;
const edgeFragment =
  common +
  `
void main() {
  vec3 col = mix(vec3(.66,.69,.67),styleFilm(vUv,uMatType.x)*.6+.35,clamp(uMatAmt.x,0.,1.)*.7);
  gl_FragColor=vec4(pow(col,vec3(2.2)),1.);
  #include <colorspace_fragment>
}
`;
const backFragment =
  common +
  `
uniform sampler2D tBack;
void main() {
  vec2 uv=vec2(1.-vUv.x,vUv.y);
  vec4 art=texture2D(tBack,uv);
  vec3 col=vec3(.956,.961,.946);
  col*=1.-strength()*.12*(1.-film(vUv));
  col+=film(vUv)*sweep(vUv)*strength()*.055;
  col=mix(col,art.rgb,art.a);
  gl_FragColor=vec4(pow(clamp(col,0.,1.),vec3(2.2)),1.);
  #include <colorspace_fragment>
}
`;

const subjectFragment = common + `
uniform sampler2D tSubject;
void main() {
  vec4 art=texture2D(tSubject,vUv);
  if(art.a<.06)discard;
  vec2 px=1./vec2(1024.,1630.);
  float inner=min(min(texture2D(tSubject,vUv+vec2(px.x*2.,0.)).a,texture2D(tSubject,vUv-vec2(px.x*2.,0.)).a),min(texture2D(tSubject,vUv+vec2(0.,px.y*2.)).a,texture2D(tSubject,vUv-vec2(0.,px.y*2.)).a));
  vec3 col=art.rgb;
  col+=film(vUv)*sweep(vUv)*strength()*.10;
  col=mix(col,vec3(.86,.72,.40),(1.-inner)*.22);
  gl_FragColor=vec4(pow(clamp(col,0.,1.),vec3(2.2)),art.a);
  #include <colorspace_fragment>
}
`;
const effectsFragment = common + `
uniform sampler2D tEffects;
void main() {
  vec4 art=texture2D(tEffects,vUv);
  // The relief effects layer is a pre-cut RGBA asset: use its real alpha so
  // thorn/spark deco keeps its silhouette instead of a color-channel matte.
  float alpha=art.a;
  if(alpha<.015)discard;
  vec3 col=art.rgb;
  col+=film(vUv)*sweep(vUv)*strength()*.08;
  gl_FragColor=vec4(pow(clamp(col,0.,1.),vec3(2.2)),alpha);
  #include <colorspace_fragment>
}
`;
const textFragment = common + `
uniform sampler2D tText;
void main(){vec4 art=texture2D(tText,vUv);if(art.a<.02)discard;gl_FragColor=vec4(pow(art.rgb,vec3(2.2)),art.a);
  #include <colorspace_fragment>
}
`;

function canvasTexture(canvas) {
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.NoColorSpace;
  return texture;
}
function backTexture() {
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
  const field = (label, y, value) => {          // 没数据 → 完全不显示(不留占位线)
    if (!value) return;
    tracked(label, 512, y, "12px 'Segoe UI', Arial", 3.2, "rgba(" + (S.frame === "bold" ? "20,20,20,.62" : "139,132,116,.92") + ")");
    tracked(value, 512, y + 30, "17px 'Segoe UI', Arial", 1, "rgba(" + (dark ? "232,217,181,.94" : "58,52,44,.9") + ")");
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
  // 背面 = 卡牌身份证: 只放 CARD # 与日期(+可选 Created/Owned/QR), 不放主题文案
  tracked(config.edition || "", 512, 312, "20px 'Segoe UI', Arial", 2.4, goldC);
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
  tracked(config.title || "", 512, 900,
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
  ctx.beginPath(); ctx.moveTo(372, 1104); ctx.lineTo(652, 1104); ctx.stroke();
  if (config.name) tracked("FOR " + String(config.name).toUpperCase(), 512, 1150, "16px 'Segoe UI', Arial", 4, inkC);
  if (config.technique) tracked(config.technique, 512, 1206, "22px 'Segoe UI', Arial", 2, goldC);
  if (config.wish) tracked(config.wish, 512, 1258, "italic 21px Palatino Linotype, Georgia, serif", 0.6,
                           "rgba(" + (dark ? "214,200,168,.78" : "58,52,44,.70") + ")");
  field("CREATED BY", 1330, config.createdBy || "");
  field("OWNED BY", 1396, config.ownedBy || "");
  return canvasTexture(c);
}function addShadow() {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const ctx = c.getContext("2d");
  const grad = ctx.createRadialGradient(128, 128, 6, 128, 128, 128);
  grad.addColorStop(0, "rgba(29,35,25,0.13)");
  grad.addColorStop(0.4, "rgba(29,35,25,0.055)");
  grad.addColorStop(1, "rgba(29,35,25,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 256, 256);
  shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(8.8, 11.8),
    new THREE.MeshBasicMaterial({
      map: canvasTexture(c),
      transparent: true,
      depthWrite: false,
    }),
  );
  shadow.position.set(0.28, -0.48, -0.5);
  scene.add(shadow);
}
// Render a lucide node tree (["svg", attrs, [children]]) into an svg element.
function renderIconNode(node) {
  const [tag, attrs = {}, children = []] = node;
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  for (const child of children) el.appendChild(renderIconNode(child));
  return el;
}
function refreshIcons() {
  const overrides = { "stroke-width": 1.5 };
  document.querySelectorAll("[data-lucide]").forEach((el) => {
    const name = el.getAttribute("data-lucide");
    const tree = icons[name];
    if (!tree) return;
    const [tag, defaults = {}, children = []] = tree;
    const svg = renderIconNode([tag, { ...defaults, ...overrides }, children]);
    el.replaceChildren(svg);
  });
}
function notice(message) {
  clearTimeout(noticeTimer);
  $("notice").textContent = message;
  $("notice").hidden = false;
  noticeTimer = setTimeout(() => ($("notice").hidden = true), 2600);
}
async function init() {
  refreshIcons();
  const response = await fetch("./card-config.json");
  if (!response.ok) throw Error("作品配置未找到");
  config = await response.json();
  document.title = config.title + " · 白相";
  // §16 缺少 3D 模型 → 2D/CSS-3D 回退
  if (!(config.assets && config.assets.model)) {
    fallback3D(new Error("缺少 3D 模型, 使用 2D 回退"));
    return;
  }
  for (const [id, key] of [
    ["card-title", "title"],
    ["subtitle", "subtitle"],
    ["description", "description"],
    ["edition", "edition"],
    ["about-description", "description"],
    ["about-edition", "edition"],
  ])
    $(id).textContent = config[key] || "";
  $("about-title").textContent = [config.subtitle, config.title]
    .filter(Boolean)
    .join(" / ");
  await document.fonts.load("500 42px Atelier");
  try {
    renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      preserveDrawingBuffer: true,
      powerPreference: "high-performance",
    });
  } catch (error) {
    // First retry with the most permissive context attributes — some setups
    // reject "high-performance" but accept the default.
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        preserveDrawingBuffer: true,
        powerPreference: "default",
        failIfMajorPerformanceCaveat: false,
      });
    } catch (retryError) {
      // No WebGL at all (browser hardware acceleration off): switch to the
      // CSS-3D card — still layered 3D, just without the shader engine.
      fallback3D(retryError);
      return;
    }
  }
  renderer.setClearColor(config.appearance?.background || "#fafafa", 1);
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  stage.append(renderer.domElement);
  renderer.domElement.setAttribute("aria-hidden", "true");
  const textureLoader = new THREE.TextureLoader();
  const A = config.assets || {};
  const blankTex = () => {
    const t = new THREE.DataTexture(new Uint8Array([0, 0, 0, 0]), 1, 1);
    t.needsUpdate = true;
    return t;
  };
  // §16 缺少分层素材时回退到整张 front.png; 连 front.png 都没有才报错
  const hasLayers = !!(A.subject && A.background && A.text);
  let textures;
  if (hasLayers) {
    textures = await Promise.all(
      ["subject", "background", "text"].map((name) => textureLoader.loadAsync(A[name])),
    );
  } else if (A.front) {
    const frontOnly = await textureLoader.loadAsync(A.front);
    textures = [blankTex(), frontOnly, blankTex()];
    console.warn("[holo-card] 缺少分层素材, 已回退到 front.png");
  } else {
    throw Error("缺少卡面素材: 需要分层图或 front.png");
  }
  const line = config.assets.lineart
    ? await textureLoader.loadAsync(config.assets.lineart)
    : new THREE.DataTexture(new Uint8Array([255, 255, 255, 255]), 1, 1);
  line.needsUpdate = true;
  // Optional effects overlay (sparks/thorn deco): drawn between subject and text.
  // A transparent 1x1 fallback keeps the front shader valid without it.
  const hasFx = !!config.assets.effects;
  const effects = hasFx
    ? await textureLoader.loadAsync(config.assets.effects)
    : new THREE.DataTexture(new Uint8Array([0, 0, 0, 0]), 1, 1);
  effects.colorSpace = THREE.NoColorSpace;
  if (!hasFx) effects.needsUpdate = true;
  [...textures, line, effects].forEach((t) => {
    t.colorSpace = THREE.NoColorSpace;
    t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  });
  const p = config.parameters || {};
  // 材质系统: 四区域(边框/文字/主体/底纹) × 四种材质
  const MAT_INDEX = { matte: 0, pearl: 1, foil: 2, gloss: 3 };
  const matCfg = config.material || {};
  const holoOn = matCfg.holoEnabled !== false &&
    String((config.appearance || {}).finish || "").toLowerCase() !== "original";
  const matRegion = matCfg.regions || {};
  const matAmount = matCfg.amounts || {};
  const foilBase = p.foil ?? 0.52;
  const matTypeOf = (k, d) => MAT_INDEX[String(matRegion[k] || d).toLowerCase()] ?? MAT_INDEX[d];
  const matAmtOf = (k, d) => (holoOn ? (matAmount[k] ?? (d === "text" ? 0 : foilBase)) : 0);
  const matType = [matTypeOf("frame", "pearl"), matTypeOf("text", "matte"),
                   matTypeOf("subject", "pearl"), matTypeOf("background", "pearl")];
  const matAmt = [matAmtOf("frame", "frame"), matAmtOf("text", "text"),
                  matAmtOf("subject", "subject"), matAmtOf("background", "background")];
  const imageAspect = textures[0].image.width / textures[0].image.height;
  const fit =
    config.artworkFit ||
    (config.sourceMode === "reference"
      ? [
          Math.min(0.87, (0.87 * imageAspect) / (2 / 3)),
          Math.min(0.87, (0.87 * (2 / 3)) / imageAspect),
        ]
      : [1, 1]);
  uniforms = {
    tSubject: { value: textures[0] },
    tBackground: { value: textures[1] },
    tText: { value: textures[2] },
    tLine: { value: line },
    tEffects: { value: effects },
    tBack: { value: backTexture() },
    uTime: { value: 0 },
    uView: { value: new THREE.Vector3(0, 0, 1) },
    uFit: { value: new THREE.Vector2(...fit) },
    uFoil: { value: p.foil ?? 0.52 },
    uMatType: { value: new THREE.Vector4(matType[0], matType[1], matType[2], matType[3]) },
    uTextDepth: { value: p.textDepth ?? 0 },
    uMatAmt: { value: new THREE.Vector4(matAmt[0], matAmt[1], matAmt[2], matAmt[3]) },
    uScale: { value: p.subjectScale ?? 1 },
    uDepth: { value: p.subjectDepth ?? 0.32 },
    uBgDepth: { value: p.backgroundDepth ?? -0.18 },
    uSafeScale: { value: config.safeArea?.scale ?? 1 },
    // The shader's V axis is flipped relative to Blender's UV space, so the
    // vertical safe-area offset needs a compensating transform (x is identical).
    uSafeOffset: {
      value: new THREE.Vector2(
        config.safeArea?.offset?.[0] ?? 0,
        1 - (config.safeArea?.scale ?? 1) - (config.safeArea?.offset?.[1] ?? 0),
      ),
    },
    uFxDepth: { value: p.effectsDepth ?? 0.14 },
    uHasFx: { value: hasFx ? 1 : 0 },
    uFinish: { value: 0 },
    uHasLine: { value: config.assets.lineart ? 1 : 0 },
    uRelief: { value: config.sourceMode === "relief" ? 1 : 0 },
  };
  const material = (fragment) =>
    new THREE.ShaderMaterial({
      uniforms,
      vertexShader: vertex,
      fragmentShader: fragment,
      side: THREE.FrontSide,
    });
  const materials = {
    web_front: material(frontFragment),
    web_back: material(backFragment),
    web_edge: material(edgeFragment),
    web_gold: new THREE.MeshBasicMaterial({ color: "#c9a24a" }),
  };
  for (const [role,fragment] of [["web_subject",subjectFragment],["web_effects",effectsFragment],["web_text",textFragment]]) {
    materials[role] = material(fragment);
    materials[role].transparent = true;
    materials[role].depthWrite = role !== "web_effects";
  }
  const gltf = await new GLTFLoader().loadAsync(config.assets.model);
  root = new THREE.Group();
  root.add(gltf.scene);
  scene.add(root);
  let faces = 0;
  gltf.scene.traverse((ob) => {
    if (!ob.isMesh) return;
    const role = ob.material?.name;
    if (role === "web_text" && config.sourceMode !== "relief") {
      ob.visible = false;
      return;
    }
    if (role === "web_front") faces++;
    ob.material = materials[role] || materials.web_edge;
    if (role === "web_subject") reliefLayers.subject.push(ob);
    if (role === "web_effects") reliefLayers.effects.push(ob);
    if (role === "web_text") reliefLayers.text.push(ob);
  });
  if (!faces) throw Error("卡片模型缺少正面材质");
  root.updateMatrixWorld(true);
  for (const meshes of Object.values(reliefLayers)) for (const mesh of meshes) {
    root.attach(mesh);
    mesh.userData.basePosition=mesh.position.clone();
    mesh.userData.baseScale=mesh.scale.clone();
  }
  if (config.sourceMode === "relief" && !reliefLayers.subject.length) throw Error("缺少独立人物层，请重新生成模型");
  addShadow();
  const settingsHome=$('parameter-panel').parentElement;
  const responsiveSettings=()=>{
    const panel=$('parameter-panel');
    if(matchMedia('(max-width:760px)').matches)document.querySelector('main').append(panel);
    else settingsHome.append(panel);
  };
  responsiveSettings();window.addEventListener('resize',responsiveSettings);
  setupControls();
  document
    .querySelectorAll("button[disabled],input[disabled]")
    .forEach((el) => (el.disabled = false));
  new ResizeObserver(resize).observe(stage);
  resize();
  renderer.compile(scene, camera);
  renderer.render(scene, camera);
  const shaderErrors = (renderer.info.programs || []).filter(
    (p) => p.diagnostics && !p.diagnostics.runnable,
  );
  if (shaderErrors.length) {
    renderer.dispose();
    renderer.domElement.remove();
    fallback3D(new Error("当前设备无法显示卡面材质"));
    return;
  }
  $("loading").remove();
  root.rotation.set(targetX, targetY, 0);
  window.__holo = {
    ready: true,
    config,
    renderer,
    root,
    uniforms,
    camera,
    reset,
    flip,
    modelSource: config.assets.model,
    layers: reliefLayers,
    getState: () => ({ auto, flipped, finish, zoom }),
  };
  setFinish(config.appearance?.finish || "pearl");
  setAuto(!media.matches);
  renderer.setAnimationLoop(animate);
}
// Layered 3D card built with CSS 3D transforms — used only when WebGL is
// unavailable (browser hardware acceleration off). It keeps the real depth
// stack: layers float at their configured offsets, the card tilts with the
// pointer, sways when idle, flips to a gold back, and the foil sheen follows
// the cursor. If WebGL comes back, the full shader engine takes over instead.
function fallback3D(error) {
  console.warn("[holo-card] WebGL unavailable, using CSS-3D fallback:", error);
  const roleZ = { background: -48, effects: -25, subject: -8, lineart: 24, text: 28 };
  const wrap = document.createElement("div");
  wrap.className = "fallback3d";
  const flipper = document.createElement("div");
  flipper.className = "flipper3d";
  const card = document.createElement("div");
  card.className = "card3d";
  card.id = "card3d";
  const front = document.createElement("div");
  front.className = "face3d front3d";
  const layers = new Map();
  for (const name of ["background", "effects", "subject", "lineart", "text"]) {
    if (!config?.assets?.[name]) continue;
    const layer = document.createElement("div");
    layer.className = "layer3d";
    const img = document.createElement("img");
    img.src = config.assets[name];
    img.alt = config.title || "卡片";
    img.loading = "eager";
    layer.append(img);
    front.append(layer);
    // White-background line art must not cover the subject: multiply drops the
    // white base and keeps only the dark contour strokes on top of the artwork.
    if (name === "lineart") layer.style.mixBlendMode = "multiply";
    layers.set(name, { el: layer, z: roleZ[name] });
  }
  // §16 没有分层但有 front.png 时, 整张正片作为唯一图层
  if (!layers.size && config?.assets?.front) {
    const layer = document.createElement("div");
    layer.className = "layer3d";
    const img = document.createElement("img");
    img.src = config.assets.front;
    img.alt = config.title || "卡片";
    img.loading = "eager";
    layer.append(img);
    front.append(layer);
    layers.set("front", { el: layer, z: -48 });
  }
  const foil = document.createElement("div");
  foil.className = "foil3d";
  front.append(foil);
  const back = document.createElement("div");
  back.className = "face3d back3d";
  if (config?.assets?.back) {
    const bimg = document.createElement("img");
    bimg.src = config.assets.back;
    bimg.alt = "卡片背面";
    bimg.loading = "eager";
    bimg.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;";
    back.append(bimg);
  } else {
    const backMark = document.createElement("span");
    backMark.className = "back-mark";
    backMark.textContent = config.title || "CARD";
    back.append(backMark);
  }
  card.append(front, back);
  flipper.append(card);
  wrap.append(flipper);
  stage.append(wrap);
  $("loading").remove();

  // ---- interaction state (independent of the WebGL path) ----
  let tx = -0.03, ty = -0.06, curX = 0, curY = 0, curFlip = 0, flipTarget = 0;
  let lastMove = 0, sway = !media.matches;
  let scale = 1, depthScale = 1, bgScale = 1;
  const applyLayers = () => {
    for (const [name, { el, z }] of layers) {
      const s = name === "background" ? bgScale : 1;
      el.style.transform = `translateZ(${(z * depthScale * s).toFixed(2)}px)`;
    }
  };
  applyLayers();
  stage.addEventListener("pointermove", (e) => {
    const r = stage.getBoundingClientRect();
    tx = Math.max(-0.5, Math.min(0.5, ((e.clientY - r.top) / r.height - 0.5) * 0.9));
    ty = Math.max(-0.5, Math.min(0.5, ((e.clientX - r.left) / r.width - 0.5) * 1.1));
    lastMove = performance.now();
    const c = card.getBoundingClientRect();
    front.style.setProperty("--mx", Math.round(((e.clientX - c.left) / c.width) * 100) + "%");
    front.style.setProperty("--my", Math.round(((e.clientY - c.top) / c.height) * 100) + "%");
  });
  stage.addEventListener("pointerleave", () => { lastMove = 0; });
  const frame = (now) => {
    if (sway && now - lastMove > 1500) {
      const t = now / 1000;
      tx = Math.sin(t * 0.7) * 0.07 + 0.05;
      ty = Math.sin(t * 0.55) * 0.11 - 0.18;
    }
    curX += (tx - curX) * 0.08;
    curY += (ty - curY) * 0.08;
    curFlip += (flipTarget - curFlip) * 0.12;
    flipper.style.transform = `rotateX(${curX.toFixed(4)}rad) rotateY(${curY.toFixed(4)}rad) scale(${scale})`;
    card.style.transform = `rotateY(${curFlip.toFixed(4)}rad)`;
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  // ---- control wiring (mirrors the WebGL controls) ----
  const setFlip = (value) => {
    flipped = value;
    flipTarget = flipped ? Math.PI : 0;
    faceLabels();
  };
  const setAutoUI = (value) => {
    sway = value;
    const b = $("auto");
    b.setAttribute("aria-pressed", String(value));
    b.setAttribute("aria-label", value ? "暂停旋转" : "自动旋转");
    b.title = value ? "暂停旋转" : "自动旋转";
    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", value ? "pause" : "play");
    b.replaceChildren(icon);
    refreshIcons();
  };
  const fallbackFinish = (value) => {
    front.classList.remove("finish-gold", "finish-silver", "finish-pearl", "finish-original");
    front.classList.add("finish-" + value);
    document
      .querySelectorAll("[data-finish]")
      .forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.finish === value)));
    $("finish-name").textContent =
      { pearl: "珠光", silver: "银箔", gold: "烫金", original: "原画" }[value];
    $("foil").disabled = value === "original";
  };
  $("info").disabled = false;
  $("info").onclick = () => $("about").showModal();
  $("flip").disabled = false;
  $("flip").onclick = () => setFlip(!flipped);
  $("front").disabled = false;
  $("front").onclick = () => setFlip(false);
  $("back").disabled = false;
  $("back").onclick = () => setFlip(true);
  $("auto").disabled = false;
  $("auto").onclick = () => setAutoUI(!sway);
  $("reset").disabled = false;
  $("reset").onclick = () => {
    tx = -0.03; ty = -0.06; lastMove = 0;
    setFlip(false);
    scale = 1; depthScale = 1; bgScale = 1;
    $("scale").value = 1; $("scale-value").textContent = "1.00";
    $("depth").value = 0; $("depth-value").textContent = "0.00";
    $("bg-depth").value = 0; $("bg-depth-value").textContent = "0.00";
    applyLayers();
  };
  $("settings").disabled = false;
  $("settings").onclick = () => {
    const panel = $("parameter-panel");
    panel.hidden = !panel.hidden;
    $("settings").setAttribute("aria-expanded", String(!panel.hidden));
  };
  const bindRange = (id, output, fn, decimals = 2) => {
    $(id).disabled = false;
    $(id).addEventListener("input", () => {
      const v = Number($(id).value);
      $(output).textContent = v.toFixed(decimals);
      fn(v);
    });
  };
  bindRange("scale", "scale-value", (v) => { scale = v; });
  bindRange("depth", "depth-value", (v) => {
    depthScale = Math.max(0.1, 1 + v * 4);
    applyLayers();
  });
  bindRange("bg-depth", "bg-depth-value", (v) => {
    bgScale = Math.max(0.1, 1 + v * 4);
    applyLayers();
  });
  document.querySelectorAll("[data-finish]").forEach((b) => {
    b.disabled = false;
    b.onclick = () => fallbackFinish(b.dataset.finish);
  });
  bindRange("foil", "foil-value", (v) => {
    front.style.setProperty("--foil-amount", v);
  }, 0);
  $("foil-value").textContent = Math.round(Number($("foil").value) * 100) + "%";
  front.style.setProperty("--foil-amount", $("foil").value);
  // Seed scale from config; depth sliders start neutral (the layered base
  // offsets above already encode the default depth profile).
  if (config.parameters?.subjectScale) {
    scale = config.parameters.subjectScale;
    $("scale").value = config.parameters.subjectScale;
  }
  applyLayers();
  fallbackFinish(config.appearance?.finish || "gold");
  notice("浏览器未开启 WebGL：已用轻量 3D 模式显示（层次保留）");
  window.__holo = { ready: false, error: String(error), fallback3d: true };
}
function resize() {
  if (!renderer) return;
  const width = stage.clientWidth,
    height = stage.clientHeight;
  const aspect = width / height;
  const halfHeight = Math.max(config.sourceMode === "relief" ? 6.25 : 5.45, 4.5 / aspect) / zoom;
  camera.left = -halfHeight * aspect;
  camera.right = halfHeight * aspect;
  camera.top = halfHeight;
  camera.bottom = -halfHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
}
function setAuto(value) {
  auto = value;
  $("auto").setAttribute("aria-pressed", String(auto));
  $("auto").setAttribute("aria-label", auto ? "暂停旋转" : "自动旋转");
  $("auto").title = auto ? "暂停旋转" : "自动旋转";
  $("auto").replaceChildren();
  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", auto ? "pause" : "play");
  $("auto").append(icon);
  refreshIcons();
}
function setFinish(value) {
  finish = value;
  uniforms.uFinish.value = { pearl: 0, silver: 1, original: 2, gold: 3 }[value] ?? 3;
  document
    .querySelectorAll("[data-finish]")
    .forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.finish === value)),
    );
  $("finish-name").textContent = {
    pearl: "珠光",
    silver: "银箔",
    gold: "烫金",
    original: "原画",
  }[value];
  $("foil").disabled = value === "original";
}
function faceLabels() {
  $("front").setAttribute("aria-pressed", String(!flipped));
  $("back").setAttribute("aria-pressed", String(flipped));
  $("view-label").textContent = flipped ? "02 / BACK" : "01 / FRONT";
}
function flip(value = !flipped) {
  flipped = value;
  setAuto(false);
  targetY = flipped ? Math.PI : 0;
  targetX = 0;
  faceLabels();
}
// Layered relief stack: clearly separated depths so the card reads as a
// lightbox diorama — subject / effects / text each float on their own plane
// (offsets in card-space units, card half-height ≈ 5.45).
const RELIEF_STEP = 0.22;
function layoutRelief() {
  const z = Number($("depth").value);
  const invScale = 1 / Number($("scale").value);
  const place = (meshes, dz) => {
    for (const mesh of meshes) {
      mesh.position.z = z + dz;
      mesh.scale.copy(mesh.userData.baseScale).multiplyScalar(invScale);
    }
  };
  place(reliefLayers.subject, 0);
  place(reliefLayers.effects, RELIEF_STEP);
  place(reliefLayers.text, RELIEF_STEP * 2);
}
function updateInput(id, name) {
  const input = $(id);
  uniforms[name].value = Number(input.value);
  if (config.sourceMode === "relief") layoutRelief();
  $(id + "-value").value =
    id === "foil"
      ? Math.round(input.value * 100) + "%"
      : Number(input.value).toFixed(2);
}
function reset() {
  targetX = -0.035;
  targetY = -0.15;
  zoom = 1;
  flipped = false;
  setAuto(false);
  faceLabels();
  const p = config.parameters || {};
  const defaults = {
    foil: p.foil ?? 0.52,
    scale: p.subjectScale ?? 1,
    depth: p.subjectDepth ?? 0.32,
    "bg-depth": p.backgroundDepth ?? -0.18,
  };
  settings.forEach(([id, name]) => {
    $(id).value = defaults[id];
    updateInput(id, name);
  });
  setFinish(config.appearance?.finish || "pearl");
  resize();
}
function toggleSettings(open = !$("parameter-panel").hidden) {
  $("parameter-panel").hidden = open;
  $("settings").setAttribute("aria-expanded", String(!open));
}
function setupControls() {
  if (config.sourceMode === "relief") {
    // Layered card relief: subject base plane 0..0.9, effects/text above it.
    $("depth").min="0.0";$("depth").max="0.9";
    $("scale").min="0.92";$("scale").max="1.3";
  }
  settings.forEach(([id, name]) => {
    $(id).value = uniforms[name].value;
    updateInput(id, name);
    $(id).addEventListener("input", () => updateInput(id, name));
  });
  stage.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    dragging = true;
    setAuto(false);
    lastPointer = { x: e.clientX, y: e.clientY };
    stage.setPointerCapture(e.pointerId);
    stage.classList.add("dragging");
    stage.focus({ preventScroll: true });
  });
  stage.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const base = flipped ? Math.PI : 0;
    targetY = THREE.MathUtils.clamp(
      targetY + (e.clientX - lastPointer.x) * 0.006,
      base - 0.65,
      base + 0.65,
    );
    targetX = THREE.MathUtils.clamp(
      targetX + (e.clientY - lastPointer.y) * 0.004,
      -0.36,
      0.36,
    );
    lastPointer = { x: e.clientX, y: e.clientY };
  });
  const release = () => {
    dragging = false;
    stage.classList.remove("dragging");
  };
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((type) =>
    stage.addEventListener(type, release),
  );
  stage.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      zoom = THREE.MathUtils.clamp(zoom - e.deltaY * 0.001, 0.82, 1.05);
      resize();
    },
    { passive: false },
  );
  stage.addEventListener("keydown", (e) => {
    if (
      ![
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "ArrowDown",
        "f",
        "F",
        "r",
        "R",
        " ",
      ].includes(e.key)
    )
      return;
    e.preventDefault();
    if (e.key === " ") {
      setAuto(!auto);
      return;
    }
    if (e.key.toLowerCase() === "f") {
      flip();
      return;
    }
    if (e.key.toLowerCase() === "r") {
      reset();
      return;
    }
    setAuto(false);
    const base = flipped ? Math.PI : 0;
    if (e.key === "ArrowLeft") targetY -= 0.08;
    if (e.key === "ArrowRight") targetY += 0.08;
    if (e.key === "ArrowUp") targetX -= 0.06;
    if (e.key === "ArrowDown") targetX += 0.06;
    targetY = THREE.MathUtils.clamp(targetY, base - 0.65, base + 0.65);
    targetX = THREE.MathUtils.clamp(targetX, -0.36, 0.36);
  });
  $("auto").onclick = () => {
    if (flipped) flip(false);
    setAuto(!auto);
  };
  $("flip").onclick = () => flip();
  $("front").onclick = () => flip(false);
  $("back").onclick = () => flip(true);
  $("reset").onclick = reset;
  document
    .querySelectorAll("[data-finish]")
    .forEach((b) => (b.onclick = () => setFinish(b.dataset.finish)));
  $("settings").onclick = () => toggleSettings();
  $("close-settings").onclick = () => {
    toggleSettings(true);
    $("settings").focus();
  };
  document.addEventListener("pointerdown", (e) => {
    if (
      !$("parameter-panel").hidden &&
      !$("parameter-panel").contains(e.target) &&
      !$("settings").contains(e.target)
    )
      toggleSettings(true);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("parameter-panel").hidden) {
      toggleSettings(true);
      $("settings").focus();
    }
  });
  $("info").onclick = () => {
    toggleSettings(true);
    $("about").showModal();
  };
  $("close-about").onclick = () => $("about").close();
  $("about").onclick = (e) => {
    if (e.target === $("about")) {
      const r = $("about").getBoundingClientRect();
      if (
        e.clientX < r.left ||
        e.clientX > r.right ||
        e.clientY < r.top ||
        e.clientY > r.bottom
      )
        $("about").close();
    }
  };
  $("save").onclick = saveCard;
  media.addEventListener("change", () => {
    if (media.matches) setAuto(false);
  });
  renderer.domElement.addEventListener("webglcontextlost", (e) => {
    e.preventDefault();
    renderer.setAnimationLoop(null);
    notice("图形显示已暂停，请刷新页面恢复");
  });
}
function saveCard() {
  try {
    const originalSize = new THREE.Vector2();
    renderer.getSize(originalSize);
    const originalRatio = renderer.getPixelRatio();
    const bounds = {
      left: camera.left,
      right: camera.right,
      top: camera.top,
      bottom: camera.bottom,
    };
    renderer.setPixelRatio(1);
    renderer.setSize(1400, 1800, false);
    const captureHeight = config.sourceMode === "relief" ? 6.4 : 5.4;
    camera.left = -captureHeight*1400/1800;
    camera.right = captureHeight*1400/1800;
    camera.top = captureHeight;
    camera.bottom = -captureHeight;
    camera.updateProjectionMatrix();
    try {
      renderer.render(scene, camera);
      const link = document.createElement("a");
      link.download =
        (config.title || "art-card") +
        "-" +
        (flipped ? "back" : "front") +
        ".png";
      link.href = renderer.domElement.toDataURL("image/png");
      link.click();
      notice("卡片图片已保存");
    } finally {
      Object.assign(camera, bounds);
      camera.updateProjectionMatrix();
      renderer.setPixelRatio(originalRatio);
      renderer.setSize(originalSize.x, originalSize.y, false);
      renderer.render(scene, camera);
    }
  } catch (error) {
    console.error(error);
    notice("图片未能保存，请重试");
  }
}
function animate(now) {
  const dt = Math.min((now - lastTime) / 1000, 0.06) || 0;
  lastTime = now;
  if (document.hidden) return;
  if (!media.matches || auto) elapsed += dt;
  if (auto) {
    targetY = Math.sin(elapsed * 0.42) * 0.23 - 0.055;
    targetX = Math.sin(elapsed * 0.53) * 0.055 - 0.018;
  }
  const ease = media.matches ? 1 : 1 - Math.exp(-dt * 8);
  root.rotation.x += (targetX - root.rotation.x) * ease;
  root.rotation.y += (targetY - root.rotation.y) * ease;
  root.updateMatrixWorld(true);
  uniforms.uView.value
    .copy(camera.position)
    .applyMatrix4(inverse.copy(root.matrixWorld).invert())
    .normalize();
  uniforms.uTime.value = media.matches && !auto ? 0 : elapsed;
  shadow.scale.x = 1 - Math.abs(Math.sin(root.rotation.y)) * 0.14;
  renderer.render(scene, camera);
}
const fail = (message) => {
  const loading = $("loading");
  if (loading && window.__holo && window.__holo.ready) return;
  loading?.classList.add("error");
  loading?.setAttribute("role", "alert");
  loading?.replaceChildren();
  const msg = document.createElement("span");
  msg.textContent = message;
  const retry = document.createElement("button");
  retry.textContent = "重新加载";
  retry.onclick = () => location.reload();
  loading?.append(msg, retry);
  window.__holo = { ready: false, error: message };
};
const LOAD_TIMEOUT_MS = 12000;
let settled = false;
Promise.race([
  init().then(() => {
    settled = true;
  }),
  new Promise((_, reject) =>
    setTimeout(
      () => reject(new Error("卡片加载超时，请检查网络或刷新重试")),
      LOAD_TIMEOUT_MS,
    ),
  ),
]).catch((error) => {
  if (settled) return;
  console.error(error);
  fail("作品暂时无法加载。\n" + error.message);
});
