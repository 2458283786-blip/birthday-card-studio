# -*- coding: utf-8 -*-
"""V2 工作台: 加「④ 精修」面板(表面光泽 / 材质组合 / 景深) + 立即应用到 3D 预览"""
from pathlib import Path

P = Path("D:/陈大帅/ai搞一搞/虚拟产品项目/卡片card/card-studio/public/index.html")
s = P.read_text(encoding="utf8")

# ---------- 1) HTML: 插在 QA 卡片之前 ----------
qa_anchor = '''      <section class="card" id="v2_qaCard" style="display:none">'''
edit_html = '''      <section class="card" id="v2_editCard" style="display:none">
        <h2><span class="n">4</span>精修(3D 表现)</h2>
        <label>表面光泽</label>
        <div class="chips" id="v2_finish">
          <div class="chip on" data-v="pearl">珠光</div>
          <div class="chip" data-v="silver">银</div>
          <div class="chip" data-v="original">原色(哑光)</div>
          <div class="chip" data-v="gold">金</div>
        </div>
        <label style="margin-top:12px">材质组合(卡框 / 文字 / 照片 / 底)</label>
        <div class="chips" id="v2_mat">
          <div class="chip on" data-v="current">经典珠光</div>
          <div class="chip" data-v="B-gloss">哑光底+镜面</div>
          <div class="chip" data-v="B-foil">哑光底+古铜烫金</div>
          <div class="chip" data-v="A-foil">全底烫金箔</div>
          <div class="chip" data-v="matte">全哑光印刷</div>
        </div>
        <label style="margin-top:12px">景深(拖动时的层间错位)</label>
        <div class="slider"><span>主体</span><input type="range" id="v2d_sub" min="-0.2" max="0.9" step="0.02"><b id="v2v_sub"></b></div>
        <div class="slider"><span>背景</span><input type="range" id="v2d_bg" min="-0.8" max="0.2" step="0.02"><b id="v2v_bg"></b></div>
        <div class="slider"><span>前景</span><input type="range" id="v2d_fx" min="0" max="1.4" step="0.02"><b id="v2v_fx"></b></div>
        <div class="slider"><span>文字</span><input type="range" id="v2d_tx" min="0" max="1.2" step="0.02"><b id="v2v_tx"></b></div>
        <div style="display:flex;gap:8px;margin-top:12px;align-items:center;flex-wrap:wrap">
          <button class="btn" id="v2_apply" style="height:34px;padding:0 16px;font-size:13px">应用到 3D 预览</button>
          <span class="muted" id="v2_applyState"></span>
        </div>
        <div class="muted" style="margin-top:6px">光泽/材质是 3D 表现层;静态卡面以「塑封围边」呈现</div>
      </section>

''' + qa_anchor
if 'id="v2_editCard"' not in s:
    s = s.replace(qa_anchor, edit_html, 1)
    print("精修面板 HTML: OK")

# ---------- 2) JS ----------
js_anchor = '$("v2_order").onclick = v2Order;'
js_block = '''/* ---------------- V2 精修 ---------------- */
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
  for (const [id, v] of [["v2d_sub", v2f.sub], ["v2d_bg", v2f.bg], ["v2d_fx", v2f.fx], ["v2d_tx", v2f.tx]]) {
    const el = $(id);
    if (el) { el.value = v; $("v2v_" + id.slice(4)).textContent = Number(v).toFixed(2); }
  }
}
["v2d_sub", "v2d_bg", "v2d_fx", "v2d_tx"].forEach((id) => {
  const el = $(id);
  if (!el) return;
  el.oninput = () => {
    const v = parseFloat(el.value);
    if (id === "v2d_sub") v2f.sub = v; else if (id === "v2d_bg") v2f.bg = v;
    else if (id === "v2d_fx") v2f.fx = v; else v2f.tx = v;
    $("v2v_" + id.slice(4)).textContent = v.toFixed(2);
  };
});
bindChips("v2_finish", (v) => { v2f.finish = v; });
bindChips("v2_mat", (v) => { v2f.mat = v; });

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
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.ok) { $("v2_applyState").textContent = "应用失败"; toast("应用失败, 见日志", true); return; }
    $("v2_applyState").textContent = "已应用 ✓ 正在重载预览";
    const f = $("viewer");
    f.dataset.id = "";                    // 强制重载 iframe, 立刻看到新材质
    showView(v2.id, "3d");
  } catch (e) { $("v2_applyState").textContent = "应用失败: " + e; }
}
if ($("v2_apply")) $("v2_apply").onclick = v2ApplyLook;

''' + js_anchor
if "V2 精修 ----------------" not in s:
    if js_anchor in s:
        s = s.replace(js_anchor, js_block, 1)
        print("精修面板 JS: OK")
    else:
        print("JS 锚点未命中")

# ---------- 3) 采用提案后显示精修面板 ----------
old_show = '''    await renderQA();
    $("v2_qaCard").style.display = "block";'''
new_show = '''    await renderQA();
    $("v2_qaCard").style.display = "block";
    await v2ShowEdit();'''
if old_show in s:
    s = s.replace(old_show, new_show, 1)
    print("采用后显示精修: OK")

P.write_text(s, encoding="utf8")
chk = P.read_text(encoding="utf8")
for k in ["v2_editCard", "v2ApplyLook", "v2ShowEdit", "V2_MAT", "v2d_fx"]:
    print(f"  写后含 {k}:", k in chk)
