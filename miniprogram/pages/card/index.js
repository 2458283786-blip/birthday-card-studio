const { getCard } = require('../../utils/api.js');

function parseRect(s) {
  if (!s) return null;
  const p = String(s).split(',').map(Number);
  if (p.length !== 4 || p.some((n) => !isFinite(n))) return null;
  return { x: p[0], y: p[1], w: p[2], h: p[3] };
}

const BAR_H = 44;   // 自绘顶栏高度(px), 与 app.wxss 的 .bar-in 一致
const HINT_RESERVE = 72;   // 底部"拖动旋转·点击翻面"提示 + 呼吸空间(px)
const META_H = 44;         // 卡牌下方只剩一行"卡号 · 日期"的高度(px)

Page({
  data: {
    statusBar: 20,
    bg: '#ffffff',
    card: null,
    missing: false,
    failed: false,
    ready: false,
    enterStyle: '',
    hintOff: false,
    padX: 24,
    padT: 8
  },

  onLoad(query) {
    const app = getApp();
    const statusBar = (app && app.globalData.statusBarHeight) || 20;
    const cardW = (app && app.globalData.cardWidthPx) || 292;
    const width = (app && app.globalData.windowWidth) || (cardW + 48);
    const winH = (app && app.globalData.windowHeight) || 812;
    const cardH = cardW * 1.5;
    const padX = Math.max(16, Math.round((width - cardW) / 2));
    // 垂直位置按屏幕高度算, 让"卡 + 下方字段"这一整块在可视区域里居中
    // (之前固定 8px 顶边距, 卡就偏上了)
    const avail = winH - (statusBar + BAR_H) - HINT_RESERVE;
    const padT = Math.max(8, Math.round((avail - cardH - META_H) / 2));

    // 从收藏页缩略图的位置和大小开始 → 再放大铺满屏幕(见 index.wxss 的 .enter)
    const from = parseRect(query && query.from);
    let enterStyle = '';
    if (from && from.w > 4) {
      const scale = from.w / cardW;
      const dx = (from.x + from.w / 2) - width / 2;
      const dy = (from.y + from.h / 2) - (statusBar + BAR_H + padT + cardH / 2);
      enterStyle = `transform: translate3d(${dx.toFixed(1)}px, ${dy.toFixed(1)}px, 0) scale(${scale.toFixed(4)});`;
    }
    this.setData({ statusBar, enterStyle, padX, padT });

    const cardId = (query && query.id) || '';
    // 没带卡号(比如在开发者工具里直接编译到这一页) → 回收藏页, 别停在空页面
    if (!cardId) {
      wx.reLaunch({ url: '/pages/collection/index' });
      return;
    }

    getCard(cardId).then((card) => {
      if (!card) {
        this.setData({ missing: true });
        return;
      }
      this.setData({ card, bg: card.background });
      this.enterTimer = setTimeout(() => {
        this.setData({ ready: true, enterStyle: '' });
      }, 60);
      // 首次进入的提示: 几秒后自己淡出
      this.hintTimer = setTimeout(() => this.setData({ hintOff: true }), 4200);
    }).catch((err) => {
      // 数据层出错时不要再装作"卡不存在", 直接显示错误并打日志 —— 否则会被误判成内容为空
      console.error('[card] 读取卡片失败', err);
      this.setData({ card: null, missing: false, failed: true });
    });
  },

  onUnload() {
    if (this.enterTimer) clearTimeout(this.enterTimer);
    if (this.hintTimer) clearTimeout(this.hintTimer);
  },

  goBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack();
    } else {
      wx.reLaunch({ url: '/pages/collection/index' });
    }
  },

  /* 保存: 把卡片正面画到画布上再存进相册(小程序包内的图片不能直接存) */
  onSave() {
    const card = this.data.card;
    if (!card) return;
    wx.showLoading({ title: '正在保存', mask: true });
    wx.createSelectorQuery().select('#export').fields({ node: true, size: true }).exec((res) => {
      const canvas = res && res[0] && res[0].node;
      if (!canvas) {
        wx.hideLoading();
        wx.showToast({ title: '保存失败', icon: 'none' });
        return;
      }
      const W = 1080;
      const H = 1620;
      canvas.width = W;
      canvas.height = H;
      const ctx = canvas.getContext('2d');
      const img = canvas.createImage();
      img.onload = () => {
        ctx.fillStyle = '#080c16';
        ctx.fillRect(0, 0, W, H);
        ctx.drawImage(img, 0, 0, W, H);
        wx.canvasToTempFilePath({
          canvas,
          fileType: 'jpg',
          quality: 0.95,
          success: (r) => this.saveToAlbum(r.tempFilePath),
          fail: () => {
            wx.hideLoading();
            wx.showToast({ title: '保存失败', icon: 'none' });
          }
        });
      };
      img.onerror = () => {
        wx.hideLoading();
        wx.showToast({ title: '图片读取失败', icon: 'none' });
      };
      img.src = card.flat;
    });
  },

  saveToAlbum(filePath) {
    wx.saveImageToPhotosAlbum({
      filePath,
      success: () => {
        wx.hideLoading();
        wx.showToast({ title: '已存到相册' });
      },
      fail: (err) => {
        wx.hideLoading();
        const msg = (err && err.errMsg) || '';
        if (/auth|deny|denied/i.test(msg)) {
          wx.showModal({
            title: '需要相册权限',
            content: '请在设置里允许「保存到相册」后再试一次',
            confirmText: '去设置',
            success: (r) => {
              if (r.confirm) wx.openSetting({});
            }
          });
        } else {
          wx.showToast({ title: '保存失败', icon: 'none' });
        }
      }
    });
  },

  onShareAppMessage() {
    const c = this.data.card;
    return {
      title: c ? `${c.displayId} · 数字收藏卡` : '数字收藏卡',
      path: c ? `/pages/card/index?id=${c.cardId}` : '/pages/collection/index'
    };
  }
});
