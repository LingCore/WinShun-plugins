# OCR Studio

WinShun 常驻插件。输入 `ocr` 打开独立窗口。截图或上传图片后自动识别，支持用户自选的 OpenAI 兼容视觉模型。

作者：[Day / askd126](https://github.com/askd126) · 许可证：[MIT](LICENSE)

## 安装（社区脚本版）

这是符合本仓库规则的 **Python 源码版本**，与自行分发的内置环境安装包不同：不包含 EXE、DLL 或 Python 运行时。适用于 Windows 10/11 x64，需要 **Python 3.12+（含 Tcl/Tk）**。

1. 在插件库安装，或将本文件夹完整放到 `%LOCALAPPDATA%\WinShun\plugins\day.ocr\`。便携版使用其实际插件目录。
2. 使用 WinShun 插件卡片显示的同一个 Python 解释器安装 `requirements.txt`，不要把依赖装到其他 Python 环境。以源码检出目录为例：

   ```powershell
   python -m pip install -r plugins/day.ocr/requirements.txt
   ```

   如果 Python 位于别处，请用其 `python.exe` 完整路径代替 `python`。Tkinter 不通过 pip 安装，需在 python.org Windows 安装程序中包含 Tcl/Tk 组件。
3. 启用插件，在插件卡片填写模型配置（批量重命名的本地功能无需模型），输入 `ocr` 使用。

启动入口 `bootstrap.py` 在依赖缺失时返回协议提示，不自动联网下载安装组件。源码更改后重新启用插件，或用 WinShun 开发者模式重载。更新同 id 插件前先停用旧版本；永久模型设置仍由 WinShun 管理。

## 模型设置

API 地址、模型名称和 API Key 的填写方式与 OpenAI Chat Completions 兼容服务一致。支持 Base URL 或完整 `/chat/completions` 地址，不预置服务商或密钥。OCR 需要支持图片输入的模型；批量重命名只需文本模型。

窗口内配置只在当前进程内有效；永久配置请使用 WinShun 插件设置，password 密钥由 Windows 凭据管理器保存。示例和源码不包含任何实际密钥。

## 使用

- 窗口「设置」可临时填写 API Key、API 地址和视觉模型 ID；仅在当前进程内有效，不写入磁盘。永久设置请使用 WinShun 插件卡片，其 password 项由 Windows 凭据管理器保存。
- 本机接口允许 `http://localhost:端口/v1` 或 `http://127.0.0.1:端口/v1`；本地免密服务的 API Key 可填任意占位值。远程接口要求 HTTPS。
- `Ctrl+O` 选择图片；`Ctrl+Enter` 开始识别；编辑区 `Ctrl+A` 全选，`Ctrl+C` 复制所选文字。
- 系统截图使用 Windows 的 Win+Shift+S 截图工具，截图前隐藏窗口，接收到新复制的图片后恢复。保留剪贴板图片的原始像素，预览缩放不影响识别。请确保系统快捷键可用；按 Esc 取消，最多等待 60 秒。等待期间复制其他新图片也会被当作本次图片，请勿同时进行其他复制操作。
- 系统截图或上传图片完成后，自动将当前图片发送到已配置的 API 并显示结果；取消选择不会发送。未配置时打开连接设置，应用配置后继续识别。底部「开始识别」用于手动重试。
- 识别期间界面仍可编辑。新的完整结果会替换编辑区内容；需要保留的修改请先复制。
- 取消会丢弃迟到结果，不能撤回已发送的网络请求，也不保证停止计费。上一请求退出前不能再次请求，最长等待 90 秒。
- 当前版本无历史记录、翻译、自动粘贴或后台截图；图片和识别结果仅保存在内存中，关闭 WinShun 后清除。关闭 OCR 窗口只是隐藏，再次输入 `ocr` 可恢复。
- 长文达到输出上限会明确报错，请分区域识别，避免将截断文本误当完整结果。

## 权限与联网

| 权限 | 用途 |
|---|---|
| `ui` | 独立窗口、系统文件选择器及调用系统截图快捷键 |
| `clipboard:read` | 用户点击系统截图后的 60 秒内，仅在剪贴板变化时接收新图片，不读取历史 |
| `network` | 截图或上传完成后自动 POST 发送当前图片、OCR 提示词、模型名和授权密钥到用户设置的服务；没有默认服务或联网目标 |
| `files:read` | 只在用户选择后读取该图片；不扫描目录 |
| `clipboard:write` | 用户点击复制或在编辑器内复制时写入剪贴板 |

不申请 `processes`、`files:write`，不直接启动子程序，不保存图片、文字或密钥。Windows 自行管理系统截图工具的进程。不调用 WinShun 文档搜索。联网和文件读取属于宿主的声明权限，不是操作系统的隔离保证。

自定义 API 地址意味着图片和密钥会发送到那个地址，请使用自己信任且支持视觉输入的接口。不跟随 HTTP 重定向。识别失败会在结果区、状态栏及弹窗保留错误提示，不显示原始响应或密钥。

请求使用 Chat Completions `image_url` + base64 PNG，`detail: high`。不附带某个服务商专属的推理参数，也不限定模型 ID。限单边 8192 像素、4000 万总像素及 PNG 编码 32 MiB；GIF 只处理首帧。服务商可能有更低的图片大小限制。只接受 Responses API、Anthropic Messages 或纯文本输入的接口不属于这里的兼容范围。

## 源码、开发与验证

本目录包含全部运行源码、依赖清单、MIT 许可证和离线回归测试。`main.py` 负责窗口，`protocol.py` 负责 JSON-RPC，`ocr_api.py` 负责核心功能。

```powershell
python plugins/day.ocr/bootstrap.py --standalone
python plugins/day.ocr/bootstrap.py --self-test
python -B -m unittest discover -s plugins/day.ocr/tests -v
python tools/check.py --changed day.ocr
```

`--self-test` 不联网、不读取剪贴板，也不修改用户文件。回归测试的文件操作只发生在临时目录，远端 API 使用模拟响应；不以单元测试代替真实模型及系统拖放/截图验证。会在桌面上显示并缩放窗口的测试需显式设置 `WINSHUN_VISIBLE_LAYOUT_TEST=1`，默认跳过。

仓库 CI 在维护者合并后按标准脚本插件格式发布 `.wsplugin`。该包仍需以上 Python 依赖，不会下载或启动外部二进制程序。
