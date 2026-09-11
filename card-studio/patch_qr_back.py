# -*- coding: utf-8 -*-
"""
把二维码绘制注入网页背板(backTexture)
=====================================
只读 config.qr.matrix(由 qr_util.py 生成), 不引入任何 JS 二维码库。
幂等标记: config.qr
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

QR_JS = """  // 二维码(§11 有就展示): 只按 config.qr.matrix 绘制, 无外部依赖
  const qrCfg = config.qr || (config.qrUrl ? { enabled: true, url: config.qrUrl } : null);
  if (qrCfg && qrCfg.enabled && Array.isArray(qrCfg.matrix) && qrCfg.matrix.length) {
    const qn = qrCfg.matrix.length;
    const qbox = 132, qpad = 12;
    const qx = 1024 - 92 - qbox, qy = 1536 - 92 - qbox;
    ctx.save();
    ctx.fillStyle = dark ? "rgba(250,247,240,.94)" : "rgba(255,253,249,.96)";
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(qx - qpad, qy - qpad, qbox + qpad * 2, qbox + qpad * 2, 12);
    else ctx.rect(qx - qpad, qy - qpad, qbox + qpad * 2, qbox + qpad * 2);
    ctx.fill();
    const qcell = qbox / qn;
    ctx.fillStyle = dark ? "#0d111c" : "#241f19";
    for (let r = 0; r < qn; r++) {
      const rowStr = String(qrCfg.matrix[r]);
      for (let c = 0; c < qn; c++) {
        if (rowStr.charAt(c) === "1") {
          ctx.fillRect(qx + c * qcell, qy + r * qcell, Math.ceil(qcell), Math.ceil(qcell));
        }
      }
    }
    ctx.restore();
    tracked("SCAN", 1024 - 92 - qbox / 2, qy + qbox + qpad + 24, "12px 'Segoe UI', Arial", 3,
            "rgba(" + (dark ? "222,201,160,.72" : "58,52,44,.58") + ")");
  }
  return canvasTexture(c);
}"""

ANCHOR = "  return canvasTexture(c);\n}"


def patch(p):
    s = p.read_text(encoding="utf8")
    if "const qrCfg = config.qr" in s:
        return "已存在"
    if s.count(ANCHOR) != 1:
        return f"锚点 {s.count(ANCHOR)} 处"
    p.write_text(s.replace(ANCHOR, QR_JS, 1), encoding="utf8")
    return "OK"


def web_dirs():
    out = [ROOT / "RuiC-card-skill-main" / "assets" / "web-template"]
    for d in ("demo-koi", "demo-birthday"):
        w = ROOT / d / "web"
        if w.is_dir():
            out.append(w)
    for sub in (ROOT / "birthday-set").glob("*"):
        if (sub / "app.js").exists():
            out.append(sub)
    for d in ("birthday-build", "card-studio/projects"):
        for sub in (ROOT / d).glob("*"):
            if (sub / "web").is_dir():
                out.append(sub / "web")
    return out


def main():
    for w in web_dirs():
        f = w / "app.js"
        if f.exists():
            print(f"{w.relative_to(ROOT)}  {patch(f)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
