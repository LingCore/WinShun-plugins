# 网页快捷搜索 · Web shortcuts

零代码插件：只有这一个 `plugin.json`，没有脚本。输入 `bd 关键字` 用百度搜，`gh ` 单独输入打开 GitHub 首页；`%s` 是要搜的文字，按网址规则编码。

## 和设置里"网页搜索"的关系

设置 → **网页搜索** 做的是同一件事，而且是你自己维护的那份：那里的关键字永远优先。这个插件的 `gh`、`bd` 和网页搜索里的撞了名，插件的那条就停用，插件卡片上会写"关键字 gh 已被网页搜索占用"——改一个，或者不用这个插件就是了。两边的网址写法相同（`%s`），所以想长期用的条目放进"网页搜索"更顺手（右键结果就能编辑）；插件适合成套分享、或者和脚本命令放在一起。

要加自己的：复制这个文件夹到 `%LOCALAPPDATA%\WinShun\plugins\`，改 `id`、加一条 `{"id", "keyword", "title", "run": {"url": "…%s…", "home": "…"}}`。

---

A zero-code plugin: `plugin.json` only. `bd words` searches Baidu, `gh ` alone opens GitHub; `%s` is the text, URL-encoded. Settings → **Web search** does the same thing and its keywords always win: a clash (such as `gh` there too) sets the plugin's keyword aside, and the card says so. Put the shortcuts you keep into Web search (editable from a result's menu); plugins suit sets you share or keep with script commands.
