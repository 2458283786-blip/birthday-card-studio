const FLIP_MS = 260;   // 翻面单程时长(卡片转到侧对屏幕的一半)
const DEPTH_DEFAULT = { background: -0.30, subject: 0.34, effects: 0.64 };

function clamp(v, a, b) {
  if (v < a) return a;
  if (v > b) return b;
  return v;
}

/**
 * 层间视差 —— 与网页版 shader 同一套公式（holo.wxs 里也有一份，改要一起改）：
 *   uView = (-cos(rx)*sin(ry), sin(rx), cos(rx)*cos(ry))
 *   uvShift = uView.xy / max(|uView.z|,.4) * depth * 0.20
 *   内容位移(px) = -uvShift * 卡牌尺寸
 * 文字层不参与视差（shader 里它固定贴在卡面）。
 */
function parallaxStyles(rxDeg, ryDeg, W, H, depths) {
  const d = depths || DEPTH_DEFAULT;
  const rx = rxDeg * Math.PI / 180;
  const ry = ryDeg * Math.PI / 180;
  const cx = Math.cos(rx);
  const vx = -cx * Math.sin(ry);
  const vy = Math.sin(rx);
  const vz = cx * Math.cos(ry);
  const az = Math.max(Math.abs(vz), 0.4);
  const kx = -(vx / az) * 0.20 * W;
  const ky = -(vy / az) * 0.20 * H;

  const out = {};
  ['background', 'subject', 'effects'].forEach((name) => {
    const depth = d[name] || 0;
    const dx = kx * depth;
    const dy = ky * depth;
    let sc = 1;
    if (name === 'background') {
      // 背景放大一点, 否则位移后卡边会露空隙
      sc = Math.min(1.2, 1 + 2 * (Math.abs(dx) / W) + 2 * (Math.abs(dy) / H));
    }
    out[name] = `transform: translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px) scale(${sc.toFixed(3)});`;
  });
  out.text = 'transform: translate(0px, 0px);';
  return out;
}

Component({
  properties: {
    card: {
      type: Object,
      value: null,
      observer(value) {
        if (!value) return;
        const L = {};
        (value.layers || []).forEach((l) => {
          L[l.name] = l.src;
        });
        const app = getApp();
        const W = (app && app.globalData.cardWidthPx) || 292;
        const H = Math.round(W * 1.5);
        const depths = value.depths || DEPTH_DEFAULT;
        this.setData({
          L,
          W,
          H,
          depths,
          flat: value.flat || '',
          back: value.back || '',
          hasBack: !!value.hasBack,
          useFlat: !!value.useFlat,
          face: 'front',
          flipStyle: 'transform: rotateY(0deg); transition: none;',
          motionStyle: '',
          LS: parallaxStyles(0, 0, W, H, depths)
        });
      }
    }
  },

  data: {
    W: 292,
    H: 438,
    depths: DEPTH_DEFAULT,
    L: {},
    LS: {},
    flat: '',
    back: '',
    hasBack: false,
    useFlat: true,
    face: 'front',
    floatOn: true,
    motionStyle: '',
    flipStyle: 'transform: rotateY(0deg); transition: none;'
  },

  lifetimes: {
    attached() {
      const app = getApp();
      const W = (app && app.globalData.cardWidthPx) || 292;
      this.setData({ W, H: Math.round(W * 1.5) });
      this.motion = { on: false, base: null, cur: { x: 0, y: 0 }, last: 0 };
      this.dragging = false;
      this.startMotion();
    },
    detached() {
      this.stopMotion();
      this.clearFlipTimers();
    }
  },

  pageLifetimes: {
    show() {
      this.startMotion();
    },
    hide() {
      this.stopMotion();
    }
  },

  methods: {
    /* 手指按住时, 层的位置归 WXS 管; 陀螺仪不要抢 */
    setDragging(value) {
      this.dragging = !!value;
    },

    onImgError() {
      this.triggerEvent('imgerror');
    },

    clearFlipTimers() {
      if (this.t1) clearTimeout(this.t1);
      if (this.t2) clearTimeout(this.t2);
      this.t1 = null;
      this.t2 = null;
    },

    /* 点击(由 WXS 判定"几乎没移动") → 翻面; 没有背面就什么都不做 */
    onCardTap() {
      if (!this.data.hasBack || this.flipping) return;
      const toBack = this.data.face === 'front';
      if (toBack && !this.data.back) return;
      this.flipping = true;

      // 第一段: 转到侧面(90°), 此时几乎看不见内容
      this.setData({
        flipStyle: `transform: rotateY(90deg); transition: transform ${FLIP_MS}ms ease-in;`
      });
      this.t1 = setTimeout(() => {
        // 在"侧对屏幕"的瞬间换内容, 再从另一侧转回来 —— 全程只有一面, 不会镜像
        this.setData({
          face: toBack ? 'back' : 'front',
          flipStyle: 'transform: rotateY(-90deg); transition: none;'
        });
        this.t2 = setTimeout(() => {
          this.setData({
            flipStyle: `transform: rotateY(0deg); transition: transform ${FLIP_MS}ms ease-out;`
          });
          this.flipping = false;
        }, 20);
      }, FLIP_MS + 10);
    },

    /* 陀螺仪: 增强交互; 设备不支持时静默失败, 手指拖动照常可用 */
    startMotion() {
      const m = this.motion;
      if (!m || m.on) return;
      const handler = (res) => this.onMotion(res);
      this._motionHandler = handler;
      try {
        wx.onDeviceMotionChange(handler);
        wx.startDeviceMotionListening({
          interval: 'ui',
          fail: () => {
            this.stopMotion();
          }
        });
        m.on = true;
      } catch (e) {
        m.on = false;
      }
    },

    stopMotion() {
      const m = this.motion;
      if (!m || !m.on) return;
      try {
        wx.stopDeviceMotionListening({});
        if (this._motionHandler) wx.offDeviceMotionChange(this._motionHandler);
      } catch (e) {
        // 忽略: 这只是增强能力
      }
      m.on = false;
    },

    onMotion(res) {
      const m = this.motion;
      if (!m) return;
      // 以第一次读数为基准, 避免拿手机的姿势不同导致卡一开始就歪着
      if (!m.base) {
        m.base = { beta: res.beta || 0, gamma: res.gamma || 0 };
        return;
      }
      const tx = clamp(-((res.beta || 0) - m.base.beta) * 0.35, -10, 10);
      // 左右倾斜方向如果反了, 把 0.42 改成 -0.42 (真机上调)
      const ty = clamp(((res.gamma || 0) - m.base.gamma) * 0.42, -14, 14);
      m.cur.x += (tx - m.cur.x) * 0.25;      // 低通: 去掉手上的抖动
      m.cur.y += (ty - m.cur.y) * 0.25;

      const now = Date.now();
      if (now - m.last < 60) return;          // 约 16fps 写样式, 靠 CSS 过渡补顺滑
      m.last = now;

      const patch = {
        motionStyle: `transform: rotateX(${m.cur.x.toFixed(2)}deg) rotateY(${m.cur.y.toFixed(2)}deg);`
      };
      if (!this.dragging) {
        patch.LS = parallaxStyles(m.cur.x, m.cur.y, this.data.W, this.data.H, this.data.depths);
      }
      this.setData(patch);
    }
  }
});
