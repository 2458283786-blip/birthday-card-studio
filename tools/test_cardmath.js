/**
 * 卡牌数学的一致性测试
 * ====================
 * 同一套公式在小程序里有两份实现：
 *   - cardmath.js（逻辑层用, CommonJS）
 *   - holo.wxs  （渲染层用, ES5；WXS 不能 require 普通 JS 模块）
 * 两份不一致 = 手指拖动时和陀螺仪倾斜时表现不一样, 而且不会报错。
 * 这里逐点比对, 另外用"手算的参考值"兜底 —— 防止两份一起错。
 *
 * 参考值来源 = 网页版 showcase 的公式（写在下面的注释里）。
 *
 * 用法: node tools/test_cardmath.js
 */
const fs = require('fs');
const path = require('path');

const MP = path.join(__dirname, '..', 'miniprogram');
const math = require(path.join(MP, 'components', 'holo-card', 'cardmath.js'));

/* 用 Function 把 .wxs 当成 CommonJS 模块求值(node 不认识 .wxs 扩展名) */
function loadWxs(file) {
  const code = fs.readFileSync(file, 'utf8');
  const module_ = { exports: {} };
  // eslint-disable-next-line no-new-func
  new Function('module', 'exports', code)(module_, module_.exports);
  return module_.exports;
}
const wxs = loadWxs(path.join(MP, 'components', 'holo-card', 'holo.wxs'));

let passed = 0;
let failed = 0;
function check(name, cond, extra) {
  if (cond) {
    passed++;
  } else {
    failed++;
    console.log(`  ❌ ${name}${extra ? '  → ' + extra : ''}`);
  }
}
function close(a, b, eps) {
  return Math.abs(a - b) <= (eps || 1e-9);
}

const W = 292;
const H = 438;
const DEPTHS = { background: -0.30, subject: 0.34, effects: 0.64 };
const ANGLES = [];
for (const rx of [-30, -18, -7, 0, 6, 15, 26]) {
  for (const ry of [-32, -20, -9, 0, 8, 21, 32]) ANGLES.push([rx, ry]);
}

console.log(`\n[1] cardmath.js 与 holo.wxs 逐点一致（${ANGLES.length} 个角度组合）`);
let worst = 0;
let worstAt = null;
for (const [rx, ry] of ANGLES) {
  const a = math.layerOffsets(rx, ry, W, H, DEPTHS);
  const b = wxs.__math.layerOffsets(rx, ry, W, H, DEPTHS);
  for (const name of ['background', 'subject', 'effects']) {
    for (const key of ['dx', 'dy', 'scale']) {
      const d = Math.abs(a[name][key] - b[name][key]);
      if (d > worst) {
        worst = d;
        worstAt = `rx=${rx} ry=${ry} ${name}.${key} ${a[name][key]} vs ${b[name][key]}`;
      }
    }
  }
  const fa = math.foilOpacity(rx, ry, 0.55);
  const fb = wxs.__math.foilCalc(rx, ry, 0.55);
  for (const key of ['tilt', 'gate', 'opacity', 'mx', 'my']) {
    const d = Math.abs(fa[key] - fb[key]);
    if (d > worst) {
      worst = d;
      worstAt = `rx=${rx} ry=${ry} foil.${key} ${fa[key]} vs ${fb[key]}`;
    }
  }
}
check(`两份实现最大偏差 ${worst.toExponential(2)}（应 < 1e-9）`, worst < 1e-9, worstAt);

console.log('\n[2] 对照手算参考值（防止两份一起错）');
// 静止：uView=(0,0,1) → 位移 0；length=0 → tilt=0 → gate=0.15 → opacity=0.55*0.15=0.0825
const rest = math.layerOffsets(0, 0, W, H, DEPTHS);
check('静止时各层不位移', close(rest.subject.dx, 0) && close(rest.background.dy, 0),
  JSON.stringify(rest));
const restF = math.foilOpacity(0, 0, 0.55);
check('静止 gate = 0.15', close(restF.gate, 0.15, 1e-12), String(restF.gate));
check('静止 opacity = 0.55×0.15 = 0.0825', close(restF.opacity, 0.0825, 1e-12),
  String(restF.opacity));
check('静止高光在中间 (50,45)', close(restF.mx, 50) && close(restF.my, 45),
  `${restF.mx},${restF.my}`);

// ry=30：uView=(-sin30, 0, cos30)=(-0.5,0,0.866) → |z|=0.866
//   主体 dx = -(-0.5/0.866)*0.20*292*0.34 = +11.46
//   背景 dx = -(-0.5/0.866)*0.20*292*(-0.30) = -10.11
const d30 = math.layerOffsets(0, 30, W, H, DEPTHS);
check('ry=30° 主体右移 ≈ +11.5px', close(d30.subject.dx, 11.46, 0.02), String(d30.subject.dx));
check('ry=30° 背景左移 ≈ -10.1px', close(d30.background.dx, -10.11, 0.02), String(d30.background.dx));
// 背景缩放 = 1 + 2*|dx|/W = 1 + 2*10.11/292 = 1.0692
check('ry=30° 背景放大 ≈ 1.069（盖住位移露出的边）',
  close(d30.background.scale, 1.0692, 0.002), String(d30.background.scale));
check('主体不缩放', close(d30.subject.scale, 1), String(d30.subject.scale));

// ry=30：length(uView.xy)=0.5 → tilt=(0.5-0.12)*3.2=1.216 → clamp 到 1 → gate=1
const f30 = math.foilOpacity(0, 30, 0.55);
check('ry=30° tilt 被夹到 1', close(f30.tilt, 1), String(f30.tilt));
check('ry=30° gate = 1 → opacity = 0.55', close(f30.opacity, 0.55, 1e-9), String(f30.opacity));
check('ry=30° 高光左移 (50-48=2 → 夹到 5)', close(f30.mx, 5), String(f30.mx));

// 小角度：ry=3 → length≈0.0523 → tilt=(0.0523-0.12)*3.2 < 0 → clamp 到 0 → gate=0.15
const f3 = math.foilOpacity(0, 3, 0.55);
check('小角度(3°)仍在"静止档" gate=0.15（克制的全息）',
  close(f3.gate, 0.15, 1e-12), String(f3.gate));

console.log('\n[3] 边界与安全性');
check('极端角度不产生 NaN/Infinity',
  ANGLES.concat([[89, 89], [-89, -89], [120, -150]]).every(([rx, ry]) => {
    const o = math.layerOffsets(rx, ry, W, H, DEPTHS);
    const f = math.foilOpacity(rx, ry, 0.55);
    return ['background', 'subject', 'effects'].every((n) =>
      isFinite(o[n].dx) && isFinite(o[n].dy) && isFinite(o[n].scale))
      && isFinite(f.opacity) && f.opacity >= 0 && f.opacity <= 1
      && f.mx >= 5 && f.mx <= 95 && f.my >= 5 && f.my <= 95;
  }));
check('depth 缺失时按 0 处理（不炸）',
  isFinite(math.layerOffsets(10, 10, W, H, {}).subject.dx));
check('foil 为 0 → 完全透明', close(math.foilOpacity(0, 30, 0).opacity, 0));
check('背景最大放大不超过 1.2', ANGLES.every(([rx, ry]) =>
  math.layerOffsets(rx, ry, W, H, DEPTHS).background.scale <= 1.2));

console.log('\n[4] 样式串能被页面直接使用');
const ls = math.layerStyles(12, 20, W, H, DEPTHS);
check('每层都有 transform 串',
  ['background', 'subject', 'effects', 'text'].every((k) => /^transform:/.test(ls[k] || '')),
  JSON.stringify(ls));
check('文字层固定不动', ls.text === 'transform: translate(0px, 0px);', ls.text);
const fs2 = math.foilStyles(12, 20, 0.55);
check('材质层给出 opacity 与 radial-gradient',
  /^opacity: [\d.]+;$/.test(fs2.foilStyle) && /radial-gradient\(/.test(fs2.sheenStyle),
  fs2.foilStyle + ' | ' + fs2.sheenStyle);

console.log(`\n结果: ${passed} 通过 / ${failed} 失败`);
process.exit(failed ? 1 : 0);
