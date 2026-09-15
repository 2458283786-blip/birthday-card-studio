/**
 * 云函数: 我的收藏
 * ================
 * 只返回"当前微信号已经领到手"的卡, 按领取时间倒序。
 * 返回: { ok:true, cards:[{ cardId, card, assets, claimedAt }] }
 */
const cloud = require('wx-server-sdk');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database();

const COLLECTION = 'cards';

exports.main = async () => {
  const wxContext = cloud.getWXContext();
  const openid = wxContext.OPENID;
  if (!openid) return { ok: false, cards: [] };

  try {
    const res = await db.collection(COLLECTION)
      .where({ ownerOpenId: openid })
      .orderBy('claimedAt', 'desc')
      .limit(100)
      .get();

    return {
      ok: true,
      cards: res.data.map((r) => ({
        cardId: r.cardId,
        card: r.card,
        assets: r.assets,
        claimedAt: r.claimedAt
      }))
    };
  } catch (e) {
    console.error('[myCards] 失败', e);
    return { ok: false, cards: [], message: String((e && e.message) || e) };
  }
};
