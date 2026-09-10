# 卡片工坊 · Birthday 数字收藏卡设计系统

把一张照片做成**可拖转的数字收藏卡网页**(HTML),带卡牌内部的层间纵深、克制的全息材质,并交付可编辑的 Blender 工程与分层素材。

> 当前工作台定位:客户提供照片 + 生日信息 → 工作台生成卡 → 打包给客户 → 客户打开网页查看。

---

## 目录结构

```
├── card-studio/                  # 卡片工坊(本地工具 + 全套生成脚本)
│   ├── server.mjs                # 本地服务: 拖图界面 / 任务队列 / 预览路由(端口 4399)
│   ├── public/index.html         # 拖放界面
│   ├── prepare.py                # 图片处理: 判断素材 → 抠图或保留整图 → 铺背景/线稿 → 写配置
│   ├── make_birthday_art.py      # 单卡(Night 风)美术生成器
│   ├── birthday_system.py        # Birthday 五套模板生成器(核心)
│   ├── build_birthday_set.py     # 一键构建多套模板(建工程 → 跑流水线 → 组装网页)
│   ├── render_previews.py        # 离线渲染效果图(与网页 shader 同公式)
│   ├── mock_overflow.py          # "特效溢出卡外"视觉 mock(实验, 未进系统)
│   ├── patch_birthday_viewer.py  # 查看器定制: 背板 / 四态 / 页面主题
│   ├── refresh_birthday.py       # 改配置或换照片后一键刷新
│   └── 启动卡片工坊.bat / 使用说明.md
├── birthday-set/                 # 五套模板成品(每套一个可独立打开的网页)
├── demo-koi/                     # 示例: 水墨锦鲤卡
├── demo-birthday/                # 示例: 深色生日卡
├── RuiC-card-skill-main/         # 生成引擎(第三方, MIT, 见其 LICENSE)
├── Birthday系列-设计方案.md        # 五套模板的视觉设计方案
└── 卡片工坊-介绍.md                # 系统完整介绍
```

## 快速开始

1. 安装依赖:**Python 3 + Pillow + numpy**、**Node.js**;Blender **不用自己装**(流水线会自动下载官方便携版并校验 SHA-256)。
2. 启动工坊:双击 `card-studio/启动卡片工坊.bat`,或 `cd card-studio && node server.mjs` → `http://127.0.0.1:4399`
3. 拖图 → 填文案 → 生成 → 在页面里预览(拖拽旋转 / 翻面 / 景深 / 光泽 / 卡面质感)。

批量出五套模板:

```bash
python card-studio/build_birthday_set.py "你的照片.jpg"
cd birthday-set && node server.mjs      # http://127.0.0.1:4185
```

渲染效果图(不依赖浏览器):

```bash
python card-studio/render_previews.py   # → birthday-set/previews/
```

## 五套 Birthday 模板

| 模板 | 定位 | 特征 |
|---|---|---|
| Celebration | 明亮开心 · **主力款** | 照片顶部出血、纸屑、大号珊瑚数字 |
| Soft | 温柔浪漫 · 杂志感 | 长渐变融入、大留白、金环小数字 |
| Pop | 年轻大胆 | 斜切色块、296px 黑体数字、蓝块排版 |
| Night | 高级安静 · **高级款** | 照片羽化入深蓝、暖金数字 |
| Diorama | 立体画框 · **备选款** | 层深 0.55/0.88、暖金笔触前景、浮雕投影、烫金 0.88 |

> 正式对外主推 **四套**(Celebration / Soft / Pop / Night);Diorama 作为可选第五款,用于需要"卡内有空间"的炫技场合。

五套共享:卡牌比例、`CARD #XXXX` 身份体系、背板信息结构(卡名/日期/祝福/CREATED BY/OWNED BY)、字体体系、边框逻辑、Holo 视角门控。

## 设计原则

- **CARD DESIGN FIRST. HOLOGRAPHIC EFFECT SECOND.** 全息是材质,不是画面主体。
- 照片优先:**默认不抠图、不改人物、不重造背景**;只做裁切/调色/暗部处理/渐变融入/局部景深。抠图仅作可选处理方式。
- 年龄:配置提供才显示,并在模板里作为核心视觉元素;未提供则完全不出现(不虚构)。
- 静止时是一张漂亮的印刷卡;倾斜才逐渐出现虹彩、边缘高光、少量 sparkle。

## 关于本仓库

- **未包含** Blender 便携版(约 1.27GB,流水线按官方 SHA-256 自动下载)、中间产物与运行期数据。
- **未包含**任何真人照片成品(客户隐私):`demo-birthday/`、`birthday-set/` 等含人脸目录默认不上传。
- 生成引擎 [`RuiC-card-skill-main`](https://github.com/HRuiCcc/RuiC-card-skill) 为第三方开源项目(**MIT License**, Copyright © 2026 HRuiCcc),本仓库按其许可保留原始 LICENSE。
