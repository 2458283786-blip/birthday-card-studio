# -*- coding: utf-8 -*-
"""
Design Language 2.0 · AI 适配层(DeepSeek)
=========================================
设计原则(见讨论):
  * AI 只做「阅读理解 + 决策 JSON」, 不产出图片
  * 只用标准库 urllib, 零额外依赖
  * key 只从环境变量 DEEPSEEK_API_KEY 读取, 绝不写入任何文件
  * 任何失败都不抛给调用方致死 —— 返回 None, 由上层回退到纯程序化方案
"""
import base64
import io
import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
MAX_SIDE = 1024          # 上传缩略图上限(隐私 + token 双友好)


def key_present():
    return bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())


def _thumb_b64(path, max_side=MAX_SIDE, quality=88):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    try:                                   # 内容方向不对(手机常见)时先转正, 减少模型误判
        from orient import detect
        deg, conf, _detail = detect(path)
        if deg and conf >= 0.6:
            im = im.rotate(-deg, expand=True)
    except Exception:
        pass
    im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode(), im.size


def ask_image(image_path, prompt, schema_hint=None, detail="low", timeout=120, retries=1):
    """把图片(缩略图)+ 提示词发给 DeepSeek, 返回 (text, meta); 失败返回 (None, {"error": ...})。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return None, {"error": "no_key"}
    try:
        b64, size = _thumb_b64(image_path)
    except Exception as e:
        return None, {"error": f"image:{type(e).__name__}"}

    full_prompt = prompt if not schema_hint else f"{prompt}\n\n只输出 JSON, 结构如下:\n{schema_hint}"
    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": full_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": detail}},
            ],
        }],
        "temperature": 0.2,
        "max_tokens": int(os.environ.get("DEEPSEEK_MAX_TOKENS", "6000")),   # 含思考 token, 给足
    }
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                API_URL, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
            text = (data["choices"][0]["message"].get("content") or "").strip()
            usage = data.get("usage", {})
            if not text:                     # 思考没写完就当失败, 重试
                last = "empty_content"
                continue
            return text, {"model": data.get("model", MODEL), "thumb": list(size), "usage": usage}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:200]}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return None, {"error": last}


def parse_json(text):
    """从模型回复里抠出 JSON(容忍 ```json 包裹与前后废话)。"""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(s[i:j + 1])
    except Exception:
        return None
