/**
 * 卡片视图模型（数据层唯一出口）
 * ================================
 * 现在从打包好的本地 Card Package 读（data/cards/manifest.js）。
 * 以后接后台时：把 Promise.resolve(...) 换成 wx.request(...) 即可，页面代码不用动。
 *
 * 这里同时负责文档 §16 的降级规则：
 *   没有分层素材 → 只用正面整图；没有背面 → 不能翻面；没有的字段 → 直接不出现。
 */
const manifest = require('../data/cards/manifest.js');

// 分层的前后顺序与深度（rpx）。数字只影响纵深感，不进入数据。
const DEPTH = { background: -96, effects: -50, subject: -16, lineart: 48, text: 56 };
const LAYER_ORDER = ['background', 'effects', 'subject', 'lineart', 'text'];

function prettyDate(iso) {
  return (iso || '').replace(/-/g, '.');
}

function toView(item) {
  const layers = LAYER_ORDER
    .filter((name) => item.layers && item.layers[name])
    .map((name) => ({ name, src: item.layers[name], z: DEPTH[name] }));

  const f = item.fields || {};
  // 只把「真的填了」的字段放进视图：没填的整行不出现（不留空占位）
  const notes = [];
  if (f.message) notes.push(f.message);
  if (f.signature) notes.push(f.signature);
  const owners = [];
  if (f.ownerName) owners.push({ label: 'FOR', value: f.ownerName });
  if (f.creatorName) owners.push({ label: 'CREATED BY', value: f.creatorName });

  return {
    cardId: item.cardId,
    displayId: item.displayId,
    dateText: prettyDate(item.date),
    surface: item.surface || 'dark',
    // 卡牌页背景：浅色卡用浅灰底，深色卡用白底（按卡面取色自动决定）
    background: (item.surface === 'light') ? '#f2f3f5' : '#ffffff',
    hasBack: !!item.hasBack,
    back: item.back || '',
    layers,
    useFlat: layers.length === 0,
    flat: item.front,
    notes,
    owners
  };
}

/** 收藏馆列表。结构对齐未来 API：{ cards: [...] } */
function listCards() {
  return Promise.resolve(manifest.cards.map(toView));
}

/** 单张卡。找不到时 resolve(null)，由页面显示空态而不是报错。 */
function getCard(cardId) {
  const hit = manifest.cards.find((c) => c.cardId === cardId);
  return Promise.resolve(hit ? toView(hit) : null);
}

module.exports = { listCards, getCard };
