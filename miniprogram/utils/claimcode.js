/**
 * 导入码(短码)的规范与校验 —— 必须与 tools/claim_code.py 完全一致
 * ==============================================================
 * 8 位: 7 位随机 + 1 位校验位; 字符表去掉 0 O 1 I; 展示成 XXXX-XXXX。
 * 校验位在本地就能发现"输错一位", 不用先联网再报错。
 */
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

function isValid(input) {
  const s = normalize(input);
  if (s.length !== CODE_LEN) return false;
  for (let i = 0; i < s.length; i++) {
    if (ALPHABET.indexOf(s.charAt(i)) < 0) return false;
  }
  return checkChar(s.slice(0, BODY_LEN)) === s.charAt(BODY_LEN);
}

/** 输入框里边打字边格式化: 自动大写 + 第 4 位后补横线, 只留合法字符 */
function formatInput(input) {
  const s = normalize(input).slice(0, CODE_LEN);
  return s.length > 4 ? `${s.slice(0, 4)}-${s.slice(4)}` : s;
}

function pretty(input) {
  const s = normalize(input);
  return s.length === CODE_LEN ? `${s.slice(0, 4)}-${s.slice(4)}` : s;
}

module.exports = { normalize, isValid, formatInput, pretty, CODE_LEN };
