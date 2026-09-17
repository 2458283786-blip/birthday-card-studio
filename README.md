# 数字收藏卡 · 生产工作台

把一张照片做成一件**属于客户的数字收藏品** —— 输出可拖转的 3D 卡网页、静态正背面、分层素材与可交付的 **Card Package**。

> **当前状态:正在按 V2 方案重构。**
> - 产品规范(唯一有效):[`docs/V2-主规范.md`](docs/V2-主规范.md)
> - 进度日志(每次改动追加):[`docs/V2-进度日志.md`](docs/V2-进度日志.md)
> - 旧 Birthday 方向文档已归档:[`archive/v1-birthday/`](archive/v1-birthday/)

---

## 这是什么
**数字收藏卡生产工作台**。使用者是**制卡人员**(不是客户);客户只提供照片与文案。

```
客户照片 + 文案 + 纪念信息
   → AI 分析(Photo Analyzer / PhotoDNA)
   → AI 设计提案(3~4 个)
   → 制卡人员选择
   → 程序化生成(确定性排版 + Card Identity + 分层/材质)
   → 人工精修 → QA → 导出 Card Package
   → Standalone Showcase(客户) / 微信小程序(收藏端)
```

**边界**:AI 负责**设计判断**,程序负责**确定性执行**;**Holo 是材质,不是 Artwork**;正面是自由 Artwork,背面是统一 Card Identity。

## 目录结构
```
card-studio/          工作台(UI + 服务 + 渲染管线)
  public/             工作台界面
  server.mjs          本地服务(生成 / 改文案 / 取色 / 导出)
  birthday_system.py  五层素材生成器(v1 兼容层, 逐步被 design-engine 取代)
  render_previews.py  离线静态成图(与网页同一套材质数学)
  dl2/                PhotoDNA / AI 客户端 / 设计语言原型
  projects/           每张卡的工作目录(素材 + 配置 + 静态图)
miniprogram/          微信小程序(交付后的收藏端, 读 Card Package)
tools/                卡包打包、小程序素材生成、全量自检
RuiC-card-skill-main/ 底层 3D / Blender / Three.js 能力(MIT)
docs/                 V2 主规范 + 进度日志
archive/v1-birthday/  旧 Birthday 方向文档与早期残留(只读参考)
```

## 怎么跑起来
```powershell
cd card-studio
node server.mjs            # 打开 http://127.0.0.1:4399
```
可选(启用 AI 判断能力,**key 只在环境变量里,不写入任何文件**):
```powershell
$env:DEEPSEEK_API_KEY="你的key"
node server.mjs
```
全量自检:
```powershell
python tools/check_all.py
```

## Card Package(交付物)
```
CARD-0027/
  card.json          卡牌数据(identity / content / material / interaction / qr)
  front.png back.png 静态正背面(关掉 Holo 也成立 —— 这是验收标准)
  preview/*.jpg      缩略图
  layers/ materials/ 按实际存在的资源输出
  showcase/          客户交付页(无工具栏 / 无调试信息)
  video/front.mp4    仅预留
```
缺失资源一律 **fallback**(缺分层→用 front.png;缺 Holo→普通材质;缺 3D→2D),optional 资源**自然隐藏**。

## 设计原则(不可违反)
1. 卡面首先成立为 **Artwork**,不是"照片 + 卡框 + 彩虹 Holo"
2. **不强制抠图**;复杂背景不得被低质量抠图破坏;始终保留原图
3. 不强制所有卡出现固定正面字段;**不为填字段破坏构图**
4. **Card ID 系统自动生成**,禁止手工填写
5. 四套设计语言**一眼可区分,但同属一个品牌系统**
6. 每个阶段报告:改了什么 / 为什么 / 怎么运行 / 测试结果 / 已知问题

## 许可
底层 3D/全息能力来自 [RuiC-card-skill](RuiC-card-skill-main/)(MIT);其余为本项目实现。
