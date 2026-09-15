/**
 * 素材缓存测试（桩掉 wx 的文件系统与下载）
 * ========================================
 * 验证：第一次打开正常显示并在后台缓存 → 第二次直接用本地文件（秒开、离线可看）；
 *       下载失败/文件被系统清掉时不报错、不白屏，继续用云端地址。
 *
 * 用法: node tools/test_cache.js
 */
const path = require('path');

const MP = path.join(__dirname, '..', 'miniprogram');

/* ---------------- 桩: storage + 文件系统 + 下载 ---------------- */
const storage = {};
const files = new Set();          // 假装存在于手机上的文件
let downloads = [];               // 记录每一次下载
let failNext = 0;                 // >0 时接下来 N 次下载失败

global.wx = {
  env: { USER_DATA_PATH: '/usr/local/cards' },
  getStorageSync: (k) => (k in storage ? JSON.parse(JSON.stringify(storage[k])) : ''),
  setStorageSync: (k, v) => {
    storage[k] = JSON.parse(JSON.stringify(v));
  },
  removeStorageSync: (k) => {
    delete storage[k];
  },
  getFileSystemManager: () => ({
    accessSync(p) {
      if (!files.has(p)) throw new Error('no such file');
    },
    mkdirSync() {},
    copyFileSync(from, to) {
      if (!files.has(from)) throw new Error('temp missing');
      files.add(to);
    },
    unlinkSync(p) {
      files.delete(p);
    }
  }),
  cloud: {
    downloadFile({ fileID, success, fail }) {
      downloads.push({ kind: 'cloud', src: fileID });
      if (failNext > 0) {
        failNext--;
        fail(new Error('network'));
        return;
      }
      const temp = 'tmp://' + fileID;
      files.add(temp);
      setTimeout(() => success({ tempFilePath: temp }), 0);
    }
  },
  downloadFile({ url, success, fail }) {
    downloads.push({ kind: 'http', src: url });
    if (failNext > 0) {
      failNext--;
      fail(new Error('network'));
      return;
    }
    const temp = 'tmp://' + url;
    files.add(temp);
    setTimeout(() => success({ statusCode: 200, tempFilePath: temp }), 0);
  }
};

const cache = require(path.join(MP, 'utils', 'cache.js'));

let passed = 0;
let failed = 0;
function check(name, cond, extra) {
  if (cond) {
    passed++;
    console.log(`  ✅ ${name}`);
  } else {
    failed++;
    console.log(`  ❌ ${name}${extra ? '  → ' + extra : ''}`);
  }
}

function cloudCard(id) {
  return {
    cardId: id,
    displayId: id.replace('-', ' #'),
    flat: `cloud://env/card/${id}/front.webp`,
    back: `cloud://env/card/${id}/back.webp`,
    hasBack: true,
    layers: [
      { name: 'background', src: `cloud://env/card/${id}/layers/background.webp` },
      { name: 'subject', src: `cloud://env/card/${id}/layers/subject.webp` }
    ],
    useFlat: false
  };
}

function countRemote(card) {
  const all = [card.flat, card.back].concat((card.layers || []).map((l) => l.src));
  return all.filter((s) => /^cloud:\/\/|^https?:/.test(s)).length;
}

function run() {
  console.log('\n[1] 还没缓存时');
  const card = cloudCard('CARD-0001');
  check('素材全是云端地址', countRemote(card) === 4, String(countRemote(card)));
  check('localCard() 返回 null（不能假装有本地文件）', cache.localCard(card) === null);
  check('本地命中率 0', cache.localRatio(card) === 0, String(cache.localRatio(card)));

  console.log('\n[2] 后台缓存（不阻塞本次显示）');
  return cache.warmCard(card).then((warmed) => {
    check('下载了 4 个素材', downloads.length === 4, `实际 ${downloads.length}`);
    check('都走的是云存储下载接口',
      downloads.every((d) => d.kind === 'cloud'), JSON.stringify(downloads[0]));
    check('返回的卡片已经指向本地文件',
      countRemote(warmed) === 0 && /cards\/CARD-0001-front\.webp$/.test(warmed.flat),
      warmed.flat);
    check('分层也换成本地路径',
      warmed.layers.every((l) => l.src.indexOf('/usr/local/cards/cards/') === 0),
      JSON.stringify(warmed.layers.map((l) => l.src)));
    check('本地文件真的写进去了', files.has(warmed.flat) && files.has(warmed.back));

    console.log('\n[3] 第二次打开（应该秒开、不再下载）');
    const before = downloads.length;
    const local = cache.localCard(card);
    check('localCard() 直接给出本地版本', !!local && countRemote(local) === 0);
    return cache.warmCard(card).then(() => {
      check('没有再发起下载', downloads.length === before,
        `又多下了 ${downloads.length - before} 个`);
      check('本地命中率 100%', cache.localRatio(card) === 1, String(cache.localRatio(card)));

      console.log('\n[4] 本地文件被系统清掉 → 自动重新缓存');
      files.delete(local.flat);
      check('发现文件没了 → localCard() 返回 null', cache.localCard(card) === null);
      const before2 = downloads.length;
      return cache.warmCard(card).then(() => {
        check('只补下缺的那一个', downloads.length - before2 === 1,
          `实际补了 ${downloads.length - before2} 个`);
        check('补完后又能用本地', cache.localCard(card) !== null);

        console.log('\n[5] 下载失败时不能崩');
        const card2 = cloudCard('CARD-0002');
        failNext = 4;
        return cache.warmCard(card2).then((w) => {
          check('失败时不抛异常, 素材保持云端地址', countRemote(w) === 4,
            JSON.stringify([w.flat, w.back]));
          check('失败后 localCard() 仍是 null', cache.localCard(card2) === null);

          console.log('\n[6] 小程序包内的本地路径不动它');
          const pkgCard = {
            cardId: 'CARD-0003', flat: '/data/packages/CARD-0003/front.webp',
            back: '/data/packages/CARD-0003/back.webp', layers: [],
            hasBack: true
          };
          const n = downloads.length;
          return cache.warmCard(pkgCard).then((w) => {
            check('没有发起下载', downloads.length === n);
            check('路径原样保留', w.flat === pkgCard.flat && w.back === pkgCard.back);

            console.log('\n[7] https 素材走普通下载接口');
            const httpCard = {
              cardId: 'CARD-0004', flat: 'https://cdn.example.com/a.webp',
              back: '', layers: [], hasBack: false
            };
            return cache.warmCard(httpCard).then(() => {
              const last = downloads[downloads.length - 1];
              check('用的是 wx.downloadFile', last.kind === 'http', last.kind);

              console.log('\n[8] 收藏列表的离线兜底');
              const idxBefore = storage['asset_cache_v1'];
              const list = [cache.localCard(card) || card];
              cache.saveList([Object.assign({}, card, { claimedAt: 1 })]);
              check('列表已存进 storage', !!storage['cards_list_cache_v1']);
              // 断网: 用缓存的列表
              const offline = cache.cachedList();
              check('断网时能拿到列表', offline.length === 1, `实际 ${offline.length}`);
              check('断网时素材尽量用本地路径', countRemote(offline[0]) === 0,
                JSON.stringify(offline[0].flat));
              check('列表缓存里带着领取时间', offline[0].claimedAt === 1);

              console.log('\n[9] 容量上限（最久没用过的先淘汰）');
              // 塞满超过上限的假记录(文件都真实存在), 再缓存一张新卡
              const idx = {};
              const total = cache.MAX_ENTRIES + 6;
              for (let i = 0; i < total; i++) {
                const p = `/usr/local/cards/cards/OLD-${i}-front.webp`;
                files.add(p);
                idx[`cloud://env/old/${i}.webp`] = { path: p, at: 1000 + i, size: 1 };
              }
              storage['asset_cache_v1'] = idx;
              const newestOld = `/usr/local/cards/cards/OLD-${total - 1}-front.webp`;
              return cache.warmCard(cloudCard('CARD-0005')).then(() => {
                const after = storage['asset_cache_v1'];
                const n = Object.keys(after).length;
                check(`淘汰后不超过上限（${n} ≤ ${cache.MAX_ENTRIES}）`,
                  n <= cache.MAX_ENTRIES, String(n));
                check('最久没用过的被删掉了（文件也删了）',
                  !after['cloud://env/old/0.webp'] &&
                  !files.has('/usr/local/cards/cards/OLD-0-front.webp'));
                check('最近用过的还在',
                  !!after[`cloud://env/old/${total - 1}.webp`] && files.has(newestOld));
                check('新缓存的素材也在', Object.keys(after).some((k) =>
                  k.indexOf('CARD-0005') >= 0));

                console.log('\n[10] 清理');
                cache.clear();
                check('清理后索引与列表都空了',
                  !storage['asset_cache_v1'] && !storage['cards_list_cache_v1']);

                console.log(`\n结果: ${passed} 通过 / ${failed} 失败`);
                process.exit(failed ? 1 : 0);
              });
            });
          });
        });
      });
    });
  }).catch((e) => {
    console.log('\n❌ 测试自身抛异常:', (e && e.stack) || e);
    process.exit(1);
  });
}

run();
