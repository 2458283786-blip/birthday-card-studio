# -*- coding: utf-8 -*-
from pathlib import Path

P = Path(r"D:\陈大帅\ai搞一搞\虚拟产品项目\卡片card\card-studio\public\index.html")
s = P.read_text(encoding="utf8")
anchor = '$("v2_order").onclick = v2Order;'
print("锚点:", anchor in s, "| 已有 V2_MAT:", "V2_MAT" in s)

JS = '''/* ---------------- V2 精修 ---------------- */
const V2_MAT = {
  current: { regions: { frame: "pearl", text: "matte", subject: "pearl", background: "pearl" },
             amounts: { frame: .5, text: 0, subject: .35, background: .35 } },
  "B-gloss": { regions: { frame: "gloss", text: "gloss", subject: "matte", background: "matte" },
               amounts: { frame: .92, text: .72, subject: 0, background: 0 } },
  "B-foil": { regions: { frame: "foil", text: "foil", subject: "matte", background: "matte" },
              amounts: { frame: .95, text: .70, subject: 0, background: 0 } },
  "A-foil": { regions: { frame: "foil", text: "foil", subject: "foil", background: "foil" },
              amounts: { frame: .95, text: .75, subject: .45, background: .55 } },
  matte: { regions: { frame: "matte", text: "matte", subject: "matte", background: "matte" },
           amounts: { frame: 0, text: 0, subject: 0, background: 0 } },
};
let v2f = { finish: "pearl", mat: "current", sub: .10, bg: -.22, fx: .78, tx: .46 };

function v2SliderSync() {
  const pairs = [["v2d_sub", v2f.sub], ["v2d_bg", v2f.bg], ["v2d_fx", v2f.fx], ["v2d_tx", v2f.tx]];
  pairs.forEach(function (pr) {
    const el = $(pr[0]);
    if (el) { el.value = pr[1]; $("v2v_" + pr[0].slice(4)).textContent = Number(pr[1]).toFixed(2); }
  });
}
["v2d_sub", "v2d_bg", "v2d_fx", "v2d_tx"].forEach(function (id) {
  const el = $(id);
  if (!el) return;
  el.oninput = function () {
    const v = parseFloat(el.value);
    if (id === "v2d_sub") v2f.sub = v; else if (id === "v2d_bg") v2f.bg = v;
    else if (id === "v2d_fx") v2f.fx = v; else v2f.tx = v;
    $("v2v_" + id.slice(4)).textContent = v.toFixed(2);
  };
});
bindChips("v2_finish", function (v) { v2f.finish = v; });
bindChips("v2_mat", function (v) { v2f.mat = v; });

async function v2ShowEdit() {
  $("v2_editCard").style.display = "block";
  try {
    const c = await (await fetch("/api/config/" + v2.id)).json();
    v2f.finish = (c.appearance || {}).finish || "pearl";
    v2f.mat = matGuess(c.material);
    const p = c.parameters || {};
    v2f.sub = p.subjectDepth == null ? .10 : p.subjectDepth;
    v2f.bg = p.backgroundDepth == null ? -.22 : p.backgroundDepth;
    v2f.fx = p.effectsDepth == null ? .78 : p.effectsDepth;
    v2f.tx = p.textDepth == null ? .46 : p.textDepth;
    chipPick("v2_finish", v2f.finish);
    chipPick("v2_mat", v2f.mat);
    v2SliderSync();
  } catch (e) { /* 忽略 */ }
}

async function v2ApplyLook() {
  if (!v2.id) { toast("先建立订单并采用提案", true); return; }
  $("v2_applyState").textContent = "应用中…";
  try {
    const r = await fetch("/api/config/" + v2.id, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ appearance: { finish: v2f.finish }, material: V2_MAT[v2f.mat],
        parameters: { subjectDepth: v2f.sub, backgroundDepth: v2f.bg,
                      effectsDepth: v2f.fx, textDepth: v2f.tx } }) });
    const d = await r.json().catch(function () { return {}; });
    if (!r.ok || !d.ok) { $("v2_applyState").textContent = "应用失败"; toast("应用失败, 见日志", true); return; }
    $("v2_applyState").textContent = "已应用 ✓ 正在重载预览";
    const f = $("viewer");
    if (f) f.dataset.id = "";
    showView(v2.id, "3d");
  } catch (e) { $("v2_applyState").textContent = "应用失败: " + e; }
}
if ($("v2_apply")) $("v2_apply").onclick = v2ApplyLook;

'''

if "V2_MAT" not in s and anchor in s:
    s = s.replace(anchor, JS + anchor, 1)
    old_show = '''    await renderQA();
    $("v2_qaCard").style.display = "block";'''
    if old_show in s:
        s = s.replace(old_show, old_show + "\n    await v2ShowEdit();", 1)
    P.write_text(s, encoding="utf8")
    print("已写入 JS")
else:
    print("跳过")
s2 = P.read_text(encoding="utf8")
for k in ["V2_MAT", "v2ApplyLook", "v2ShowEdit", "await v2ShowEdit()"]:
    print(f"  写后含 {k}:", k in s2)
print("行数:", s2.count("\n"))
