const DEFAULT_CARD = {
  useFlat: true,
  layers: [],
  flat: '',
  back: '',
  hasBack: false
};

function clamp(v, a, b) {
  if (v < a) return a;
  if (v > b) return b;
  return v;
}

Component({
  properties: {
    card: {
      type: Object,
      value: null,
      observer(value) {
        if (!value) return;
        this.setData({
          useFlat: !!value.useFlat,
          layers: value.layers || [],
          flat: value.flat || '',
          back: value.back || '',
          hasBack: !!value.hasBack
        });
      }
    }
  },

  data: Object.assign({
    flipped: false,
    floatOn: true,
    motionStyle: ''
  }, DEFAULT_CARD),

  lifetimes: {
    attached() {
      this.motion = { on: false, base: null, cur: { x: 0, y: 0 }, last: 0 };
      this.startMotion();
    },
    detached() {
      this.stopMotion();
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
    /* 点击(由 WXS 判定"几乎没移动") → 翻面; 没有背面就什么都不做, 不报错 */
    onCardTap() {
      if (!this.data.hasBack) return;
      this.setData({ flipped: !this.data.flipped });
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
        // 忽略: 只是增强能力
      }
      m.on = false;
    },

    onMotion(res) {
      const m = this.motion;
      if (!m) return;
      // 以第一次读数为基准, 避免"拿手机的姿势"不同导致卡片一开始就歪着
      if (!m.base) {
        m.base = { beta: res.beta || 0, gamma: res.gamma || 0 };
        return;
      }
      const tx = clamp(-((res.beta || 0) - m.base.beta) * 0.35, -10, 10);
      // 左右倾斜的方向如果反了, 把下面的 0.42 改成 -0.42 即可(真机上调)
      const ty = clamp(((res.gamma || 0) - m.base.gamma) * 0.42, -14, 14);
      m.cur.x += (tx - m.cur.x) * 0.25;      // 低通: 去掉手上的抖动
      m.cur.y += (ty - m.cur.y) * 0.25;

      const now = Date.now();
      if (now - m.last < 60) return;          // 最高约 16fps 写样式, 靠 CSS 过渡补顺滑
      m.last = now;
      this.setData({
        motionStyle: `transform: rotateX(${m.cur.x.toFixed(2)}deg) rotateY(${m.cur.y.toFixed(2)}deg);`
      });
    }
  }
});
