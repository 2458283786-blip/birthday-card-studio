// 卡片工坊 · 本地服务 (零依赖, node >= 18)
// 双击"启动卡片工坊.bat"即可; 浏览器打开 http://127.0.0.1:4399
import http from "node:http";
import { spawn } from "node:child_process";
import { readFile, writeFile, mkdir, readdir, stat, rm } from "node:fs/promises";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dir = path.dirname(fileURLToPath(import.meta.url));
const ROOT = __dir;
const PROJECTS = path.join(ROOT, "projects");
const PUBLIC = path.join(ROOT, "public");
const EXPORTS = path.join(ROOT, "..", "exports");
const SKILL = path.join(ROOT, "..", "RuiC-card-skill-main", "scripts");
const PORT = Number(process.env.PORT || 4399);

// 找共享的便携 Blender (demo 安装的那份)
function findBlender() {
  const cands = [
    path.join(ROOT, "..", "demo-koi", "tools"),
    path.join(ROOT, "..", "tools"),
  ];
  for (const base of cands) {
    try {
      for (const s of readdirSync(base)) {
        const exe = path.join(base, s, "blender.exe");
        if (s.startsWith("blender") && existsSync(exe)) return exe;
      }
    } catch {}
  }
  return null;
}
const BLENDER = findBlender();

const jobs = new Map(); // id -> job
let queue = [];

function mime(p) {
  const t = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".glb": "model/gltf-binary", ".svg": "image/svg+xml",
    ".mp4": "video/mp4", ".ico": "image/x-icon",
  };
  return t[path.extname(p).toLowerCase()] || "application/octet-stream";
}

async function serveStatic(req, res, base, rel) {
  const safe = path.normalize(rel).replace(/^([.][.][/\\])+/, "");
  let fp = path.join(base, safe);
  try {
    const st = await stat(fp);
    if (st.isDirectory()) fp = path.join(fp, "index.html");
    const data = await readFile(fp);
    res.writeHead(200, { "Content-Type": mime(fp), "Cache-Control": "no-cache" });
    res.end(data);
  } catch {
    res.writeHead(404); res.end("Not found");
  }
}

// ---------- 任务执行 ----------
// 受限环境不允许子进程 stdout 管道, 因此:
//  - python 进程继承控制台输出(stdio inherit)
//  - prepare.py 会把日志自写一份到项目 job.log, 这里轮询该文件喂给 UI
function runPy(args, cwd, logPath, onLine) {
  return new Promise((resolve) => {
    const child = spawn(args[0], args.slice(1), {
      cwd,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1",
             CARD_JOB_LOG: logPath || "" },
      stdio: "inherit",
      windowsHide: true,
    });
    let pending = "";
    let prevLen = 0;
    const sync = (final) => {
      if (!logPath) return;
      try {
        const b = readFileSync(logPath);
        const text = b.toString("utf8");
        if (text.length > prevLen) {
          const fresh = text.slice(prevLen);
          prevLen = text.length;
          const parts = (pending + fresh).split("\n");
          pending = parts.pop() || "";
          for (const raw of parts) {
            const l = raw.replace(/\r$/, "");
            if (l) onLine(l);
          }
        }
        if (final && pending) onLine(pending.replace(/\r$/, ""));
      } catch {}
    };
    const iv = setInterval(() => sync(false), 350);
    child.on("close", (code) => {
      clearInterval(iv);
      sync(true);
      resolve(code ?? 1);
    });
    child.on("error", (e) => {
      clearInterval(iv);
      sync(true);
      onLine("[工坊] 无法启动子进程: " + e.message);
      resolve(1);
    });
  });
}

async function processJob(job) {
  job.status = "running";
  const logPath = path.join(job.dir, "job.log");
  try { await rm(logPath, { force: true }); } catch {}
  const push = (l) => job.lines.push(l);
  job.lines.push("[工坊] 开始生成… Blender: " + (BLENDER ? "已就绪" : "未找到!"));
  if (!BLENDER) {
    job.status = "error";
    job.lines.push("错误: 找不到便携 Blender。请先跑通 demo-koi(它自带 tools/blender)。");
    return;
  }
  const metaPath = path.join(job.dir, "meta.json");
  await writeFile(metaPath, JSON.stringify(job.meta, null, 2), "utf8");
  const py = process.env.PY || "python";

  if (job.template === "night") {
    // ---- Birthday / Night 高级款: 静态优先的设计(自带纸张质感/排版/背面规则) ----
    const cfg = {
      subtitle: job.meta.subtitle || "HAPPY BIRTHDAY",
      title: job.meta.title || "",
      tagline: "",
      technique: job.meta.technique || "",
      edition: job.meta.edition || "",
      wish: job.meta.wish || "",
      age: job.meta.age || "",
      name: job.meta.name || "",
      collection: job.meta.collection || "",
      description: job.meta.description || "",
      createdBy: "", ownedBy: "",
      _provenance: { template: "night", style: job.style, mode: job.mode },
      backStyle: "night",
      appearance: { finish: "pearl", background: "#080c16" },
      material: {
        holoEnabled: true,
        regions: { frame: "pearl", text: "matte", subject: "pearl", background: "pearl" },
        amounts: { frame: 0.5, subject: 0.35, background: 0.35 },
      },
      parameters: { subjectScale: 1.0, subjectDepth: 0.34, backgroundDepth: -0.30,
                    effectsDepth: 0.62, effectsScale: 1.05, foil: 0.52, textDepth: 0.55 },
      safeArea: { scale: 1.0, offset: [0.0, 0.0] },
    };
    await writeFile(path.join(job.dir, "card-config.json"),
                    JSON.stringify(cfg, null, 2), "utf8");
    let code = await runPy(
      [py, "-u", path.join(__dir, "birthday_system.py"), job.image, job.dir, "night"],
      ROOT, logPath, push);
    if (code !== 0) {
      job.status = "error";
      job.lines.push("[工坊] Night 高级款素材生成失败(见上方提示)。");
      return;
    }
    job.lines.push("[工坊] 素材就绪, 生成静态卡面(正片/背面/展示图)…");
    await runPy([py, "-u", path.join(__dir, "make_static_card.py"), job.dir],
                ROOT, logPath, push);
    job.lines.push("[工坊] 静态卡面完成, 继续组装网页卡(约 1 分钟)…");
    code = await runPy(
      [py, "-u", path.join(SKILL, "run_pipeline.py"),
       "--project", job.dir, "--blender", BLENDER, "--skip-npm", "--skip-render"],
      ROOT, null, push);
    const glbN = path.join(job.dir, "web", "assets", "card.glb");
    if (code === 0 && existsSync(glbN)) {
      job.status = "done";
      job.lines.push("[工坊] ✅ 完成! 静态卡面: /cardimg/" + job.id + "/static-preview.png");
      job.lines.push("[工坊] 网页预览: /p/" + job.id + "/");
    } else {
      job.status = "error";
      job.lines.push("[工坊] 网页组装出错(静态卡面已生成, 可先在 projects\\" + job.id + " 查看 static.png)。");
    }
    return;
  }

  let code = await runPy(
    [py, "-u", path.join(__dir, "prepare.py"), job.dir, job.image, job.style, metaPath, job.mode],
    ROOT, logPath, push);
  if (code !== 0) {
    job.status = "error";
    job.lines.push("[工坊] 素材加工失败(见上方提示)。");
    return;
  }
  job.lines.push("[工坊] 素材就绪, 先生成静态卡面(几秒钟, 可先看效果)…");
  await runPy([py, "-u", path.join(__dir, "make_static_card.py"), job.dir], ROOT, logPath, push);
  job.lines.push("[工坊] 开始跑全息流水线(Blender 建场景/导出/组装, 约 1~3 分钟, 日志在命令行窗口)…");
  code = await runPy(
    [py, "-u", path.join(SKILL, "run_pipeline.py"),
     "--project", job.dir, "--blender", BLENDER, "--skip-npm", "--skip-render"],
    ROOT, null, push);
  const glb = path.join(job.dir, "web", "assets", "card.glb");
  if (code === 0 && existsSync(glb)) {
    job.status = "done";
    job.lines.push("[工坊] ✅ 完成! 预览地址: /p/" + job.id + "/");
  } else {
    job.status = "error";
    job.lines.push("[工坊] 流水线出错(请查看启动窗口里的输出, 或把 projects\\" + job.id + " 目录给我排查)。");
  }
}

function nextJob() {
  if (queue.length === 0) return;
  const job = queue.shift();
  jobs.get(job.id).status = "running";
  processJob(job).finally(() => nextJob());
}

// ---------- HTTP ----------
function body(req, limit = 60 << 20) {
  return new Promise((resolve, reject) => {
    let n = 0; const chunks = [];
    req.on("data", (c) => {
      n += c.length;
      if (n > limit) { reject(new Error("too large")); req.destroy(); return; }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

async function nextEdition() {
  try {
    const n = (await readdir(PROJECTS)).filter((x) => x.startsWith("card-")).length + 1;
    return "NO." + String(n).padStart(3, "0") + " / 001";
  } catch { return "NO.001 / 001"; }
}

async function restoreHistory() {
  try {
    for (const id of await readdir(PROJECTS)) {
      if (!/^card-[a-z0-9]+$/.test(id)) continue;
      const dir = path.join(PROJECTS, id);
      try {
        const meta = JSON.parse(await readFile(path.join(dir, "meta.json"), "utf8"));
        let style = "ink", mode = "auto";
        try {
          const cfg = JSON.parse(await readFile(path.join(dir, "card-config.json"), "utf8"));
          style = cfg?._provenance?.style || style;
          mode = cfg?._provenance?.mode || mode;
        } catch {}
        const done = existsSync(path.join(dir, "web", "assets", "card.glb"));
        const up = readdirSync(dir).find((f) => f.startsWith("_upload."));
        const st = await stat(dir);
        jobs.set(id, {
          id, dir, image: up ? path.join(dir, up) : "", style, mode, meta,
          status: done ? "done" : "error",
          lines: ["[工坊] 这是服务重启前生成的卡片(已从磁盘恢复, 可直接预览)。"],
          created: new Date(st.mtimeMs).toLocaleString("zh-CN", { hour12: false }),
          preview: "/p/" + id + "/",
        });
      } catch {}
    }
  } catch {}
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, "http://localhost");
  const p = u.pathname;
  try {
    if (req.method === "POST" && p === "/api/generate") {
      const raw = JSON.parse((await body(req)).toString("utf8"));
      const edition = String(raw.edition || "").trim() || await nextEdition();
      const meta = {
        title: String(raw.title || "无题").slice(0, 40),
        subtitle: String(raw.subtitle || "").slice(0, 60),
        collection: String(raw.collection || "我的全息典藏").slice(0, 60),
        tagline: String(raw.tagline || "").slice(0, 60),
        technique: String(raw.technique || "").slice(0, 40),
        edition: edition.slice(0, 24),
        age: String(raw.age || "").slice(0, 4),
        wish: String(raw.wish || "").slice(0, 80),
        name: String(raw.name || "").slice(0, 24),
        description: String(raw.description || "").slice(0, 200),
        finish: ["gold", "silver", "pearl", "original"].includes(raw.finish) ? raw.finish : "gold",
      };
      const style = ["ink", "space", "plain", "blackgold"].includes(raw.style) ? raw.style : "ink";
      const mode = ["auto", "keep", "cut"].includes(raw.mode) ? raw.mode : "auto";
      const template = ["studio", "night"].includes(raw.template) ? raw.template : "studio";
      if (!raw.imageData) { res.writeHead(400); return res.end("no image"); }
      const m = /^data:image\/(png|jpe?g|webp|gif);base64,(.+)$/s.exec(raw.imageData);
      if (!m) { res.writeHead(400); return res.end("bad image"); }
      const ext = { png: "png", jpeg: "jpg", jpg: "jpg", webp: "webp", gif: "gif" }[m[1]];
      const id = "card-" + Date.now().toString(36);
      const dir = path.join(PROJECTS, id);
      await mkdir(dir, { recursive: true });
      const image = path.join(dir, "_upload." + ext);
      await writeFile(image, Buffer.from(m[2], "base64"));
      const job = {
        id, dir, image, style, mode, template, meta, status: "queued", lines: [],
        created: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
        preview: "/p/" + id + "/",
      };
      jobs.set(id, job);
      queue.push(job);
      job.lines.push("[工坊] 已入队(编号 " + meta.edition + ", 标题: " + meta.title + ")");
      nextJob();
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ id }));
    }

    if (req.method === "GET" && p === "/api/jobs") {
      const list = [...jobs.values()].map((j) => ({
        id: j.id, title: j.meta.title, edition: j.meta.edition, style: j.style,
        template: j.template || "studio",
        staticReady: existsSync(path.join(j.dir, "static-preview.png")),
        status: j.status, created: j.created, last: j.lines.slice(-1)[0] || "",
        export: j.export || null,
      }));
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify(list));
    }

    // ---- 导出卡牌(Card Package + 单文件 Showcase) ----
    if (req.method === "POST" && p === "/api/export") {
      const raw = JSON.parse((await body(req)).toString("utf8"));
      const job = jobs.get(String(raw.id || ""));
      if (!job) { res.writeHead(404); return res.end("no job"); }
      if (!existsSync(path.join(job.dir, "web"))) {
        res.writeHead(400); return res.end("这张卡还没生成完成(缺 web 目录)");
      }
      if (job.export && job.export.status === "running") {
        res.writeHead(409); return res.end("正在导出中");
      }
      job.export = { status: "running", zip: null, url: null };
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
      (async () => {
        const logPath = path.join(job.dir, "export.log");
        try { await rm(logPath, { force: true }); } catch {}
        await mkdir(EXPORTS, { recursive: true }).catch(() => {});
        const digits = (String(job.meta.edition || "").match(/\d+/) || ["1"])[0]
          .slice(-4).padStart(4, "0");
        const args = [process.env.PY || "python", "-u", path.join(__dir, "export_package.py"),
                      job.dir, "--out", EXPORTS, "--card-id", "CARD-" + digits];
        job.lines.push("[工坊] 开始导出 Card Package…");
        const code = await runPy(args, ROOT, logPath, (l) => job.lines.push(l));
        let zip = null;
        try {
          const files = readdirSync(EXPORTS).filter((f) => f.toLowerCase().endsWith(".zip"));
          const withTime = files.map((f) => ({ f, t: statSync(path.join(EXPORTS, f)).mtimeMs }));
          withTime.sort((a, b) => b.t - a.t);
          zip = withTime.length ? withTime[0].f : null;
        } catch {}
        if (code === 0 && zip) {
          job.export = { status: "done", zip, url: "/exports/" + encodeURIComponent(zip) };
          job.lines.push("[工坊] ✅ 导出完成: " + zip);
        } else {
          job.export = { status: "error", zip: null, url: null };
          job.lines.push("[工坊] ⚠ 导出失败(见上方输出)");
        }
      })();
      return;
    }

    if (req.method === "GET" && p.startsWith("/exports/")) {
      const name = decodeURIComponent(p.slice("/exports/".length));
      const file = path.join(EXPORTS, name);
      if (!file.startsWith(EXPORTS) || !existsSync(file)) { res.writeHead(404); return res.end("not found"); }
      const data = await readFile(file);
      res.writeHead(200, {
        "Content-Type": "application/zip",
        "Content-Disposition": 'attachment; filename="' + name.replace(/"/g, "") + '"',
      });
      return res.end(data);
    }

    const logM = p.match(/^\/api\/jobs\/([a-z0-9-]+)\/log$/);
    if (req.method === "GET" && logM) {
      const job = jobs.get(logM[1]);
      if (!job) { res.writeHead(404); return res.end("no job"); }
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ lines: job.lines }));
    }

    // 项目内的静态卡面图(白名单)
    const img = p.match(/^\/cardimg\/([a-z0-9-]+)\/([a-z0-9._-]+)$/i);
    if (img && req.method === "GET") {
      const id = img[1], file = img[2];
      const allow = ["static.png", "static-back.png", "static-preview.png", "static-back-preview.png"];
      if (!/^card-[a-z0-9]+$/.test(id) || !allow.includes(file)) { res.writeHead(404); return res.end("no image"); }
      return serveStatic(req, res, path.join(PROJECTS, id), file);
    }

    const prev = p.match(/^\/p\/([a-z0-9-]+)\/(.*)$/);
    if (prev) {
      const id = prev[1];
      const base = path.join(PROJECTS, id, "web");
      if (!/^card-[a-z0-9]+$/.test(id) || !existsSync(base)) { res.writeHead(404); return res.end("no card"); }
      return serveStatic(req, res, base, prev[2] || "index.html");
    }

    if (req.method === "GET") {
      if (p === "/" || p.startsWith("/index.html")) return serveStatic(req, res, PUBLIC, "index.html");
      return serveStatic(req, res, PUBLIC, p.replace(/^\//, "") || "index.html");
    }
    res.writeHead(405); res.end();
  } catch (e) {
    res.writeHead(500); res.end(String(e && e.message || e));
  }
});

server.listen(PORT, "127.0.0.1", async () => {
  await mkdir(PROJECTS, { recursive: true }).catch(() => {});
  await restoreHistory();
  console.log("卡片工坊已启动: http://127.0.0.1:" + PORT + " (历史卡片 " + jobs.size + " 张)");
  console.log(BLENDER ? "Blender 就绪: " + BLENDER : "警告: 未找到 Blender");
});
