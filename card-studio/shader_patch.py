# -*- coding: utf-8 -*-
"""
查看器 shader 调优补丁(层间纵深 + 克制全息)
============================================
1) 视差强度 .10 -> .20: 各层按 depth 成比例位移, 空间纵深更明显
2) 全息改为"视角门控": 静止时只有 15% 光泽, 转动后才逐渐亮起
3) 压低全息存在感: 条纹压暗量 .21->.11, 提亮量 (.065+.11)->(.028+.06),
   边缘高光 .42/.3 -> .22/.16, sparkle 阈值 .994->.9975 且强度 .13->.08,
   线稿辉光 .055->.035

同时改写 app.js(源码) 与 app.bundle.js(页面实际加载的打包版),
两者字符串完全一致, 因此无需 bun/esbuild 重新打包。
"""
import shutil
from pathlib import Path

TPL = Path("RuiC-card-skill-main/assets/web-template")
BACKUP = Path("card-studio/_shader_backup")

REPL = [
    ("* depth * .10;", "* depth * .20;"),
    ("float amount = strength();",
     "float tilt = clamp((length(uView.xy) - 0.12) * 3.2, 0.0, 1.0);\n"
     "  float amount = strength() * mix(0.15, 1.0, tilt);"),
    (".21 * (1.-foil)", ".11 * (1.-foil)"),
    ("(.065 + .11*(1.-luminance))", "(.028 + .06*(1.-luminance))"),
    ("edge*amount*(uFinish > 2.5 ? .42 : .3)", "edge*amount*(uFinish > 2.5 ? .22 : .16)"),
    ("step(.994,hash(cell))", "step(.9975,hash(cell))"),
    ("foil*flake*amount*.13", "foil*flake*amount*.08"),
    ("band*amount*.055", "band*amount*.035"),
]


def main():
    BACKUP.mkdir(parents=True, exist_ok=True)
    for name in ("app.js", "app.bundle.js"):
        src = TPL / name
        bak = BACKUP / name
        if not bak.exists():
            shutil.copy2(src, bak)
        s = src.read_text(encoding="utf8")
        for old, new in REPL:
            if new in s and old not in s:
                continue  # 已打过
            n = s.count(old)
            if n != 1:
                print(f"  !! {name}: 片段出现 {n} 次, 跳过: {old[:40]}")
                continue
            s = s.replace(old, new)
        src.write_text(s, encoding="utf8")
        print("patched", name)


if __name__ == "__main__":
    main()
