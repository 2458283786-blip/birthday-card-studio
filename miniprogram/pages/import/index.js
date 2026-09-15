const api = require('../../utils/api.js');
const code = require('../../utils/claimcode.js');

const MSG = {
  BAD_CODE: '这个码不对，请检查有没有输错',
  NOT_FOUND: '找不到这个码，确认一下是不是输错了',
  CLAIMED: '这张卡已经被领取了',
  NETWORK: '网络不太好，稍后再试一次',
  FAILED: '导入失败，稍后再试一次'
};

function stamp(ts) {
  const d = new Date(ts || Date.now());
  const p = (n) => (n < 10 ? '0' + n : String(n));
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())}`;
}

Page({
  data: {
    statusBar: 20,
    code: '',
    tip: '',
    tipKind: '',
    busy: false,
    demo: []
  },

  onLoad() {
    const app = getApp();
    this.setData({
      statusBar: (app && app.globalData.statusBarHeight) || 20,
      demo: api.demoCodes()
    });
  },

  onInput(e) {
    this.setData({
      code: code.formatInput(e.detail.value),
      tip: '',
      tipKind: ''
    });
  },

  useDemo(e) {
    this.setData({
      code: code.formatInput(e.currentTarget.dataset.code),
      tip: '',
      tipKind: ''
    });
  },

  onSubmit() {
    if (this.data.busy) return;
    const input = this.data.code;
    if (!input) {
      this.setData({ tip: '请先输入导入码', tipKind: 'warn' });
      return;
    }
    // 先在本地校验：输错一位立刻告诉他，不用白跑一趟服务器
    if (!code.isValid(input)) {
      this.setData({ tip: '导入码是 8 位，请检查一下（横线可以不打）', tipKind: 'warn' });
      return;
    }

    this.setData({ busy: true, tip: '', tipKind: '' });
    api.claimCard(input).then((res) => {
      this.setData({ busy: false });
      if (res.ok && res.card) {
        wx.redirectTo({ url: `/pages/card/index?id=${res.card.cardId}&fresh=1` });
        return;
      }
      let tip = MSG[res.error] || MSG.FAILED;
      if (res.error === 'CLAIMED' && res.claimedAt) {
        tip += `（${stamp(res.claimedAt)} 已被领取）`;
      }
      this.setData({ tip, tipKind: 'warn' });
    });
  },

  /* 仅本地演示模式: 清空本地登记处, 方便反复试 */
  onReset() {
    if (!api.isMock()) return;
    api.resetMock();
    wx.showToast({ title: '演示记录已重置', icon: 'none' });
  },

  goBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack();
    } else {
      wx.reLaunch({ url: '/pages/collection/index' });
    }
  }
});
