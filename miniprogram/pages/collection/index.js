const { listCards } = require('../../utils/cardview.js');

Page({
  data: {
    statusBar: 20,
    cards: [],
    countText: ''
  },

  onLoad() {
    const app = getApp();
    this.setData({ statusBar: (app && app.globalData.statusBarHeight) || 20 });
    this.load();
  },

  load() {
    listCards().then((cards) => {
      this.setData({
        cards,
        countText: cards.length ? `${cards.length} CARDS` : ''
      });
    });
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

  onShareAppMessage() {
    return { title: '我的收藏 · 数字收藏卡', path: '/pages/collection/index' };
  }
});
