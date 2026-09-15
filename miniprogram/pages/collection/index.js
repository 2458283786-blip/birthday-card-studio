const api = require('../../utils/api.js');

Page({
  data: {
    statusBar: 20,
    cards: [],
    countText: '',
    loading: true,
    demo: [],
    // 三种情况要分清楚, 否则断网时会显示"还没有卡", 让人以为卡丢了
    offline: false,     // 用的是本地的上次列表
    failed: false       // 云端没连上, 本地也没缓存 → 给重试
  },

  onLoad() {
    const app = getApp();
    this.setData({
      statusBar: (app && app.globalData.statusBarHeight) || 20,
      demo: api.demoCodes()
    });
  },

  // 从导入页回来、或在别处领了新卡, 都要刷新
  onShow() {
    this.load();
  },

  load() {
    api.listCardsWithState().then((r) => {
      this.setData({
        cards: r.cards,
        countText: r.cards.length ? `${r.cards.length} CARDS` : '',
        loading: false,
        offline: !!r.state.offline,
        failed: !!(r.state.offline && !r.state.cached)
      });
    });
  },

  onRetry() {
    this.setData({ loading: true, failed: false });
    this.load();
  },

  onImport() {
    wx.navigateTo({ url: '/pages/import/index' });
  },

  // 点一张卡 → 带着它在屏幕上的位置跳到卡牌页, 卡牌页据此做"从原位放大"的过渡
  onOpen(e) {
    const cardId = e.currentTarget.dataset.id;
    const query = wx.createSelectorQuery();
    query.select(`#t-${cardId}`).boundingClientRect();
    query.exec((res) => {
      const rect = res && res[0];
      let url = `/pages/card/index?id=${cardId}`;
      if (rect) {
        const r = [rect.left, rect.top, rect.width, rect.height]
          .map((n) => Math.round(n)).join(',');
        url += `&from=${r}`;
      }
      wx.navigateTo({ url });
    });
  },

  /* 仅本地演示模式: 清空本地登记处, 方便反复试 */
  onResetMock() {
    if (!api.isMock()) return;
    api.resetMock();
    this.load();
    wx.showToast({ title: '演示记录已重置', icon: 'none' });
  },

  onShareAppMessage() {
    return { title: '我的收藏 · 数字收藏卡', path: '/pages/collection/index' };
  }
});
