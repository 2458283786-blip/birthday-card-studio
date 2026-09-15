/**
 * 小程序数据层的可执行测试（用 Node 桩掉 wx）
 * ============================================
 * 为什么要有它: 开发者工具我这边跑不起来(命令行启动会超时),
 * 而"导入码 → 认领 → 我的收藏"这套逻辑全在 JS 里, 可以脱开界面直接测。
 * 这里跑的是小程序**真实的那几个文件**, 不是复制品。
 *
 * 用法: node tools/test_mp_datalayer.js
 */
const path = require('path');

const MP = path.join(__dirname, '..', 'miniprogram');

/* ---------- 桩: 只实现数据层用到的 wx 能力 ---------- */
const storage = {};
global.wx = {
  getStorageSync: (k) => (k in storage ? storage[k] : ''),
  setStorageSync: (k, v) => {
    storage[k] = JSON.parse(JSON.stringify(v));
  },
  removeStorageSync: (k) => {
    delete storage[k];
  }
};

const api = require(path.join(MP, 'utils', 'api.js'));
const claimcode = require(path.join(MP, 'utils', 'claimcode.js'));
const manifest = require(path.join(MP, 'data', 'cards', 'manifest.js'));

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

function sameIdentity() {
  // 模拟"还是同一个人": 不清 storage
}

function otherIdentity() {
  // 模拟"换了一个微信号": 只换身份, 保留登记处(码仍被占用)
  storage['claim_mock_me_v1'] = 'local-someone-else';
}

function resetAll() {
  Object.keys(storage).forEach((k) => delete storage[k]);
}

function run() {
  const codes = Object.keys(require(path.join(MP, 'data', 'cards', 'mockcodes.js')));
  const anyCode = codes[0];

  console.log('\n[1] 空收藏');
  return api.listCards().then((cards) => {
    check('没导入过时收藏为空', cards.length === 0, `实际 ${cards.length} 张`);

    console.log('\n[2] 输错码(校验位拦下, 不联网)');
    return api.claimCard('AAAA-AAAA');
  }).then((res) => {
    check('格式不对 → BAD_CODE', res.ok === false && res.error === 'BAD_CODE', JSON.stringify(res));

    console.log('\n[3] 合法但不存在的码');
    // 造一个校验位合法的码: 取真码前 7 位改最后一位让它仍合法
    let nowhere = null;
    for (let i = 0; i < 200 && !nowhere; i++) {
      const c = claimcode.formatInput(
        'ZZZZ' + Math.random().toString(36).slice(2, 6).toUpperCase());
      if (claimcode.isValid(c) && !codes.includes(claimcode.normalize(c))) nowhere = c;
    }
    return api.claimCard(nowhere || 'ZZZZ-ZZZZ');
  }).then((res) => {
    check('查不到 → NOT_FOUND', res.ok === false && res.error === 'NOT_FOUND', JSON.stringify(res));

    console.log('\n[4] 正常导入');
    return api.claimCard(claimcode.pretty(anyCode));
  }).then((res) => {
    check('导入成功', res.ok === true && !!res.card, JSON.stringify(res).slice(0, 120));
    const card = res.card || {};
    check('拿到的卡片在包里存在', !!manifest.cards.find((c) => c.cardId === card.cardId));
    check('卡片带卡号/日期', !!card.displayId && !!card.dateText, JSON.stringify({
      id: card.displayId, date: card.dateText
    }));
    check('分层齐全时用分层渲染', card.useFlat === false || card.layers.length >= 2,
      `useFlat=${card.useFlat} layers=${card.layers.length}`);
    check('有背面 → 可以翻面', card.hasBack === true);
    check('背景按卡面明暗决定', !!card.background, card.background);

    console.log('\n[5] 同一个人再输一次(不算第二次导入)');
    return api.claimCard(claimcode.pretty(anyCode));
  }).then((res) => {
    check('本人重进 → 直接进入, 不报"已被领取"',
      res.ok === true && !!res.card, JSON.stringify(res).slice(0, 120));

    console.log('\n[6] 收藏列表');
    return api.listCards();
  }).then((cards) => {
    check('收藏里出现刚才那张卡', cards.length === 1 && !!cards[0].displayId,
      `实际 ${cards.length} 张`);
    check('收藏项带领取时间', !!cards[0] && !!cards[0].claimedAt);

    console.log('\n[7] 换一个微信号输同一个码');
    otherIdentity();
    return api.claimCard(claimcode.pretty(anyCode));
  }).then((res) => {
    check('别人来领 → CLAIMED(先到先得)', res.ok === false && res.error === 'CLAIMED',
      JSON.stringify(res));
    check('并且带上"什么时候被领的"', !!res.claimedAt);

    console.log('\n[8] 换人后的收藏');
    return api.listCards();
  }).then((cards) => {
    check('别人的收藏里没有这张卡', cards.length === 0, `实际 ${cards.length} 张`);

    console.log('\n[9] 重置演示登记处');
    sameIdentity();
    resetAll();
    return api.listCards();
  }).then((cards) => {
    check('重置后收藏回到空', cards.length === 0);

    console.log(`\n结果: ${passed} 通过 / ${failed} 失败`);
    process.exit(failed ? 1 : 0);
  }).catch((err) => {
    console.log('\n❌ 测试自身抛异常:', err && err.stack || err);
    process.exit(1);
  });
}

run();
