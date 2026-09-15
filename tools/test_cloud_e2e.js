/**
 * 端到端契约测试：工作台发布 → 云函数 → 小程序视图
 * ================================================
 * 这条链上有三个环节分别由三种语言/运行时负责, 字段一旦对不上, 真机上就是"卡不显示":
 *
 *   tools/publish_to_mp.py   写出的记录(publish/<CODE>/record.json)
 *        ↓ 存进云数据库
 *   云函数 claimCard/myCards  取出来返回
 *        ↓ wx.cloud.callFunction
 *   utils/cardview.js        viewFromRecord() 变成页面能用的视图
 *
 * 这个测试把三段真实代码串起来跑:
 *   - 夹具用工作台真实写出的 record.json(把本地路径换成云存储 fileID)
 *   - 云函数用真的 miniprogram/cloudfunctions/*
 *   - 小程序数据层用真的 utils/api.js + utils/cardview.js(模式切到 cloud)
 *
 * 用法: node tools/test_cloud_e2e.js
 */
const fs = require('fs');
const path = require('path');
const Module = require('module');

const ROOT = path.join(__dirname, '..');
const MP = path.join(ROOT, 'miniprogram');

/* ---------------- 内存假数据库 ---------------- */
let docs = [];
let currentOpenId = 'openid-A';

function clone(v) {
  return JSON.parse(JSON.stringify(v));
}

function matches(doc, cond) {
  return Object.keys(cond).every((k) => doc[k] === cond[k]);
}

const fakeDb = {
  collection() {
    return {
      where(cond) {
        let order = null;
        const api = {
          orderBy(field, dir) {
            order = { field, dir };
            return api;
          },
          limit(n) {
            return { get: () => api.get(n) };
          },
          get: (n) => {
            let rows = docs.filter((d) => matches(d, cond));
            if (order) {
              const sign = order.dir === 'desc' ? -1 : 1;
              rows = rows.slice().sort(
                (a, b) => sign * ((a[order.field] || 0) - (b[order.field] || 0)));
            }
            if (n) rows = rows.slice(0, n);
            return { data: clone(rows) };
          },
          update: async ({ data }) => {
            const hit = docs.filter((d) => matches(d, cond));
            hit.forEach((d) => Object.assign(d, clone(data)));
            return { stats: { updated: hit.length } };
          }
        };
        return api;
      },
      doc(id) {
        return {
          get: async () => {
            const found = docs.find((d) => d._id === id);
            if (!found) throw new Error('not found');
            return { data: clone(found) };
          }
        };
      }
    };
  }
};

const fakeCloud = {
  DYNAMIC_CURRENT_ENV: 'test-env',
  init() {},
  getWXContext: () => ({ OPENID: currentOpenId }),
  database: () => fakeDb
};

const origLoad = Module._load;
Module._load = function (request) {
  if (request === 'wx-server-sdk') return fakeCloud;
  return origLoad.apply(this, arguments);
};

const claimFn = require(path.join(MP, 'cloudfunctions', 'claimCard', 'index.js'));
const listFn = require(path.join(MP, 'cloudfunctions', 'myCards', 'index.js'));

/* ---------------- 桩: 小程序的 wx(含 wx.cloud) ---------------- */
const storage = {};
const cloudCalls = [];
global.wx = {
  getStorageSync: (k) => (k in storage ? storage[k] : ''),
  setStorageSync: (k, v) => {
    storage[k] = clone(v);
  },
  removeStorageSync: (k) => {
    delete storage[k];
  },
  cloud: {
    init() {},
    callFunction({ name, data, success, fail }) {
      cloudCalls.push(name);
      const handler = name === 'claimCard' ? claimFn : listFn;
      Promise.resolve()
        .then(() => handler.main(data || {}))
        .then((result) => success && success({ result }))
        .catch((e) => fail && fail(e));
    }
  }
};

const cfg = require(path.join(MP, 'config.js'));
const api = require(path.join(MP, 'utils', 'api.js'));
const claimcode = require(path.join(MP, 'utils', 'claimcode.js'));

let failed = 0;
let passed = 0;

function check(name, cond, extra) {
  if (cond) {
    passed++;
    console.log(`  ✅ ${name}`);
  } else {
    failed++;
    console.log(`  ❌ ${name}${extra ? '  → ' + extra : ''}`);
  }
}

/** 找一份工作台真实写出的发布记录 */
function loadFixture() {
  const publishDir = path.join(ROOT, 'publish');
  if (!fs.existsSync(publishDir)) return null;
  const files = [];
  for (const code of fs.readdirSync(publishDir)) {
    const f = path.join(publishDir, code, 'record.json');
    if (fs.existsSync(f)) files.push({ f, t: fs.statSync(f).mtimeMs });
  }
  if (!files.length) return null;
  files.sort((a, b) => b.t - a.t);
  return { record: JSON.parse(fs.readFileSync(files[0].f, 'utf8')), file: files[0].f };
}

async function run() {
  console.log('\n[0] 夹具: 工作台真实写出的发布记录');
  const fixture = loadFixture();
  if (!fixture) {
    console.log('  ❌ 找不到 publish/*/record.json');
    console.log('     先跑一次: python tools/publish_to_mp.py CARD-0001 --dry-run');
    process.exit(1);
  }
  const rec = fixture.record;
  console.log(`     来源: ${path.relative(ROOT, fixture.file)}`);
  check('记录含 code/cardId/card/assets',
    !!(rec.code && rec.cardId && rec.card && rec.assets), Object.keys(rec).join(','));
  check('记录里的 card 带渲染必需字段',
    !!(rec.card.displayId && rec.card.date && rec.card.surface),
    JSON.stringify(Object.keys(rec.card)));
  check('记录里的 assets 分 front/back/layers',
    !!rec.assets.front && 'back' in rec.assets && !!rec.assets.layers,
    JSON.stringify(Object.keys(rec.assets)));

  // 真发布时素材是云存储 fileID; 这里把本地路径换掉, 其余原样入库
  const cloudRec = clone(rec);
  const toCloud = (p) => (p ? p.replace('/data/packages/', 'cloud://test-env/card/') : p);
  cloudRec.assets.front = toCloud(cloudRec.assets.front);
  cloudRec.assets.back = toCloud(cloudRec.assets.back);
  Object.keys(cloudRec.assets.layers).forEach((k) => {
    cloudRec.assets.layers[k] = toCloud(cloudRec.assets.layers[k]);
  });
  cloudRec._id = 'doc1';
  docs.push(cloudRec);

  console.log('\n[1] 切到 cloud 模式(这时 api.js 走 wx.cloud 而不是本地存储)');
  cfg.mode = 'cloud';
  check('数据层认为自己在云模式', api.isMock() === false);

  console.log('\n[2] 小程序里输码 → 云函数认领');
  currentOpenId = 'openid-A';
  let res = await api.claimCard(claimcode.pretty(rec.code));
  check('领取成功', res.ok === true && !!res.card, JSON.stringify(res).slice(0, 160));
  check('确实调用了云函数', cloudCalls.includes('claimCard'), cloudCalls.join(','));

  const card = res.card || {};
  console.log('\n[3] 云函数返回的卡片 → 页面能用的视图');
  check('卡号 / 日期', card.displayId === rec.card.displayId && !!card.dateText,
    `${card.displayId} / ${card.dateText}`);
  check('分层齐全 → 用分层渲染(不是整图)', card.useFlat === false,
    `useFlat=${card.useFlat} layers=${(card.layers || []).length}`);
  check('分层带各自的 src', (card.layers || []).every((l) => !!l.src));
  check('有背面 → 能翻面', card.hasBack === true && !!card.back);
  check('有卡面整图兜底', !!card.flat);
  check('按卡面明暗给了背景色', !!card.background, card.background);
  check('层深度参数带过来了(视差要用)',
    !!(card.depths && typeof card.depths.subject === 'number'),
    JSON.stringify(card.depths));

  console.log('\n[4] 我的收藏(cloud 模式)');
  let cards = await api.listCards();
  check('收藏里有 1 张', cards.length === 1, `实际 ${cards.length}`);
  check('收藏项的卡片能渲染', !!cards[0] && cards[0].useFlat === false &&
    (cards[0].layers || []).length >= 2);
  check('调用了 myCards 云函数', cloudCalls.includes('myCards'));

  console.log('\n[5] 换个人 → 领不走');
  currentOpenId = 'openid-B';
  res = await api.claimCard(claimcode.pretty(rec.code));
  check('被挡下 → CLAIMED', res.ok === false && res.error === 'CLAIMED', JSON.stringify(res));
  cards = await api.listCards();
  check('B 的收藏是空的', cards.length === 0, `实际 ${cards.length}`);

  console.log('\n[6] 云函数出错时不能白屏');
  const backup = global.wx.cloud.callFunction;
  global.wx.cloud.callFunction = ({ fail }) => fail && fail(new Error('boom'));
  res = await api.claimCard(claimcode.pretty(rec.code));
  check('网络失败 → NETWORK, 页面能给出提示', res.ok === false && res.error === 'NETWORK',
    JSON.stringify(res));
  cards = await api.listCards();
  check('列表读取失败 → 空列表而不是崩', Array.isArray(cards) && cards.length === 0);
  global.wx.cloud.callFunction = backup;

  console.log(`\n结果: ${passed} 通过 / ${failed} 失败`);
  process.exit(failed ? 1 : 0);
}

run().catch((e) => {
  console.log('\n❌ 测试自身抛异常:', (e && e.stack) || e);
  process.exit(1);
});
