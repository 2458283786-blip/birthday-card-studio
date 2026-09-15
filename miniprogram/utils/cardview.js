/**
 * 卡片视图模型（数据层的地基）
 * ============================
 * 不管是本地打包的 Card Package，还是云开发返回的记录，最终都经过这里变成同一种"视图"，
 * 页面只认这个结构 —— 以后换数据来源，页面代码不用改。
 *
 * 同时负责降级规则（文档 §16）：
 *   没有分层素材 → 只用正面整图；没有背面 → 不能翻面；没填的字段 → 整行不出现。
 */
const manifest = require('../data/cards/manifest.js');

// 分层的前后顺序与深度（rpx）。留到第二版 WebGL 渲染时使用。
const DEPTH = { background: -96, effects: -50, subject: -16, lineart: 48, text: 56 };
const LAYER_ORDER = ['background', 'effects', 'subject', 'lineart', 'text'];

/**
 * 第一版：卡面直接用成品整图（front.webp / back.webp），保证与工作台生成的卡 100% 一致。
 * 为什么不用分层：透视会把每一层缩放（后层缩小、前层放大），拼回去就和成品图不一样；
 * 层间纵深是 shader 的活，交给第二版 WebGL（与网页版同一套公式）。
 * 改成 true 必须和第二版渲染器一起开。
 */
const DEPTH_READY = false;

function prettyDate(iso) {
  return (iso || '').replace(/-/g, '.');
}

/** 从 card.json 里挑出"真的填了"的字段 —— 工作台打包与云端返回共用同一套规则 */
function fieldsOf(card) {
  const c = card || {};
  const content = c.content || {};
  const owner = c.owner || {};
  const creator = c.creator || {};
  const qr = c.qr || {};
  return {
    message: content.message || '',
    signature: content.signature || '',
    ownerName: owner.name || '',
    creatorName: creator.name || '',
    qr: !!qr.enabled
  };
}

function buildView(meta, assets) {
  const layerMap = assets.layers || {};
  const layers = LAYER_ORDER
    .filter((name) => layerMap[name])
    .map((name) => ({ name, src: layerMap[name], z: DEPTH[name] }));

  // 只有真的填了的字段才进视图：没填的整行不出现（不留空占位）
  const notes = [];
  if (meta.fields.message) notes.push(meta.fields.message);
  if (meta.fields.signature) notes.push(meta.fields.signature);
  const owners = [];
  if (meta.fields.ownerName) owners.push({ label: 'FOR', value: meta.fields.ownerName });
  if (meta.fields.creatorName) owners.push({ label: 'CREATED BY', value: meta.fields.creatorName });

  const hasBack = !!assets.back;

  return {
    cardId: meta.cardId,
    displayId: meta.displayId || meta.cardId,
    title: meta.title || null,
    dateText: prettyDate(meta.date),
    surface: meta.surface || 'dark',
    // 卡牌页背景：浅色卡用浅灰底，深色卡用白底（打包时按卡面取色算好 surface）
    background: (meta.surface === 'light') ? '#f2f3f5' : '#ffffff',
    hasBack,
    back: assets.back || '',
    flat: assets.front || '',
    layers,
    useFlat: !DEPTH_READY || layers.length === 0,
    notes,
    owners
  };
}

/** 本地打包的卡（收藏页/卡牌页的数据来源之一） */
function toView(item) {
  return buildView({
    cardId: item.cardId,
    displayId: item.displayId,
    title: item.title,
    date: item.date,
    surface: item.surface,
    fields: item.fields || fieldsOf(item)
  }, {
    front: item.front,
    back: item.hasBack ? item.back : null,
    layers: item.layers || {}
  });
}

/** 云开发返回的一条记录 → 视图。assets 里是云存储 fileID，image 组件可直接显示 */
function viewFromRecord(record) {
  const r = record || {};
  const card = r.card || {};
  const assets = r.assets || {};
  return buildView({
    cardId: card.cardId || r.cardId,
    displayId: card.displayId || card.cardId || r.cardId,
    title: card.title,
    date: card.date,
    surface: card.surface || 'dark',
    fields: card.fields || fieldsOf(card)
  }, {
    front: assets.front,
    back: assets.back || null,
    layers: assets.layers || {}
  });
}

function rawCard(cardId) {
  return manifest.cards.find((c) => c.cardId === cardId) || null;
}

module.exports = { toView, viewFromRecord, rawCard, fieldsOf, DEPTH_READY };
