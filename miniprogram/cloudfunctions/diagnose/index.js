/**
 * 云函数: 环境自检（第一次配好云开发后跑一次, 就知道通不通、缺什么）
 * =================================================================
 * 怎么跑:
 *   云开发控制台 → 云函数 → diagnose → 「测试」→ 直接点运行(不用传参数)
 *   然后看返回的 checks: 哪一项 false, 就照 hint 去修。
 *
 * 它检查的正是真发布/导入会用到的那几条路:
 *   1. 云函数拿得到调用者的 openid 吗
 *   2. 数据库连得上吗
 *   3. cards 集合存在吗
 *   4. 能写进去 / 读回来 / 删掉吗（权限与索引对不对）
 *   5. 云存储能传能删吗（工作台发布素材走的就是这条路）
 *
 * 说明: 每次自检会写一条 code 以 DIAG 开头的临时记录, 并在结束时删掉。
 *       之所以要带 code, 是因为如果你的 code 字段建了唯一索引,
 *       不带 code 的记录会被当成"重复的空值"而写入失败。
 */
const cloud = require('wx-server-sdk');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

const COLLECTION = 'cards';

exports.main = async () => {
  const checks = [];
  const add = (name, ok, detail) => checks.push({ name, ok: !!ok, detail: detail || '' });

  // 1) openid
  let openid = '';
  try {
    openid = cloud.getWXContext().OPENID || '';
  } catch (e) {
    add('拿到调用者 openid', false, String(e && e.message || e));
  }
  if (!openid) {
    add('拿到调用者 openid', false,
      '从云开发控制台直接测试时本来就没有 openid, 属正常; 但要确认小程序端调得到这个函数');
  } else {
    add('拿到调用者 openid', true, openid.slice(0, 6) + '…');
  }

  // 2) 数据库连得上 + 3) 集合存在
  const col = db.collection(COLLECTION);
  let count = null;
  try {
    const res = await col.count();
    count = res.total;
    add(`集合 ${COLLECTION} 存在且可查询`, true, `现有 ${count} 条记录`);
  } catch (e) {
    const msg = String((e && e.errMsg) || (e && e.message) || e);
    add(`集合 ${COLLECTION} 存在且可查询`, false,
      msg + ' → 去「云开发控制台 → 数据库」新建一个叫 cards 的集合');
  }

  // 4) 写入 / 读回 / 删除（顺带验证唯一索引不会挡住正常写入）
  let diagId = null;
  const code = 'DIAG' + Date.now();
  try {
    const added = await col.add({
      data: {
        code,
        cardId: 'DIAG',
        status: 'diagnose',
        ownerOpenId: '',
        claimedAt: null,
        createdAt: Date.now()
      }
    });
    diagId = added._id;
    add('能往集合里写记录', true, '临时记录已写入');
  } catch (e) {
    add('能往集合里写记录', false,
      String((e && e.errMsg) || (e && e.message) || e)
      + ' → 检查集合权限, 以及 code 字段的唯一索引是否正常');
  }

  if (diagId) {
    try {
      const got = await col.doc(diagId).get();
      add('能把刚写的读回来', got && got.data && got.data.code === code);
    } catch (e) {
      add('能把刚写的读回来', false, String((e && e.errMsg) || (e && e.message) || e));
    }
    try {
      await col.doc(diagId).remove();
      add('能删掉临时记录', true, '自检没留下垃圾数据');
    } catch (e) {
      add('能删掉临时记录', false,
        String((e && e.errMsg) || (e && e.message) || e) + ' → 记得手动删掉 code 以 DIAG 开头的记录');
    }
  }

  // 5) 云存储（发布素材走这条路）
  const cloudPath = `diagnose/${code}.txt`;
  try {
    const up = await cloud.uploadFile({
      cloudPath,
      fileContent: Buffer.from('cardstudio diagnose', 'utf8')
    });
    add('云存储能上传文件', true, up.fileID || '');
    try {
      await cloud.deleteFile({ fileList: [up.fileID] });
      add('云存储能删除文件', true);
    } catch (e) {
      add('云存储能删除文件', false, String((e && e.errMsg) || (e && e.message) || e));
    }
  } catch (e) {
    add('云存储能上传文件', false,
      String((e && e.errMsg) || (e && e.message) || e)
      + ' → 云开发控制台里确认「存储」已开通');
  }

  const failed = checks.filter((c) => !c.ok);
  return {
    ok: failed.length === 0,
    openid: openid ? '(已获取)' : '(无, 控制台测试时正常)',
    checks,
    hint: failed.length
      ? '还有 ' + failed.length + ' 项没过, 按上面的 detail 逐条修'
      : '云环境没问题, 可以去工作台跑: python tools/publish_to_mp.py CARD-0001'
  };
};
