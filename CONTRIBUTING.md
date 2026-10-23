# 怎么提交一个插件

插件怎么写，看 Win顺 主仓库的文档：[docs/plugins.md](https://github.com/LingCore/WinShun/blob/main/docs/plugins.md)。设置 → 插件 → 高级 → 开发者模式 里有"新建插件…"，能生成一个能跑的模板。

这篇只讲怎么放进这个仓库。

## 步骤

1. Fork 这个仓库。
2. 在 `plugins/` 下建文件夹，名字和插件的 `id` 一样，`作者.名字` 的形式，例如 `plugins/zhangsan.ip/`。
3. 文件夹里至少要有：
   - `plugin.json`
   - `README.md`：它做什么、怎么用、要哪些权限、为什么要。
   - 脚本和 SDK 文件（`winshun.py`、`WinShun.psm1` 要自己复制进来，从 Win顺 的 `src/plugins-sdk/`）。
4. 本地检查：`python tools/check.py`。有错会告诉你哪个文件哪一行不对。
5. 在 Win顺 里试：把文件夹放进 `%LOCALAPPDATA%\WinShun\plugins\`，设置 → 插件 → 高级 → 开发者模式，改了脚本会自动重载。不开界面也能试：
   ```powershell
   wsbench --plugin plugins\zhangsan.ip --query "ip" --runs 5
   ```
   `wsbench` 要自己从 Win顺 源码编译。
6. 提 PR，把模板里的清单勾一遍。

`plugin.json` 开头可以加一行 `"$schema": "https://raw.githubusercontent.com/LingCore/WinShun-plugins/main/schema/plugin.schema.json"`，VS Code 里就有补全和提示。Win顺 会忽略这一行。

## 更新自己的插件

改了文件就把 `version` 升高（`1.0.0` → `1.0.1`）。不升版本，检查不会过：同一个版本只发布一次，内容不能偷偷变。

## 这个仓库的规矩

- 每个插件写明 `author` 和 `license`。你提交的代码要能按这个许可证放出来。
- 只放文本和图片：不收 `.exe` `.dll` `.bat` `.cmd` `.vbs` `.jar` 这类能直接运行的文件，也不收 `.pyc`。单个文件不超过 1 MB，整个文件夹不超过 5 MB。
- 运行方式只用 `python`、`pwsh`、`powershell`、`node`。要带自己的 exe 的插件，放在自己的仓库，这里不收。
- 图标用 PNG、JPG 或 ICO，不用 SVG。
- PowerShell 脚本（`.ps1`、`.psm1`）存成带 BOM 的 UTF-8，否则 Windows PowerShell 5.1 里的中文会乱码。
- 权限只要用得到的。`network`、`processes`、`files:write`、`ui`、`winshun:content`、剪贴板，这几项审核时会逐条对照代码看；README 里要写清为什么要。
- 关键字尽量别和已有的撞。撞了检查会给警告，用户可以在设置里改，但最好你先换一个。

## 审核

维护者会读一遍代码再合并。看这几件事：

- 权限和 README 说的一致，代码没有干权限以外的事（比如声明了只读书签，却把内容发出去）。
- 没有下载再运行别的程序、没有混淆过的代码。
- 联网的地方，README 里写了连哪里、发什么。
- 插件在你自己的普通权限下运行，Win顺 不能拦住 `network`，所以这条看得最仔细。

合并后 CI 会自动发布一个 `<id>-v<version>` 的 Release，附上 `.wsplugin` 文件，并更新 README 里的表。

"已收录"的意思是：合并时有人读过代码。它不是担保，装之前请看一眼 README 里的权限。
