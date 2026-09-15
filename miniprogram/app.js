// 小程序入口: 环境信息 + (正式模式时)初始化云开发
const cfg = require('./config.js');

App({
  globalData: {
    statusBarHeight: 20,
    windowWidth: 375,
    windowHeight: 812,
    cardWidthPx: 292,
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
    this.globalData.windowWidth = width;
    this.globalData.windowHeight = win.windowHeight || 812;
    // 卡牌宽度: 屏宽的 78%, 上限 300px(原来铺得太满, 现在留出呼吸感)
    this.globalData.cardWidthPx = Math.min(300, Math.round(width * 0.78));

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
