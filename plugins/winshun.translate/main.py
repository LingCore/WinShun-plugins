# 翻译 · Translate: a resident Win顺 plugin in Python on the winshun.py SDK.
# `tr sentence` translates with the service the settings name (DeepL, or
# any OpenAI-compatible chat endpoint) and the key the user put in the
# Credential Manager. Without a provider or a key nothing goes online: one
# row says what to set. Shows what streaming looks like: a "翻译中…" row
# goes out at once (query/partial), the translation replaces it.
import json
import re
import urllib.error
import urllib.request

import winshun

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
ICON = "glyph:U+E8C1"
NAMES = {"zh": "中文", "en": "英文", "ja": "日文"}
TIMEOUT = 8


def target_of(text, settings):
    target = (settings.get("target") or "auto").lower()
    if target != "auto":
        return target
    return "en" if CJK.search(text) else "zh"


def deepl(text, target, key):
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    body = json.dumps({"text": [text], "target_lang": {"zh": "ZH", "en": "EN", "ja": "JA"}.get(target, target.upper())}).encode("utf-8")
    request = urllib.request.Request("https://%s/v2/translate" % host, data=body, method="POST", headers={
        "Authorization": "DeepL-Auth-Key " + key, "Content-Type": "application/json", "User-Agent": "WinShun-translate/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = json.loads(response.read().decode("utf-8"))
    translations = data.get("translations") or []
    if not translations:
        raise ValueError("no translation in the answer")
    return translations[0].get("text", ""), translations[0].get("detected_source_language", "")


def openai(text, target, key, endpoint, model):
    base = (endpoint or "https://api.openai.com/v1").rstrip("/")
    prompt = "Translate the following text into %s. Reply with the translation only, no explanations." % NAMES.get(target, target)
    body = json.dumps({"model": model or "gpt-4o-mini", "temperature": 0,
                       "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}]}).encode("utf-8")
    request = urllib.request.Request(base + "/chat/completions", data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "WinShun-translate/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = json.loads(response.read().decode("utf-8"))
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("no choices in the answer")
    return (choices[0].get("message") or {}).get("content", "").strip(), ""


def on_query(q, plugin):
    zh = plugin.locale != "en"
    text = q.text.strip()
    settings = plugin.settings or {}
    provider = (settings.get("provider") or "none").lower()
    key = (settings.get("apiKey") or "").strip()
    if not text:
        return [winshun.item("hint", "输入要翻译的句子" if zh else "Type a sentence to translate",
                             "中文译成英文，其他译成中文；Enter 复制译文" if zh else "Chinese to English, anything else to Chinese; Enter copies",
                             icon=ICON, valid=False)]
    if provider == "none" or not key:
        # Enter opens Win顺's settings at this plugin's card ("winshun:settings"
        # is Win顺's own, never handed to the browser).
        return [winshun.item("setup",
                             "还没有设置翻译服务" if zh else "No translation service set up",
                             "Enter 打开设置 → 插件 → 翻译：选 DeepL 或 OpenAI 兼容，填 API 密钥；没填之前不联网" if zh
                             else "Enter opens Settings → Plugins → Translate: pick DeepL or OpenAI-compatible and enter the API key; nothing is sent until then",
                             icon=ICON, url="winshun:settings")]
    target = target_of(text, settings)
    plugin.partial(q.query_id, [winshun.item("working", "翻译中…" if zh else "Translating…", text, icon=ICON, valid=False)])
    try:
        if provider == "deepl":
            translated, detected = deepl(text, target, key)
        else:
            translated, detected = openai(text, target, key, settings.get("endpoint") or "", settings.get("model") or "")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001 - the body is only a detail
            pass
        return [winshun.item("error", ("接口返回 %d" % e.code) if zh else ("The service answered %d" % e.code), detail or str(e), icon=ICON, valid=False)]
    except Exception as e:  # noqa: BLE001 - every failure becomes one row
        return [winshun.item("error", "翻译失败" if zh else "Translation failed", str(e), icon=ICON, valid=False)]
    if not translated:
        return [winshun.item("empty", "没有译文" if zh else "No translation came back", text, icon=ICON, valid=False)]
    subtitle = "→ " + NAMES.get(target, target) + (" · " + detected if detected else "") + " · " + ("Enter 复制" if zh else "Enter copies")
    return {"items": [winshun.item("t", translated, subtitle, icon=ICON, copy=translated, score=90),
                      winshun.item("source", text, "原文" if zh else "source", icon=ICON, copy=text)],
            "cache": 300}


if __name__ == "__main__":
    winshun.serve(on_query, name="winshun.translate")
