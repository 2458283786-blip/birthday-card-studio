const FLIP_MS = 260;   // 翻面的单程时长(卡片转到侧对屏幕的一半)

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
          flat: value.flat || '',
          back: value.back || '',
          hasBack: !!value.hasBack,
          face: 'front',
          src: value.flat || '',
          flipStyle: 'transform: rotateY(0deg); transition: none;'
        });
      }
    }
  },

  data: {
    flat: '',
    back: '',
    hasBack: false,
    face: 'front',
    src: '',
    flipped: false,
    floatOn: true,
    motionStyle: '',
    flipStyle: 'transform: rotateY(0deg); transition: none;'
  },

  lifetimes: {
    attached() {
      this.motion = { on: false, base: null, cur: { x: 0, y: 0 }, last: 0 };
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
    /* 图片加载失败: 不白屏、不报错, 只是没有画面 —— 留给页面显示空态 */
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

      // 第一段: 转到侧面(90°), 图片此时几乎看不见
      this.setData({
        flipStyle: `transform: rotateY(90deg); transition: transform ${FLIP_MS}ms ease-in;`
      });
      this.t1 = setTimeout(() => {
        // 在"侧对屏幕"的瞬间换图, 再从另一侧转回来 —— 全程只有一张图, 不会镜像
        this.setData({
          face: toBack ? 'back' : 'front',
          src: toBack ? this.data.back : this.data.flat,
          flipped: toBack,
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
      this.setData({
        motionStyle: `transform: rotateX(${m.cur.x.toFixed(2)}deg) rotateY(${m.cur.y.toFixed(2)}deg);`
      });
    }
  }
});
