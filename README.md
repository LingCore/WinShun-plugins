# Win顺 插件库

[Win顺](https://github.com/LingCore/WinShun)（WinShun）是 Windows 上的搜索启动器。它的插件能给搜索框加关键字命令。这个仓库收集大家写的插件，每个插件一个文件夹，在 [Releases](https://github.com/LingCore/WinShun-plugins/releases) 里下载。

## 怎么装

1. 在下面的表里点"下载"，或到 [Releases](https://github.com/LingCore/WinShun-plugins/releases) 找到插件，下载 `.wsplugin` 文件。
2. 打开 Win顺 设置 → 插件 → **从压缩包安装**，选这个文件。
3. 看一眼它要的权限，打开开关。

## 插件

<!-- plugins:start -->
| 名称 | 关键字 | 说明 | 作者 | 权限 | 下载 |
|---|---|---|---|---|---|
| [易更名](plugins/crazy-zxx.yigengming) | `br` `rename` `易更名` `批量重命名` `bc` `批量创建` | 带窗口界面的批量文件/文件夹创建与重命名，支持组合规则、实时预览、冲突检查和撤销。 | Xiangxin (@crazy-zxx) | **files:write**、**processes**、**clipboard:read**、**clipboard:write**、**ui**、files:read | [1.3.0](https://github.com/LingCore/WinShun-plugins/releases/download/crazy-zxx.yigengming-v1.3.0/crazy-zxx.yigengming-1.3.0.wsplugin) |
| [OCR Studio](plugins/day.ocr) | `ocr` | 输入 ocr 打开截图与图片文字识别窗口，支持 OpenAI 兼容的视觉模型。 | Day (askd126) | **clipboard:read**、**clipboard:write**、**ui**、**network**、files:read | [1.0.4](https://github.com/LingCore/WinShun-plugins/releases/download/day.ocr-v1.0.4/day.ocr-1.0.4.wsplugin) |
| [批量重命名](plugins/day.rename) | `pl` `cmm` | 查找替换、插入内容、自动编号、手动编辑与可选 AI 命名；先预览再执行，支持撤销。 | Day (askd126) | **files:write**、**clipboard:read**、**ui**、**network**、files:read | [1.0.2](https://github.com/LingCore/WinShun-plugins/releases/download/day.rename-v1.0.2/day.rename-1.0.2.wsplugin) |
| [浏览器书签](plugins/winshun.bookmarks)<br>（随 Win顺 自带） | `bm` `sq` | bm 词：搜 Chrome 和 Edge 的书签，Enter 打开 | LingCore | files:read | [1.1.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.bookmarks-v1.1.0/winshun.bookmarks-1.1.0.wsplugin) |
| [快捷跳转](plugins/winshun.go)<br>（随 Win顺 自带） | `code` `np` `dl` `desk` `pdf` `img` `go` | 零代码示例：code 用 VS Code 打开、dl 下载文件夹、pdf 找 PDF、go 常用位置 | LingCore | 无 | [1.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.go-v1.0.0/winshun.go-1.0.0.wsplugin) |
| [结束进程](plugins/winshun.kill)<br>（随 Win顺 自带） | `kill` `jc` | kill 进程名或 PID：列出进程，Enter 结束，Ctrl+Enter 连同子进程 | LingCore | **processes** | [1.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.kill-v1.0.0/winshun.kill-1.0.0.wsplugin) |
| [翻译](plugins/winshun.translate)<br>（随 Win顺 自带） | `tr` `fy` | tr 句子：中英互译，用你自己的 DeepL 或 OpenAI 兼容接口（在设置里填密钥；不填不联网） | LingCore | **network** | [1.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.translate-v1.0.0/winshun.translate-1.0.0.wsplugin) |
| [网页快捷搜索](plugins/winshun.web)<br>（随 Win顺 自带） | `bd` `gh` `yt` `wiki` `bing` `bili` | 零代码示例：bd 百度、gh GitHub、yt YouTube、wiki 维基百科、bing 必应、bili 哔哩哔哩 | LingCore | 无 | [1.0.0](https://github.com/LingCore/WinShun-plugins/releases/download/winshun.web-v1.0.0/winshun.web-1.0.0.wsplugin) |
<!-- plugins:end -->

权限加粗的几项（联网、起子进程、写文件、开窗口、读文档文字、剪贴板）值得多看一眼 README 里的说明。

## 随 Win顺 自带

下面两个插件是 C++ 写的程序，和 Win顺 一起装好，不在这个仓库里：

- [winshun.tools](https://github.com/LingCore/WinShun/tree/main/plugins/winshun.tools)：计算器、单位换算、颜色、时间戳、UUID、Base64、哈希。
- [winshun.semantic](https://github.com/LingCore/WinShun/tree/main/plugins/winshun.semantic)：按意思找文档。

表里标了"随 Win顺 自带"的插件，Win顺 安装时也带着，这里放一份是为了方便看代码、当例子。

## 安全

- 插件永远以你自己的普通权限运行，不是管理员。Win顺 能强制的权限（起子进程、剪贴板等）会强制；`network` 和 `files:read` 它拦不住，只能告诉你。
- "已收录"的意思是：合并时有维护者读过代码。它不是担保。只装你信得过的，装之前看一眼权限。
- 发现有问题的插件，请开 Issue。

## 想写一个插件

看 [CONTRIBUTING.md](CONTRIBUTING.md)。插件格式见 Win顺 的 [docs/plugins.md](https://github.com/LingCore/WinShun/blob/main/docs/plugins.md)。没有主意的话，可以开一个"想要一个插件"的 Issue。

## 本仓库的许可证

仓库里的脚本和文档（`tools/`、`.github/`、`schema/` 等）用 MIT。每个插件有自己的 `license` 字段，以它为准。

---

## English

Community plugins for [Win顺 / WinShun](https://github.com/LingCore/WinShun), a Windows search launcher. Each plugin lives in `plugins/<id>/` and is published as a `.wsplugin` file under Releases. To install one: download the file, then Win顺 Settings → Plugins → Install from archive. A machine-readable list is at the `index` release (`index.json`), which a future in-app browser will read.

Plugins run with your own normal (non-admin) rights. "Listed" means a maintainer read the code when it was merged. It is not a guarantee, so read the permissions first.

To submit a plugin, see [CONTRIBUTING.md](CONTRIBUTING.md) (in Chinese); the format is in the [plugin docs](https://github.com/LingCore/WinShun/blob/main/docs/plugins.md). Run `python tools/check.py` before opening a PR. `winshun.tools` and `winshun.semantic` are C++ programs that ship inside Win顺 and are not copied here.
