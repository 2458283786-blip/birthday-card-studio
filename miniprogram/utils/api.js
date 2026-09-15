/**
 * 数据层唯一出口：导入码 / 我的收藏
 * =================================
 * 两种后端，一行开关（config.js 的 mode）：
 *   mock  —— 本地存储模拟"登记处"，不连云开发也能走完整流程（防不住转发，只用于本地预览）
 *   cloud —— 微信云开发：云函数 claimCard / myCards，一个码只能被一个微信号领走
 *
 * 页面只调 claimCard / listCards，不关心后端是谁。
 */
const cfg = require('../config.js');
const code = require('./claimcode.js');
const cache = require('./cache.js');
const { toView, viewFromRecord, rawCard } = require('./cardview.js');
const mockCodes = require('../data/cards/mockcodes.js');

const DB_KEY = 'claim_mock_db_v1';
const ME_KEY = 'claim_mock_me_v1';

function isMock() {
  return cfg.mode !== 'cloud';
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* ---------------- mock: 本地"登记处" ---------------- */

function mockDb() {
  try {
    return wx.getStorageSync(DB_KEY) || { claims: {} };
  } catch (e) {
    return { claims: {} };
  }
}

function mockSave(db) {
  try {
    wx.setStorageSync(DB_KEY, db);
  } catch (e) {
    // 存储失败就当作没记下来，下次重新领
  }
}

/** 本地模拟"这个微信号"：正式环境里由云函数从 OPENID 拿到，永远拿不到也改不了 */
function mockMe() {
  let me = '';
  try {
    me = wx.getStorageSync(ME_KEY) || '';
  } catch (e) {
    me = '';
  }
  if (!me) {
    me = 'local-' + Math.random().toString(36).slice(2, 10);
    try {
      wx.setStorageSync(ME_KEY, me);
    } catch (e) {
      // 忽略
    }
  }
  return me;
}

function mockClaim(clean) {
  return sleep(240).then(() => {
    const cardId = mockCodes[clean];
    if (!cardId) return { ok: false, error: 'NOT_FOUND' };
    const db = mockDb();
    const me = mockMe();
    const rec = db.claims[clean];
    if (rec && rec.owner !== me) {
      return { ok: false, error: 'CLAIMED', claimedAt: rec.at };
    }
    db.claims[clean] = { cardId, owner: me, at: Date.now() };
    mockSave(db);
    const raw = rawCard(cardId);
    return raw ? { ok: true, card: toView(raw) } : { ok: false, error: 'NOT_FOUND' };
  });
}

/* ---------------- 对外接口 ---------------- */

/**
 * 导入一张卡。返回：
 *   { ok: true,  card }
 *   { ok: false, error: 'BAD_CODE' | 'NOT_FOUND' | 'CLAIMED' | 'NETWORK' | 'FAILED', claimedAt? }
 */
function claimCard(input) {
  const clean = code.normalize(input);
  if (!code.isValid(clean)) {
    return Promise.resolve({ ok: false, error: 'BAD_CODE' });
  }
  if (isMock()) return mockClaim(clean);

  return new Promise((resolve) => {
    wx.cloud.callFunction({
      name: cfg.claimFunction,
      data: { code: clean },
      success: (res) => {
        const r = (res && res.result) || { ok: false, error: 'FAILED' };
        // 云函数返回的是数据库里的记录; 这里和 mock 模式一样转成"视图",
        // 保证两种后端的返回结构完全一致(否则页面换个字段就踩空)
        if (r.ok && r.card) {
          resolve({
            ok: true,
            alreadyMine: !!r.alreadyMine,
            card: viewFromRecord({ card: r.card, assets: r.assets })
          });
          return;
        }
        resolve(r);
      },
      fail: () => resolve({ ok: false, error: 'NETWORK' })
    });
  });
}

/** 演示模式下的收藏：从本地登记处取 */
function listMockCards() {
  return sleep(120).then(() => {
    const db = mockDb();
    const me = mockMe();
    const out = [];
    Object.keys(db.claims).forEach((clean) => {
      const rec = db.claims[clean];
      if (rec.owner !== me) return;
      const raw = rawCard(rec.cardId);
      if (!raw) return;
      const view = toView(raw);
      view.claimCode = code.pretty(clean);
      view.claimedAt = rec.at;
      out.push(view);
    });
    out.sort((a, b) => (b.claimedAt || 0) - (a.claimedAt || 0));
    return preferLocal(out);            // 演示模式素材本来就在包里, 这里是个空操作
  });
}

/**
 * 能全程用本地素材的卡就直接用本地路径（秒开、离线可看），
 * 其余的保持云端地址并顺手把素材缓存下来 —— 下次打开就快了。
 */
function preferLocal(views) {
  return views.map((view) => {
    const local = cache.localCard(view);
    if (local) return local;
    cache.warmCard(view);               // 不 await: 不拖慢这次显示
    return view;
  });
}

/**
 * 我的收藏。返回值除了卡片，还带一个"这次是怎么拿到的"：
 *   state.offline = false            → 云端正常
 *   state.offline = true, cached     → 用了本地的上次列表（断网也能看）
 *   state.offline = true, !cached    → 云端失败且没有缓存（页面要给出重试，别装作"没有卡"）
 * 页面按 state 显示不同的话；getCard 只关心卡片。
 */
function listCardsWithState() {
  if (isMock()) {
    return listMockCards().then((cards) => ({
      cards,
      state: { offline: false, cached: false, reason: 'ok' }
    }));
  }

  return new Promise((resolve) => {
    wx.cloud.callFunction({
      name: cfg.listFunction,
      success: (res) => {
        const r = (res && res.result) || {};
        if (r.ok === false) {
          // 云函数自己报错（比如集合还没建）—— 和断网一样走兜底, 但原因记下来
          resolve(fallbackList(r.message ? 'CLOUD_ERROR' : 'FAILED'));
          return;
        }
        const views = (r.cards || []).map(viewFromRecord);
        cache.saveList(views);          // 存一份, 断网时用
        resolve({
          cards: preferLocal(views),
          state: { offline: false, cached: false, reason: 'ok' }
        });
      },
      // 断网/云函数调用失败: 用上一次的列表(素材尽量用本地缓存), 页面不会空
      fail: () => resolve(fallbackList('NETWORK'))
    });
  });
}

function fallbackList(reason) {
  const cached = cache.cachedList();
  return {
    cards: cached,
    state: {
      offline: true,
      cached: cached.length > 0,
      reason: cached.length > 0 ? 'CACHED' : reason
    }
  };
}

/** 兼容旧签名: 只要卡片数组 */
function listCards() {
  return listCardsWithState().then((r) => r.cards);
}

/** 单张卡：从"我的收藏"里找。找不到 resolve(null)，页面显示空态而不是报错 */
function getCard(cardId) {
  return listCardsWithState().then((r) => ({
    card: r.cards.find((c) => c.cardId === cardId) || null,
    state: r.state
  }));
}

/** 本地演示模式下可用的示例码（页面上给个提示，正式模式返回空） */
function demoCodes() {
  return isMock() ? Object.keys(mockCodes).map(code.pretty) : [];
}

/** 清空本地登记处，方便反复演示（仅 mock 模式有意义） */
function resetMock() {
  try {
    wx.removeStorageSync(DB_KEY);
  } catch (e) {
    // 忽略
  }
}

module.exports = {
  claimCard,
  listCards,
  listCardsWithState,
  getCard,
  demoCodes,
  resetMock,
  isMock
};
