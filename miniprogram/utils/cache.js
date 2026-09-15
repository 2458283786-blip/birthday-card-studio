/**
 * 卡片素材的本地缓存
 * ==================
 * 为什么需要：云开发模式下每次打开卡片都会把图片重新拉一遍 —— 慢，而且没网就什么都看不见。
 *
 * 做法（不改变页面代码，全部收在数据层里）：
 *   1. 第一次照常显示（直接用云端地址，不等下载）
 *   2. 同时在后台把素材存到手机本地
 *   3. 以后打开：先看本地有没有全套素材 → 有就直接用（秒开、离线也能看）
 *
 * 索引存在 storage：{ [素材地址]: { path, at, size } }
 * 文件放在：wx.env.USER_DATA_PATH/cards/<卡号>-<槽位>.<后缀>
 *
 * 降级原则：任何一步失败都只是"没缓存成功"，绝不报错、绝不白屏 —— 继续用云端地址。
 */
const KEY = 'asset_cache_v1';
const MAX_ENTRIES = 420;          // 约 70 张卡的素材(一张卡 6 个), 每张 ~150KB

function env() {
  try {
    return (wx.env && wx.env.USER_DATA_PATH) || '';
  } catch (e) {
    return '';
  }
}

function fs() {
  try {
    return wx.getFileSystemManager();
  } catch (e) {
    return null;
  }
}

function loadIndex() {
  try {
    const idx = wx.getStorageSync(KEY);
    return (idx && typeof idx === 'object') ? idx : {};
  } catch (e) {
    return {};
  }
}

function saveIndex(idx) {
  try {
    wx.setStorageSync(KEY, idx);
  } catch (e) {
    // 存不下就算了, 下次重新缓存
  }
}

function isRemote(src) {
  return /^(cloud:\/\/|https?:\/\/)/.test(String(src || ''));
}

function extOf(src) {
  const m = String(src || '').match(/\.([A-Za-z0-9]+)(?:\?|$)/);
  return m ? m[1].toLowerCase() : 'bin';
}

function exists(path) {
  const f = fs();
  if (!f || !path) return false;
  try {
    f.accessSync(path);
    return true;
  } catch (e) {
    return false;
  }
}

function removeFile(path) {
  const f = fs();
  if (!f || !path) return;
  try {
    f.unlinkSync(path);
  } catch (e) {
    // 文件可能已经不在了
  }
}

/** 一条素材记录 → 本地路径（没缓存或文件没了都返回 ''） */
function localPathFor(idx, key) {
  const rec = idx[key];
  if (!rec || !rec.path) return '';
  if (!exists(rec.path)) {
    delete idx[key];                 // 文件被系统清掉了, 当成没缓存
    return '';
  }
  rec.at = Date.now();               // 命中就刷新 LRU 时间
  return rec.path;
}

/** 把卡片里的远端地址换成本地路径; all=true 时要求每一张都在本地 */
function mapCard(card, resolve, requireAll) {
  let missing = false;
  const wrap = (src, slot) => {
    if (!isRemote(src)) return src;               // 小程序包内的路径本来就是本地的
    const local = resolve(src, slot);
    if (local) return local;
    missing = true;
    return src;
  };
  const out = Object.assign({}, card);
  out.flat = wrap(card.flat, 'front');
  out.back = card.back ? wrap(card.back, 'back') : card.back;
  out.layers = (card.layers || []).map((l) =>
    Object.assign({}, l, { src: wrap(l.src, 'layer-' + l.name) }));
  if (requireAll && missing) return null;
  return out;
}

/** 同步：这套素材是不是全在本地了。是 → 返回换成本地路径的卡片；否 → null */
function localCard(card) {
  if (!card) return null;
  const idx = loadIndex();
  const out = mapCard(card, (src) => localPathFor(idx, src), true);
  saveIndex(idx);                     // 可能刷新了 LRU 时间 / 清理了失效项
  return out;
}

/** 同步：这套素材在本地有几成（只用于显示/调试，不参与渲染决策） */
function localRatio(card) {
  if (!card) return 0;
  const all = [];
  if (card.flat) all.push(card.flat);
  if (card.back) all.push(card.back);
  (card.layers || []).forEach((l) => all.push(l.src));
  const remote = all.filter(isRemote);
  if (!remote.length) return 1;
  const idx = loadIndex();
  const hit = remote.filter((src) => !!localPathFor(idx, src)).length;
  return hit / remote.length;
}

function downloadOne(src, dest) {
  return new Promise((resolve) => {
    const finish = (tempPath) => {
      const f = fs();
      if (!f || !tempPath) {
        resolve('');
        return;
      }
      try {
        const dir = dest.slice(0, dest.lastIndexOf('/'));
        try {
          f.mkdirSync(dir, true);
        } catch (e) {
          // 目录已存在
        }
        f.copyFileSync(tempPath, dest);
        resolve(exists(dest) ? dest : '');
      } catch (e) {
        resolve('');
      }
    };
    try {
      if (String(src).indexOf('cloud://') === 0 && wx.cloud && wx.cloud.downloadFile) {
        wx.cloud.downloadFile({
          fileID: src,
          success: (r) => finish(r && r.tempFilePath),
          fail: () => resolve('')
        });
      } else {
        wx.downloadFile({
          url: src,
          success: (r) => finish(r && r.statusCode === 200 ? r.tempFilePath : ''),
          fail: () => resolve('')
        });
      }
    } catch (e) {
      resolve('');
    }
  });
}

function trimIndex(idx) {
  const keys = Object.keys(idx);
  if (keys.length <= MAX_ENTRIES) return;
  keys.sort((a, b) => (idx[a].at || 0) - (idx[b].at || 0));   // 最久没用过的在前面
  const drop = keys.slice(0, keys.length - MAX_ENTRIES);
  drop.forEach((k) => {
    removeFile(idx[k].path);
    delete idx[k];
  });
}

/**
 * 把一张卡的素材存到本地。返回换成本地路径的卡片（没下成功的仍是云端地址）。
 * 页面可以直接忽略返回值 —— 它的作用是"下次打开就快了"。
 */
function warmCard(card) {
  if (!card || !env()) return Promise.resolve(card);
  const idx = loadIndex();
  const jobs = [];
  const slotPath = (cardId, slot, src) =>
    `${env()}/cards/${cardId}-${slot}.${extOf(src)}`;

  const plan = (src, slot) => {
    if (!isRemote(src)) return;
    if (localPathFor(idx, src)) return;            // 已经在本地
    const dest = slotPath(card.cardId, slot, src);
    jobs.push(downloadOne(src, dest).then((path) => {
      if (path) idx[src] = { path, at: Date.now(), size: 0 };
    }));
  };

  plan(card.flat, 'front');
  if (card.back) plan(card.back, 'back');
  (card.layers || []).forEach((l) => plan(l.src, 'layer-' + l.name));

  if (!jobs.length) return Promise.resolve(mapCard(card, (src) => localPathFor(idx, src), false));

  return Promise.all(jobs).then(() => {
    trimIndex(idx);
    saveIndex(idx);
    return mapCard(card, (src) => localPathFor(idx, src), false);
  });
}

/* ---------------- 收藏列表的离线兜底 ---------------- */

const LIST_KEY = 'cards_list_cache_v1';

function saveList(views) {
  try {
    // 只存渲染要用的字段, 避免 storage 无谓变大
    const slim = (views || []).map((v) => ({
      cardId: v.cardId, displayId: v.displayId, dateText: v.dateText,
      surface: v.surface, background: v.background, hasBack: v.hasBack,
      back: v.back, flat: v.flat, layers: v.layers, depths: v.depths,
      useFlat: v.useFlat, finish: v.finish, foil: v.foil, holoOn: v.holoOn,
      notes: v.notes, owners: v.owners, claimedAt: v.claimedAt || 0
    }));
    wx.setStorageSync(LIST_KEY, slim);
  } catch (e) {
    // 忽略
  }
}

/** 断网时的收藏列表（素材尽量换成本地路径，这样离线也能看） */
function cachedList() {
  try {
    const rows = wx.getStorageSync(LIST_KEY);
    if (!Array.isArray(rows)) return [];
    const idx = loadIndex();
    const out = rows.map((r) => mapCard(r, (src) => localPathFor(idx, src), false));
    saveIndex(idx);
    return out;
  } catch (e) {
    return [];
  }
}

function clear() {
  const idx = loadIndex();
  Object.keys(idx).forEach((k) => removeFile(idx[k].path));
  try {
    wx.removeStorageSync(KEY);
    wx.removeStorageSync(LIST_KEY);
  } catch (e) {
    // 忽略
  }
}

module.exports = {
  localCard,
  localRatio,
  warmCard,
  saveList,
  cachedList,
  clear,
  MAX_ENTRIES
};
