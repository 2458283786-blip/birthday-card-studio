/**
 * 卡牌的数学：层间视差 + 材质门控（纯函数，方便测）
 * =================================================
 * 两条公式都抄自网页版 showcase（app.js 的 shader 与 CSS-3D 路径）：
 *
 * 1) 视差：uView = (-cos(rx)·sin(ry), sin(rx), cos(rx)·cos(ry))
 *          uvShift = uView.xy / max(|uView.z|, .4) × depth × 0.20
 *          内容位移(px) = -uvShift × 卡牌尺寸
 *    文字层不参与（shader 里它固定在卡面）。
 *
 * 2) 材质门控：tilt = clamp((length(uView.xy) - 0.12) × 3.2, 0, 1)
 *              gate = mix(0.15, 1.0, tilt)      // 静止时也留一点材质感
 *              opacity = foil × gate
 *              高光位置：网页里跟鼠标，这里跟倾斜角度。
 *
 * ⚠️ holo.wxs 里有一份等价的 ES5 实现（WXS 不能 require 这个文件）。
 *    tools/test_cardmath.js 会逐点比对两份实现，改一处必须改另一处。
 */
const DEPTH_DEFAULT = { background: -0.30, subject: 0.34, effects: 0.64 };
const PARALLAX_K = 0.20;      // shader: * .20
const GATE_MIN = 0.15;        // shader: mix(0.15, 1.0, tilt)
const GATE_K = 3.2;           // shader: (length - 0.12) * 3.2
const GATE_BASE = 0.12;

function clamp(v, a, b) {
  if (v < a) return a;
  if (v > b) return b;
  return v;
}

/** 相机方向在卡牌本地空间（归一化前的三个分量） */
function viewVector(rxDeg, ryDeg) {
  const rx = rxDeg * Math.PI / 180;
  const ry = ryDeg * Math.PI / 180;
  const cx = Math.cos(rx);
  return {
    x: -cx * Math.sin(ry),
    y: Math.sin(rx),
    z: cx * Math.cos(ry)
  };
}

/**
 * 各层的位移与缩放。
 * 返回 { background: {dx, dy, scale}, subject: {...}, effects: {...} }
 */
function layerOffsets(rxDeg, ryDeg, W, H, depths) {
  const d = depths || DEPTH_DEFAULT;
  const v = viewVector(rxDeg, ryDeg);
  const az = Math.max(Math.abs(v.z), 0.4);
  const kx = -(v.x / az) * PARALLAX_K * W;
  const ky = -(v.y / az) * PARALLAX_K * H;
  const out = {};
  ['background', 'subject', 'effects'].forEach((name) => {
    const depth = d[name] || 0;
    const dx = kx * depth;
    const dy = ky * depth;
    let scale = 1;
    if (name === 'background') {
      // 背景放大一点, 否则位移后卡边会露空隙
      scale = Math.min(1.2, 1 + 2 * (Math.abs(dx) / W) + 2 * (Math.abs(dy) / H));
    }
    out[name] = { dx, dy, scale };
  });
  return out;
}

/** 材质层：不透明度与高光位置（百分比） */
function foilOpacity(rxDeg, ryDeg, foil) {
  const v = viewVector(rxDeg, ryDeg);
  const len = Math.sqrt(v.x * v.x + v.y * v.y);
  const tilt = clamp((len - GATE_BASE) * GATE_K, 0, 1);
  const gate = GATE_MIN + (1 - GATE_MIN) * tilt;
  return {
    tilt,
    gate,
    opacity: Math.max(0, Math.min(1, (foil || 0) * gate)),
    mx: clamp(50 - ryDeg * 1.6, 5, 95),
    my: clamp(45 + rxDeg * 1.6, 5, 95)
  };
}

/** 给 WXML 用的样式串 */
function layerStyles(rxDeg, ryDeg, W, H, depths) {
  const o = layerOffsets(rxDeg, ryDeg, W, H, depths);
  const out = {};
  Object.keys(o).forEach((name) => {
    const l = o[name];
    out[name] = `transform: translate(${l.dx.toFixed(1)}px, ${l.dy.toFixed(1)}px) scale(${l.scale.toFixed(3)});`;
  });
  out.text = 'transform: translate(0px, 0px);';
  return out;
}

function foilStyles(rxDeg, ryDeg, foil) {
  const f = foilOpacity(rxDeg, ryDeg, foil);
  const op = f.opacity.toFixed(3);
  return {
    foilStyle: `opacity: ${op};`,
    sheenStyle: `opacity: ${op}; background-image: radial-gradient(55% 40% at ${f.mx.toFixed(1)}% ${f.my.toFixed(1)}%, rgba(255,238,190,0.65), transparent 70%);`
  };
}

module.exports = {
  DEPTH_DEFAULT,
  clamp,
  viewVector,
  layerOffsets,
  foilOpacity,
  layerStyles,
  foilStyles
};
