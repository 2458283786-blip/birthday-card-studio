/**
 * 云函数测试：一个码不会被两个人领走
 * ==================================
 * 把 wx-server-sdk 换成内存假库, 然后跑**真实的云函数代码**
 * (miniprogram/cloudfunctions/claimCard 与 myCards)。
 *
 * 重点验证两件在真机上才可能发生的事:
 *   1. 别人已经领了 → CLAIMED, 并且带上领取时间
 *   2. 两个人"同时"来领(都读到了"还没人领"的旧快照)
 *      → 只有一个写成功, 另一个必须被挡下, 不能出现两个 owner
 *
 * 说明: 这里假设云数据库的 where().update() 是"条件更新"(只有匹配到的才更新,
 *       返回 stats.updated)—— 微信云开发就是这个语义, 也是这个方案能成立的前提。
 *
 * 用法: node tools/test_cloud_claim.js
 */
const path = require('path');
const Module = require('module');

/* ---------------- 内存假数据库 ---------------- */
let docs = [];
let nextId = 1;
let currentOpenId = 'openid-A';
let staleSnapshot = null;      // 用来模拟"别人读到了旧数据"

function clone(v) {
  return JSON.parse(JSON.stringify(v));
}

function matches(doc, cond) {
  return Object.keys(cond).every((k) => doc[k] === cond[k]);
}

const fakeDb = {
  collection() {
    return {
      // diagnose 用: 集合存在性检查
      count: async () => {
        if (fakeDb.__noCollection) {
          const e = new Error('collection not exists');
          e.errMsg = 'database collection not exists';
          throw e;
        }
        return { total: docs.length };
      },
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
            // 需要时返回一份"过期的"快照, 用来制造并发读
            const source = staleSnapshot || docs;
            staleSnapshot = null;
            let rows = source.filter((d) => matches(d, cond));
            if (order) {
              const sign = order.dir === 'desc' ? -1 : 1;
              rows = rows.slice().sort(
                (a, b) => sign * ((a[order.field] || 0) - (b[order.field] || 0)));
            }
            if (n) rows = rows.slice(0, n);
            return { data: clone(rows) };
          },
          update: async ({ data }) => {
            // 条件更新: 只有仍然匹配的文档才会被写
            const hit = docs.filter((d) => matches(d, cond));
            hit.forEach((d) => Object.assign(d, clone(data)));
            return { stats: { updated: hit.length } };
          }
        };
        return api;
      },
      // diagnose 用: 写 / 读 / 删
      add: async ({ data }) => {
        const doc = clone(data);
        doc._id = 'doc' + nextId++;
        docs.push(doc);
        return { _id: doc._id };
      },
      doc(id) {
        return {
          get: async () => {
            const found = docs.find((d) => d._id === id);
            if (!found) throw new Error('document not found');
            return { data: clone(found) };
          },
          remove: async () => {
            const i = docs.findIndex((d) => d._id === id);
            if (i < 0) throw new Error('document not found');
            docs.splice(i, 1);
            return { stats: { removed: 1 } };
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
  database: () => fakeDb,
  // diagnose 用
  uploadFile: async ({ cloudPath }) => {
    if (fakeCloud.__noStorage) {
      const e = new Error('storage not enabled');
      e.errMsg = 'storage not enabled';
      throw e;
    }
    uploaded.push(cloudPath);
    return { fileID: 'cloud://test-env/' + cloudPath };
  },
  deleteFile: async ({ fileList }) => {
    deleted.push(fileList[0]);
    return { fileList: fileList.map((f) => ({ fileID: f, status: 0 })) };
  }
};
const uploaded = [];
const deleted = [];

const origLoad = Module._load;
Module._load = function (request) {
  if (request === 'wx-server-sdk') return fakeCloud;
  return origLoad.apply(this, arguments);
};

const claim = require(path.join(__dirname, '..', 'miniprogram', 'cloudfunctions',
                                 'claimCard', 'index.js'));
const myCards = require(path.join(__dirname, '..', 'miniprogram', 'cloudfunctions',
                                   'myCards', 'index.js'));

/* 与 tools/claim_code.py 相同的算法(测试里自造码用), 顺带验证两边一致 */
const ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
function checkChar(body) {
  let acc = 0;
  for (let i = 0; i < body.length; i++) {
    acc = (acc + ALPHABET.indexOf(body[i]) * (i + 1)) % ALPHABET.length;
  }
  return ALPHABET[acc];
}
function makeCode() {
  let body = '';
  for (let i = 0; i < 7; i++) {
    body += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
  }
  return body + checkChar(body);
}

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

function seed(code, cardId) {
  docs.push({
    _id: 'doc' + nextId++,
    code,
    cardId,
    status: 'unclaimed',
    ownerOpenId: '',
    claimedAt: null,
    createdAt: Date.now(),
    card: { cardId, displayId: cardId.replace('-', ' #'), date: '2026-09-09',
            surface: 'dark', content: {}, owner: {}, creator: {}, qr: {} },
    assets: { front: 'cloud://x/front.webp', back: 'cloud://x/back.webp',
              layers: { background: 'cloud://x/bg.webp', subject: 'cloud://x/s.webp' } }
  });
}

async function run() {
  const codeA = makeCode();
  const codeB = makeCode();
  seed(codeA, 'CARD-0001');
  seed(codeB, 'CARD-0002');

  console.log('\n[0] Python 生成的码, Node 这边也认(两边算法一致)');
  const mockCodes = require(path.join(__dirname, '..', 'miniprogram', 'data',
                                        'cards', 'mockcodes.js'));
  const pyCode = Object.keys(mockCodes)[0];
  check('Python 码的校验位能对上', checkChar(pyCode.slice(0, 7)) === pyCode[7], pyCode);

  console.log('\n[1] 没人领过 → 领取成功');
  currentOpenId = 'openid-A';
  let res = await claim.main({ code: codeA });
  check('返回 ok + 卡片', res.ok === true && !!res.card, JSON.stringify(res).slice(0, 140));
  check('卡片数据带分层与背面', !!(res.assets && res.assets.layers && res.assets.back));
  check('记录里写上了 ownerOpenId', docs[0].ownerOpenId === 'openid-A');
  check('记录里写上了 claimedAt', !!docs[0].claimedAt);

  console.log('\n[2] 同一个人再来一次（本人不算重复导入）');
  res = await claim.main({ code: codeA });
  check('仍然 ok, 且标记 alreadyMine', res.ok === true && res.alreadyMine === true,
    JSON.stringify(res).slice(0, 140));

  console.log('\n[3] 换个人来领同一个码');
  currentOpenId = 'openid-B';
  res = await claim.main({ code: codeA });
  check('被挡下 → CLAIMED', res.ok === false && res.error === 'CLAIMED', JSON.stringify(res));
  check('带上了领取时间', !!res.claimedAt);
  check('owner 没有被改写', docs[0].ownerOpenId === 'openid-A');

  console.log('\n[4] 两个人"同时"来领（都读到"还没人领"的旧快照）');
  currentOpenId = 'openid-C';
  const stale = clone(docs.filter((d) => d.code === codeB));   // C 读到的旧数据
  staleSnapshot = stale;                                      // 下一次 where().get() 返回它
  res = await claim.main({ code: codeB });
  check('C 正常领到（第一次写入成功）', res.ok === true, JSON.stringify(res).slice(0, 140));
  check('codeB 的 owner 是 C', docs[1].ownerOpenId === 'openid-C');
  // 现在 D 拿着"同样读到还没人领"的旧快照冲进来
  currentOpenId = 'openid-D';
  staleSnapshot = clone(stale);
  res = await claim.main({ code: codeB });
  check('D 被拦下 → CLAIMED（没有出现两个 owner）',
    res.ok === false && res.error === 'CLAIMED', JSON.stringify(res));
  check('owner 仍然只有 C 一个', docs[1].ownerOpenId === 'openid-C');

  console.log('\n[5] 乱七八糟的码');
  res = await claim.main({ code: 'AAAA-AAAA' });
  check('校验位不对 → BAD_CODE', res.ok === false && res.error === 'BAD_CODE');
  res = await claim.main({ code: makeCode() });
  check('合法但库里没有 → NOT_FOUND', res.ok === false && res.error === 'NOT_FOUND');
  res = await claim.main({ code: codeA.toLowerCase().split('').join('-') });
  check('小写带横线也认', res.ok === true || res.error === 'CLAIMED', JSON.stringify(res));

  console.log('\n[6] 我的收藏（按 openid 隔离）');
  currentOpenId = 'openid-A';
  let list = await myCards.main();
  check('A 看到 1 张', list.cards.length === 1, `实际 ${list.cards.length}`);
  check('A 看到的是自己那张', list.cards[0] && list.cards[0].cardId === 'CARD-0001');
  currentOpenId = 'openid-C';
  list = await myCards.main();
  check('C 也只看到自己那张', list.cards.length === 1 && list.cards[0].cardId === 'CARD-0002');
  currentOpenId = 'openid-nobody';
  list = await myCards.main();
  check('没领过的人看到空', list.cards.length === 0, `实际 ${list.cards.length}`);

  console.log('\n[7] 环境自检云函数（第一次配云环境时靠它定位问题）');
  const diagnose = require(path.join(__dirname, '..', 'miniprogram', 'cloudfunctions',
                                     'diagnose', 'index.js'));
  currentOpenId = 'openid-A';
  const before = docs.length;
  let report = await diagnose.main();
  check('全部检查项通过', report.ok === true,
    JSON.stringify(report.checks.filter((c) => !c.ok)));
  check('检查项覆盖数据库/读写/云存储',
    report.checks.length >= 6 && report.checks.some((c) => /云存储/.test(c.name)),
    report.checks.map((c) => c.name).join(' | '));
  check('自检不留垃圾数据（临时记录已删）',
    docs.length === before && !docs.some((d) => d.cardId === 'DIAG'),
    `记录数 ${docs.length} vs ${before}`);
  check('云存储的临时文件也删了', uploaded.length === 1 && deleted.length === 1,
    `上传 ${uploaded.length} 删除 ${deleted.length}`);
  check('提示语告诉下一步做什么', /publish_to_mp/.test(report.hint), report.hint);

  console.log('\n[8] 集合不存在时要指得出来');
  fakeDb.__noCollection = true;
  report = await diagnose.main();
  fakeDb.__noCollection = false;
  check('整体不通过', report.ok === false);
  const colCheck = report.checks.find((c) => /集合/.test(c.name));
  check('明确指出集合有问题', !!colCheck && colCheck.ok === false);
  check('并且告诉他去新建集合', /新建/.test(colCheck.detail), colCheck.detail);
  check('提示语给出待修项数量', /1 项没过/.test(report.hint) || /没过/.test(report.hint),
    report.hint);

  console.log('\n[9] 云存储没开通时也要说清楚');
  fakeCloud.__noStorage = true;
  const before2 = docs.length;
  report = await diagnose.main();
  fakeCloud.__noStorage = false;
  const storeCheck = report.checks.find((c) => /云存储能上传/.test(c.name));
  check('云存储那项是失败的', !!storeCheck && storeCheck.ok === false);
  check('提示他去开通存储', /存储/.test(storeCheck.detail), storeCheck.detail);
  check('数据库那部分仍然正常（不会因为一个错全崩）',
    report.checks.filter((c) => /集合|写记录|读回来/.test(c.name)).every((c) => c.ok),
    JSON.stringify(report.checks.map((c) => [c.name, c.ok])));
  check('即使云存储失败, 临时记录也没留下', docs.length === before2);

  console.log(`\n结果: ${passed} 通过 / ${failed} 失败`);
  process.exit(failed ? 1 : 0);
}

run().catch((e) => {
  console.log('\n❌ 测试自身抛异常:', (e && e.stack) || e);
  process.exit(1);
});
