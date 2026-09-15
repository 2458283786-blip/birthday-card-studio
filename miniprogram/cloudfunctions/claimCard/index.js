/**
 * 云函数: 导入码认领（先到先得）
 * ==============================
 * 一个导入码只能被一个微信号领走:
 *   1. 码不存在        → NOT_FOUND
 *   2. 已被别人领走     → CLAIMED（带上领取时间）
 *   3. 本来就是本人     → 直接返回卡片（不算第二次导入）
 *   4. 还没人领         → 用一个"带条件的更新"写进去; 两个人同时来, 只有一个能成功
 *
 * 返回: { ok:true, card, assets } 或 { ok:false, error }
 */
const cloud = require('wx-server-sdk');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

const COLLECTION = 'cards';
const ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
const BODY_LEN = 7;
const CODE_LEN = BODY_LEN + 1;

function normalize(input) {
  return String(input || '').toUpperCase().replace(/[^0-9A-Z]/g, '');
}

function checkChar(body) {
  let acc = 0;
  for (let i = 0; i < body.length; i++) {
    const idx = ALPHABET.indexOf(body.charAt(i));
    if (idx < 0) return '';
    acc = (acc + idx * (i + 1)) % ALPHABET.length;
  }
  return ALPHABET.charAt(acc);
}

function isValid(s) {
  if (s.length !== CODE_LEN) return false;
  for (let i = 0; i < s.length; i++) {
    if (ALPHABET.indexOf(s.charAt(i)) < 0) return false;
  }
  return checkChar(s.slice(0, BODY_LEN)) === s.charAt(BODY_LEN);
}

exports.main = async (event) => {
  const wxContext = cloud.getWXContext();
  const openid = wxContext.OPENID;
  const code = normalize(event && event.code);

  if (!openid) return { ok: false, error: 'NO_OPENID' };
  if (!isValid(code)) return { ok: false, error: 'BAD_CODE' };

  try {
    const col = db.collection(COLLECTION);
    const found = await col.where({ code }).limit(1).get();
    if (!found.data.length) return { ok: false, error: 'NOT_FOUND' };

    const rec = found.data[0];
    if (rec.ownerOpenId) {
      if (rec.ownerOpenId === openid) {
        return { ok: true, card: rec.card, assets: rec.assets, alreadyMine: true };
      }
      return { ok: false, error: 'CLAIMED', claimedAt: rec.claimedAt || null };
    }

    // 先到先得: 条件里带上"还是没人领", 两个人同时来只有一个写成功
    const res = await col
      .where({ _id: rec._id, ownerOpenId: '' })
      .update({
        data: {
          ownerOpenId: openid,
          claimedAt: Date.now(),
          status: 'claimed'
        }
      });

    if (!res.stats || !res.stats.updated) {
      const again = await col.doc(rec._id).get().catch(() => null);
      const at = again && again.data ? again.data.claimedAt : null;
      return { ok: false, error: 'CLAIMED', claimedAt: at };
    }

    return { ok: true, card: rec.card, assets: rec.assets };
  } catch (e) {
    console.error('[claimCard] 失败', e);
    return { ok: false, error: 'FAILED', message: String((e && e.message) || e) };
  }
};
