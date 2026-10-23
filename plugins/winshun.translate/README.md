# 翻译 · Translate

随 Win顺 安装的 Python 常驻插件（`main.py` + SDK `winshun.py`，需要 Python 3）。输入 `tr 句子`（或 `fy 句子`）：中文译成英文，其他译成中文（设置里可以固定译成某种语言）。Enter 复制译文。

**默认不联网。** 要用它，先在设置 → 插件 → 翻译里：
1. **翻译服务**选 DeepL 或 OpenAI 兼容；
2. 填 **API 密钥**——它存在 Windows 凭据管理器里，不写进 `WinShun.ini`，也不进插件日志；
3. OpenAI 兼容的再填**接口地址**（如 `https://api.openai.com/v1`，或任何兼容服务）和**模型**。

没设置时输入 `tr 任何东西` 只会看到一行提示，不会发出任何请求。

这个插件演示的是：
- **settings**：`choice`、`password`、`text` 三种设置项，改了常驻进程立刻知道（`settingsChanged`）；
- **network** 权限：只是声明——Win顺 挡不住插件联网，卡片上标"仅声明"；
- **流式结果**：先推一行"翻译中…"（`query/partial`），译文回来再替换；
- `cache`：同一句 5 分钟内不再请求。

---

A resident Python plugin on the `winshun.py` SDK (Python 3 needed): `tr sentence` translates Chinese to English and anything else to Chinese, with **your own** DeepL or OpenAI-compatible API. Nothing goes online until a service and a key are set in Settings → Plugins → Translate (the key lives in Windows Credential Manager). It shows declared settings (`choice`, `password`, `text`), the `network` permission (a declaration only), streaming (a "Translating…" row first, `query/partial`) and `cache`.
