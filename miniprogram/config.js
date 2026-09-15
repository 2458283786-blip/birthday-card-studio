/**
 * 运行配置（只有这里需要改）
 * ==========================
 * mode:
 *   'mock'  —— 本地演示模式: 不连云开发, 用手机本地存储模拟"登记处"。
 *              可以完整走一遍「输码 → 领取 → 再输一次提示已被领取」,
 *              但**防不住转发**(换台手机就是新的"登记处")。只用于本地预览。
 *   'cloud' —— 正式模式: 用微信云开发做登记处, 一个码只能被一个微信号领走。
 *              需要正式 AppID(测试号用不了云开发) + cloudEnv 填云环境 ID。
 */
module.exports = {
  mode: 'mock',

  // 开通云开发后, 在「云开发控制台 → 设置 → 环境 ID」里复制过来, 形如 'cloud1-9gxxxxxx'
  cloudEnv: '',

  // 云函数名(和 cloudfunctions/ 里的目录名一致)
  claimFunction: 'claimCard',
  listFunction: 'myCards'
};
