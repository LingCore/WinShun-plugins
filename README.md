# Win顺 插件库

[Win顺](https://github.com/LingCore/WinShun)（WinShun）是 Windows 上的搜索启动器。它的插件能给搜索框加关键字命令。这里是官方和社区插件的目录：社区插件的源码和发布包放在作者自己的 GitHub 仓库，官方插件的源码在 Win顺 主仓库、发布包在本仓库。这里为每个插件登记一个条目 `plugins/<id>.json`，写着去哪里下载、文件的 sha256。Win顺 的插件库读的就是用这些条目生成的列表。

## 怎么装

- Win顺 设置 → 插件 → **插件库**，点“安装并启用”，需要权限时先确认；拒绝后保留安装、保持关闭。Win顺 下载以后先核对大小和 sha256，对不上就不装。更新保留原来的开关。
- 或者在下面的表里点版本号，下载 `.wsplugin` 文件，再到 Win顺 设置 → 插件 → **从压缩包安装**，选这个文件。

装之前看一眼它要的权限。

## 插件

<!-- plugins:start -->
| 名称 | 关键字 | 说明 | 作者 | 权限 | 下载 |
|---|---|---|---|---|---|
| [易更名](https://github.com/LingCore/WinShun-plugins/tree/main/legacy/crazy-zxx.yigengming) | `br` `rename` `易更名` `批量重命名` `bc` `批量创建` | 带窗口界面的批量文件/文件夹创建与重命名，支持组合规则、实时预览、冲突检查和撤销。 | Xiangxin (@crazy-zxx) | **files:write**、**processes**、**clipboard:read**、**clipboard:write**、**ui**、files:read | [1.3.0](https://github.com/LingCore/WinShun-plugins/releases/download/crazy-zxx.yigengming-v1.3.0/crazy-zxx.yigengming-1.3.0.wsplugin) |
| [OCR Studio](https://github.com/LingCore/WinShun-plugins/tree/main/legacy/day.ocr) | `ocr` | 输入 ocr 打开截图与图片文字识别窗口，支持 OpenAI 兼容的视觉模型。 | Day (askd126) | **clipboard:read**、**clipboard:write**、**ui**、**network**、files:read | [1.0.4](https://github.com/LingCore/WinShun-plugins/releases/download/day.ocr-v1.0.4/day.ocr-1.0.4.wsplugin) |
| [批量重命名](https://github.com/LingCore/WinShun-plugins/tree/main/legacy/day.rename) | `pl` `cmm` | 查找替换、插入内容、自动编号、手动编辑与可选 AI 命名；先预览再执行，支持撤销。 | Day (askd126) | **files:write**、**clipboard:read**、**ui**、**network**、files:read | [1.0.2](https://github.com/LingCore/WinShun-plugins/releases/download/day.rename-v1.0.2/day.rename-1.0.2.wsplugin) |
| [Outlook 邮件](https://github.com/harafuhub/winshun-outlook) | `ol` `mail` | ol 关键词：通过 Windows 搜索索引查找经典 Outlook 的邮件和附件（PDF、Word、Excel 的内容），Enter 打开 | harafuhub | **processes** | [1.4.2](https://github.com/harafuhub/winshun-outlook/releases/download/v1.4.2/harafuhub.outlook-1.4.2.wsplugin) |
| [浏览器书签](https://github.com/LingCore/WinShun/tree/main/src/bookmarks-plugin) | `bm` `sq` | bm 词：搜 Chrome 和 Edge 的书签，Enter 打开 | LingCore | files:read | [2.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.bookmarks-v2.0.0/winshun.bookmarks-2.0.0.wsplugin) |
| [休息提醒](https://github.com/LingCore/WinShun/tree/main/src/break-plugin) | `休息` `break` | 定时提醒休息：小休看看远处，大休起来走走，可以设成必须休完 | LingCore | **ui** | [1.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.break-v1.0.0/winshun.break-1.0.0.wsplugin) |
| [截图与录屏](https://github.com/LingCore/WinShun/tree/main/src/capture-plugin) | `cap` | 截图、标注、贴图、长截图、识别文字和录屏 | LingCore | **files:write**、**processes**、**clipboard:read**、**clipboard:write**、**ui**、winshun:open、notifications | [1.0.1](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.capture-v1.0.1/winshun.capture-1.0.1.wsplugin) |
| [快捷跳转](https://github.com/LingCore/WinShun/tree/main/plugins/winshun.go)<br>（随 Win顺 自带） | `code` `np` `dl` `desk` `pdf` `img` `go` | 零代码示例：code 用 VS Code 打开、dl 下载文件夹、pdf 找 PDF、go 常用位置 | LingCore | **processes** | [1.1.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.go-v1.1.0/winshun.go-1.1.0.wsplugin) |
| [结束进程](https://github.com/LingCore/WinShun/tree/main/plugins/winshun.kill)<br>（随 Win顺 自带） | `kill` `jc` | kill 进程名或 PID：列出进程，Enter 结束，Ctrl+Enter 连同子进程 | LingCore | **processes** | [1.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.kill-v1.0.0/winshun.kill-1.0.0.wsplugin) |
| [局域网传输](https://github.com/LingCore/WinShun/tree/main/src/localsend-plugin) | `传` `ls` | 兼容 LocalSend，手机电脑互传文件 | LingCore | **files:write**、**clipboard:read**、**network**、notifications、**network:listen** | [1.0.2](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.localsend-v1.0.2/winshun.localsend-1.0.2.wsplugin) |
| [按意思找](https://github.com/LingCore/WinShun/tree/main/src/semantic-plugin) | `?` `？` | ? 一句话：按文档讲的是什么来找，不用记得原词。用你选的模型（本机的 Ollama，或云服务的密钥） | LingCore | **network**、**winshun:content** | [1.0.1](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.semantic-v1.0.1/winshun.semantic-1.0.1.wsplugin) |
| [翻译](https://github.com/LingCore/WinShun/tree/main/src/translate-plugin) | `tr` `fy` | tr 句子：中英互译，用你自己的 DeepL 或 OpenAI 兼容接口（在设置里填密钥；不填不联网） | LingCore | **network** | [2.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.translate-v2.0.0/winshun.translate-2.0.0.wsplugin) |
| [网页快捷搜索](https://github.com/LingCore/WinShun/tree/main/plugins/winshun.web)<br>（随 Win顺 自带） | `bd` `gh` `yt` `wiki` `bing` `bili` | 零代码示例：bd 百度、gh GitHub、yt YouTube、wiki 维基百科、bing 必应、bili 哔哩哔哩 | LingCore | 无 | [1.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.web-v1.0.0/winshun.web-1.0.0.wsplugin) |
<!-- plugins:end -->

点名称看插件的源码。权限加粗的几项（联网、起子进程、写文件、开窗口、读文档文字、剪贴板）值得多看一眼插件 README 里的说明。

## 随 Win顺 自带

表里标了“随 Win顺 自带”的 `winshun.go`、`winshun.kill`、`winshun.web`，Win顺 安装时就带着，源码在主仓库的 [plugins/](https://github.com/LingCore/WinShun/tree/main/plugins) 里。另外两个是 C++ 写的程序，也和 Win顺 一起装好，不在表里：

- [winshun.tools](https://github.com/LingCore/WinShun/tree/main/plugins/winshun.tools)：计算器、单位换算、颜色、时间戳、UUID、Base64、哈希。
- [winshun.switches](https://github.com/LingCore/WinShun/tree/main/src/switches-plugin)：系统开关，可在插件设置中启用或停用。

## 官方可选插件

Win顺 0.17.0 起，截图与录屏（`winshun.capture`）、局域网传输（`winshun.localsend`）、按意思找（`winshun.semantic`）、休息提醒（`winshun.break`）、翻译（`winshun.translate`）、浏览器书签（`winshun.bookmarks`）从插件库按需安装，最低要求 Win顺 **0.17.0**，标准、便携和完整离线安装包均不包含它们。源码位于主仓库的 `src/<名字>-plugin/`，包由本仓库分发，下载见上表。

升级时，原来开启的这些功能会尝试从插件库恢复，保留原有设置。暂时无法下载时，在设置 → 插件 → 已安装中重试恢复，或从本地 `.wsplugin` 包安装后启用。插件包需要修改时会发布新版本，保留旧附件。

## 安全

- 插件永远以你自己的普通权限运行，不是管理员。Win顺 能强制的权限（起子进程、剪贴板等）会强制；`network` 和 `files:read` 它拦不住，只能告诉你。
- "收录"的意思是：插件第一次收录时，维护者读过那个版本的代码；之后的新版本由机器检查（包没被换掉、`plugin.json` 合规、权限有没有变多），多要权限或者运行方式变了的新版本，维护者再看一遍才收录。它不是担保。只装你信得过的，装之前看一眼权限。
- 发现有问题的插件，请开 Issue。

## 想写一个插件

看 [CONTRIBUTING.md](CONTRIBUTING.md)：插件放在你自己的仓库里，打个标签发布，再来这里加一个条目。插件格式见 Win顺 的 [docs/plugins.md](https://github.com/LingCore/WinShun/blob/main/docs/plugins.md)。没有主意的话，可以开一个"想要一个插件"的 Issue。

以前直接提交到这里的插件在 [legacy/](legacy) 里，还在这里打包发布。

## 本仓库的许可证

仓库里的脚本和文档（`tools/`、`.github/`、`schema/`、`template/` 等）用 MIT。每个插件的许可证以它自己的 `license` 字段为准（`legacy/` 里的老插件也一样）。

---

## English

This is the index of official and community plugins for [Win顺 / WinShun](https://github.com/LingCore/WinShun), a Windows search launcher. Community plugins live in their authors' own GitHub repositories and are published there as `<id>-<version>.wsplugin` release assets. Official plugins have their source in the WinShun repository and their packages here. This repository keeps one entry per plugin, `plugins/<id>.json`, with the package's address and SHA-256. CI builds `index.json` from the entries and attaches it to the `index` release, which WinShun's in-app plugin library reads. In Settings → Plugins → Library, choose **Install and enable** and review the requested permissions; declining keeps the plugin installed and disabled. Downloads are checked for size and SHA-256 before installation, and updates preserve the enabled state. You can also download a package from the table and use Settings → Plugins → Install from archive, then enable it.

Since WinShun 0.17.0, screenshots and recording (`winshun.capture`), LAN transfer (`winshun.localsend`), semantic search (`winshun.semantic`), break reminders (`winshun.break`), translation (`winshun.translate`) and browser bookmarks (`winshun.bookmarks`) are optional downloads requiring **WinShun 0.17.0 or later**. They are separate from the standard, portable and offline packages. Previously enabled features are recovered from the library during upgrade while keeping their settings. If downloading fails, retry recovery in Settings → Plugins → Installed, or install a local `.wsplugin` and enable it. Package changes are published as new versions; existing assets are retained.

Plugins run with your own normal (non-admin) rights. "Listed" means a maintainer read the code of the first listed version. Later versions are checked automatically (the package is unchanged, the manifest is valid), and a version that asks for more permissions or changes how it runs is reviewed again before it is listed. It is not a guarantee, so read the permissions first.

To submit a plugin, see [CONTRIBUTING.md](CONTRIBUTING.md) (in Chinese): put the plugin in your own repository, copy [template/release.yml](template/release.yml), push a `v<version>` tag, then open a PR that adds `plugins/<id>.json` (made by `python tools/entry.py <package URL>`, or copied from the release run's summary). The plugin format is in the [plugin docs](https://github.com/LingCore/WinShun/blob/main/docs/plugins.md). Plugins submitted earlier as folders live in `legacy/` and are still packed and released here. `winshun.go`, `winshun.kill` and `winshun.web` ship with WinShun, as do the C++ utility plugin `winshun.tools` and system-switch plugin `winshun.switches`.
