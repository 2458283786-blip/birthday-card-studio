# -*- coding: utf-8 -*-
import sys
from pathlib import Path

P = Path(r"D:\陈大帅\ai搞一搞\虚拟产品项目\卡片card\card-studio\public\index.html")
print("存在:", P.exists(), "| 大小:", P.stat().st_size if P.exists() else 0)
s = P.read_text(encoding="utf8")
qa = '      <section class="card" id="v2_qaCard" style="display:none">'
js = '$("v2_order").onclick = v2Order;'
print("QA 锚点:", qa in s, "| JS 锚点:", js in s, "| 已有 editCard:", 'id="v2_editCard"' in s)

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

'''

if 'id="v2_editCard"' not in s and qa in s:
    s = s.replace(qa, edit_html + qa, 1)
    P.write_text(s, encoding="utf8")
    print("已写入 HTML")
else:
    print("跳过 HTML 插入")

s2 = P.read_text(encoding="utf8")
print("写入后 editCard:", 'id="v2_editCard"' in s2, "| v2_apply:", 'id="v2_apply"' in s2, "| 行数:", s2.count("\n"))
