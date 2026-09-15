// 小程序入口: 只做一件事 —— 把状态栏高度等环境信息算好, 供页面自绘顶栏
App({
  globalData: {
    statusBarHeight: 20,
    cardWidthPx: 320
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
  }
});
