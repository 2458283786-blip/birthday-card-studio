/**
 * 卡片视图模型（数据层的地基）
 * ============================
 * 不管是本地打包的 Card Package，还是云开发返回的记录，最终都经过这里变成同一种"视图"，
 * 页面只认这个结构 —— 以后换数据来源，页面代码不用改。
 *
 * 降级规则（文档 §16）：
 *   缺少分层素材 → 只用正面成品整图；没有背面 → 不能翻面；没填的字段 → 整行不出现。
 */
const manifest = require('../data/cards/manifest.js');

/**
 * 分层的绘制顺序 = 网页版 shader 的合成顺序（这一条必须和 shader 一致，否则画面就错了）：
 *   背景 → 主体 → 光点 → 文字
 * 注意 lineart 不在里面：它在 shader 里只是给主体加高光的蒙版，不是一张可见图层。
 */
const LAYER_ORDER = ['background', 'subject', 'effects', 'text'];

// 层深度的兜底值；真实值来自 card.json 的 _studio.parameters（打包时写进 manifest）
const DEFAULT_DEPTH = { background: -0.30, subject: 0.34, effects: 0.64 };

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
    .map((name) => ({ name, src: layerMap[name] }));

  // 有背景 + 主体就能分层显示(其余层本来就是可选的)；
  // 缺这两层就退回成品整图 —— 两者画面一致，因为整图就是这些层压出来的。
  const useFlat = !(layerMap.background && layerMap.subject);

  // 只有真的填了的字段才进视图：没填的整行不出现（不留空占位）
  const notes = [];
  if (meta.fields.message) notes.push(meta.fields.message);
  if (meta.fields.signature) notes.push(meta.fields.signature);
  const owners = [];
  if (meta.fields.ownerName) owners.push({ label: 'FOR', value: meta.fields.ownerName });
  if (meta.fields.creatorName) owners.push({ label: 'CREATED BY', value: meta.fields.creatorName });

  return {
    cardId: meta.cardId,
    displayId: meta.displayId || meta.cardId,
    title: meta.title || null,
    dateText: prettyDate(meta.date),
    surface: meta.surface || 'dark',
    // 卡牌页背景：浅色卡用浅灰底，深色卡用白底（打包时按卡面取色算好 surface）
    background: (meta.surface === 'light') ? '#f2f3f5' : '#ffffff',
    hasBack: !!assets.back,
    back: assets.back || '',
    flat: assets.front || '',
    layers,
    depths: meta.depths || DEFAULT_DEPTH,
    useFlat,
    notes,
    owners
  };
}

/** 本地打包的卡 */
function toView(item) {
  return buildView({
    cardId: item.cardId,
    displayId: item.displayId,
    title: item.title,
    date: item.date,
    surface: item.surface,
    depths: item.depth,
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
    depths: card.depth,
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

module.exports = { toView, viewFromRecord, rawCard, fieldsOf, LAYER_ORDER };
