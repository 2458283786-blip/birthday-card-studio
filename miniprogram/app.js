// 小程序入口: 环境信息 + (正式模式时)初始化云开发
const cfg = require('./config.js');

App({
  globalData: {
    statusBarHeight: 20,
    cardWidthPx: 320,
    mode: cfg.mode
  },

  onLaunch() {
    let win = {};
    try {
      win = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
    } catch (e) {
      win = { statusBarHeight: 20, windowWidth: 375 };
    }
    const width = win.windowWidth || 375;
    this.globalData.statusBarHeight = win.statusBarHeight || 20;
    // 卡牌页的卡宽: 屏宽 - 左右各 24px
    this.globalData.cardWidthPx = Math.min(360, width - 48);

    // 正式模式: 初始化云开发(需要正式 AppID; 测试号用不了云开发, 所以默认走 mock)
    if (cfg.mode === 'cloud' && wx.cloud) {
      try {
        wx.cloud.init({ env: cfg.cloudEnv || undefined, traceUser: true });
        this.globalData.cloudReady = true;
      } catch (e) {
        this.globalData.cloudReady = false;
        console.error('[cloud] init 失败', e);
      }
    } else {
      this.globalData.cloudReady = false;
    }
  }
});
