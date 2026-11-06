# 怎么把插件放进插件库

## 未审核的原生插件（待配套 Win顺 0.22.0 发布）

社区原生包可包含 `.exe`、`.dll`，不再仅限解释器脚本。必须提供公开源码、许可证，以及对应 Release 的源码标签/提交和构建说明，建议通过 GitHub Actions 从固定提交构建并提供构建记录。托管源码、构建日志和包的校验值均不等于代码安全审核；不得将“未审核”宣传为“安全认证”。

1. `plugin.json` 的 `minWinShun` 至少为 `0.22.0`。旧客户端没有这类包的安装风险确认。
2. 将 `.wsplugin` 发布在自己的公开 GitHub 仓库，README 写明用途、权限、源码版本和构建方式。
3. 用 `python tools/entry.py <Release附件地址> --unreviewed-native` 生成条目。条目的 `review: "unreviewed-native"` 会进入 index；作者不能自行写 `official` 或 `reviewed`，也不能在后续投稿中移除标记。
4. 提交 `plugins/<id>.json`。继续检查 Release 来源、ID/版本、大小、哈希、链接、重复文件和路径穿越；不执行上传包。此类别允许 exe/dll，其他被禁的驱动、批处理、编译脚本等仍拒绝。压缩包最多 64 MiB、解压最多 256 MiB、单文件最多 64 MiB。
5. 新版本由维护者核对收录来源，保留未审核标记；Win顺 安装及每次更新分别要求用户确认，不走后台自动安装或“全部更新”。

原生 Qt 插件可选择主仓库 `docs/plugins.md` 中的共享 Qt 契约；这不会赋予它审核状态或管理员权限。没有 `review` 字段的历史脚本条目继续按原先的源码审核流程处理，官方原生白名单保持独立。

插件怎么写，看 Win顺 主仓库的文档：[docs/plugins.md](https://github.com/LingCore/WinShun/blob/main/docs/plugins.md)。设置 → 插件 → 高级 → 开发者模式 里有"新建插件…"，能生成一个能跑的模板。

这个仓库不放插件的代码，只放一份目录：每个插件一个文件 `plugins/<id>.json`（叫"条目"），写着插件在哪个仓库、下载哪个文件、这个文件的 sha256。Win顺 设置 → 插件 → 插件库 读的就是用这些条目生成的列表。插件的代码放在你自己的 GitHub 仓库里，由你自己发布。

## 第一次发布

1. 在 GitHub 上建一个公开仓库，比如 `zhangsan/winshun-ip`。插件文件夹里的东西直接放在仓库最外层：`plugin.json`、`README.md`、`LICENSE`、脚本，还有用到的 SDK 文件（`winshun.py`、`WinShun.psm1`，从 Win顺 的 `src/plugins-sdk/` 复制进来）。
2. 把本仓库的 [template/release.yml](template/release.yml) 复制到你的仓库，存成 `.github/workflows/release.yml`。
3. 想先在本地检查一遍的话（可以跳过，发布时也会检查）：把本仓库克隆下来，运行
   ```
   python tools/check.py 你的插件仓库的文件夹 --id zhangsan.ip
   ```
4. 把 `plugin.json` 的 `version` 写好（比如 `1.0.0`），提交，再推一个同样版本号的标签：
   ```
   git tag v1.0.0
   git push origin v1.0.0
   ```
   发布工作流会检查、打包，把 `zhangsan.ip-1.0.0.wsplugin` 附到 v1.0.0 的 Release 上。打开这次运行的页面，摘要里有现成的条目。
5. Fork 本仓库，加一个文件 `plugins/zhangsan.ip.json`，内容二选一：
   - 从上一步的运行摘要里复制；
   - 用工具生成：`python tools/entry.py https://github.com/zhangsan/winshun-ip/releases/download/v1.0.0/zhangsan.ip-1.0.0.wsplugin`

   然后提 PR。PR 只改这一个文件。

不用发布工作流、自己打包上传也行，只要 Release 上的文件名是 `<id>-<版本>.wsplugin`（版本是 `1.2.3` 这样的三段数字），Release 是正式发布的（不是草稿、预发布）。`python tools/build.py 你的插件文件夹` 打出来的包和工作流的一样：只收提交过的文件，以点开头的（`.github`、`.gitignore`……）不收。

## 条目里写了什么

```json
{
  "id": "zhangsan.ip",
  "repo": "zhangsan/winshun-ip",
  "autoUpdate": true,
  "version": "1.0.0",
  "url": "https://github.com/zhangsan/winshun-ip/releases/download/v1.0.0/zhangsan.ip-1.0.0.wsplugin",
  "sha256": "…",
  "size": 12345,
  "name": "查 IP",
  "…": "…"
}
```

- `id`、`repo`、`autoUpdate` 由你定。`autoUpdate: true`：以后你发的新版本，插件库自动跟上（见下面）。
- 其余的字段（版本、网址、sha256、名字、权限……）都是工具从包里读出来的，不要手改，改了检查不会过。
- `bundled`、`hosted` 只有维护者能改。

## 发新版本

改好代码，把 `version` 升上去，提交，推一个新标签（比如 `v1.0.1`）。然后：

- 开了 `autoUpdate`：不用再提 PR。插件库每 6 小时看一次你的仓库：
  - 权限没多、运行方式没变：直接收录新版本。
  - 多要了权限（或者权限的范围变了），或者运行方式变了（换了程序、参数、沙盒等）：自动开一个 PR，维护者看过才收录。
  - 新版本没通过检查：开一个 Issue，写清楚哪里不对。修好以后再发一个更高的版本就行。
- 没开 `autoUpdate`：用 `entry.py` 重新生成条目（或者从运行摘要里复制），提 PR。

已经发出去的包不要删，也不要换成别的内容：插件库每天核对一次，包不见了或者 sha256 变了会开 Issue。要改就发新版本。

## 审核

- 第一次收录：维护者读一遍那个版本的代码再合并。PR 的检查摘要里有源码链接和权限表。看这几件事：
  - 权限和 README 说的一致，代码没有干权限以外的事（比如声明了只读书签，却把内容发出去）。
  - 没有下载再运行别的程序、没有混淆过的代码。
  - 联网的地方，README 里写了连哪里、发什么。
  - 插件在用户自己的普通权限下运行，Win顺 拦不住 `network`，所以这条看得最仔细。
- 之后的更新：机器检查（包能下载、和登记的一样、`plugin.json` 合规、id 和版本对得上），不读代码。多要权限、运行方式变了的更新，维护者再看一遍。

"收录"的意思是：第一版有人读过代码，之后多要权限的版本有人看过。它不是担保。

## 规矩

- 每个插件写明 `author` 和 `license`。你发布的代码要能按这个许可证放出来。
- `id` 写成 `作者.名字`，比如 `zhangsan.ip`。`winshun.` 开头的留给 Win顺 自带的插件。
- 普通社区脚本包只放文本和图片：不收 `.exe` `.dll` `.bat` `.cmd` `.vbs` `.jar` 或 `.pyc`。单个文件不超过 1 MB，整个包解开不超过 5 MB。exe/dll 包须走上方“未审核的原生插件”类别。
- 普通社区脚本运行方式是 `python`、`pwsh`、`powershell`、`node`；未审核原生类别也支持包内 exe 的相对路径。下方官方原生包仍有独立白名单规则。
- 图标用 PNG、JPG 或 ICO，不用 SVG。
- PowerShell 脚本（`.ps1`、`.psm1`）存成带 BOM 的 UTF-8，否则 Windows PowerShell 5.1 里的中文会乱码。
- 权限只要用得到的。`network`、`processes`、`files:write`、`ui`、`winshun:content`、剪贴板，这几项审核时会逐条对照代码看；README 里要写清为什么要。
- 关键字尽量别和已有的撞。撞了检查会给警告，用户可以在设置里改，但最好你先换一个。

`plugin.json` 开头可以加一行 `"$schema": "https://raw.githubusercontent.com/LingCore/WinShun-plugins/main/schema/plugin.schema.json"`，VS Code 里就有补全和提示。Win顺 会忽略这一行。

在 Win顺 里试：把插件文件夹放进 `%LOCALAPPDATA%\WinShun\plugins\`，设置 → 插件 → 高级 → 开发者模式，改了脚本会自动重载。不开界面也能试：

```powershell
wsbench --plugin 你的插件文件夹 --query "ip" --runs 5
```

`wsbench` 要自己从 Win顺 源码编译。

## 老插件（legacy/）

`legacy/` 里是以前直接提交到这个仓库的插件：`day.ocr`、`day.rename`、`crazy-zxx.yigengming`。它们还在这里打包发布：

- 要修改：照旧提 PR，改 `legacy/<id>/` 里的文件，记得把 `version` 升上去。合并后 CI 会打包、发 Release，并把条目指向新版本。PR 里不用改 `plugins/<id>.json`。不再收新的老插件。
- 想搬到自己的仓库（推荐，以后发版本不用等合并）：
  ```
  git clone https://github.com/LingCore/WinShun-plugins
  cd WinShun-plugins
  git subtree split --prefix=legacy/<id> -b <id>
  git push https://github.com/你/你的仓库.git <id>:main
  ```
  这样插件就在你仓库的最外层，历史记录也一起带过去。再按"第一次发布"的第 2、4 步发一个新版本，然后开个 Issue 告诉维护者。维护者会把条目改到你的仓库，删掉 `legacy/<id>/`。

## 维护者

- 自带的脚本插件源码在 Win顺 主仓库的 `plugins/` 里，这里只有条目（`bundled: true`）。发新版本：把主仓库的 `plugins/<id>/` 和它用的 SDK 文件（和 Win顺 构建时复制的一样）放进一个不在 git 仓库里的文件夹，`python tools/build.py 那个文件夹`，把包传到本仓库一个新的 Release，再 `python tools/entry.py <包的网址>`，推到 main。
- Win顺 0.17.0 起，六个官方原生插件从插件库按需安装（`bundled: false`、`minWinShun: 0.17.0`）：`winshun.bookmarks`、`winshun.break`、`winshun.capture`、`winshun.localsend`、`winshun.semantic`、`winshun.translate`。源码在主仓库 `src/<名字>-plugin/`，由主仓库的 `scripts/release.ps1` 生成 `.wsplugin`，发布到 **LingCore/WinShun-plugins** 的新版本 Release。
- 原生例外只接受上述仓库的真实 Release 下载地址，按 `tools/registry.py` 中的 id 对照表核对唯一入口 exe；capture 可额外包含 `WinShunCaptureApp.dll`，图片文字搜索可额外包含 `WinShunOcrSearchApp.dll`。其他 exe、DLL、脚本启动器和驱动仍拒绝。压缩包最多 64 MiB，解压最多 256 MiB，单文件最多 64 MiB；路径穿越、链接及重复条目检查仍适用。声明 `winshun.*` 或在 JSON 中填这个仓库名都不能获得例外。
- 先离线检查实际包并跑 `python -I -m unittest discover -s tools -p test_native.py`；发布后用 `python tools/entry.py <包的网址> --no-bundled --no-auto-update` 联网重新核对附件、哈希、最低宿主版本和权限，再推送条目。不替换已发布同版本包；内容变动时必须升插件版本。Release 说明应记录主仓库源码提交及最低宿主版本。
- `bundled`、`hosted` 这类只有维护者能改的字段，直接推到 main（`entry.py --bundled`、`--hosted`）。
- 每次生成 index.json 后，CI 会用 GitHub Environment `index-signing` 里的私钥（secret `INDEX_SIGNING_KEYS`）签名，把 `index.json.sig` 和 `index.json` 一起传到 `index` Release。私钥只在签名那一步能看到，仓库里只有公钥（`keys/*.pub`）。改 `tools/sign_index.py` 后跑 `python -I -m unittest discover -s tools -p test_sign.py`（要先 `pip install cryptography`）；换钥匙、丢钥匙、泄露怎么办，看 [keys/README.md](keys/README.md)。
- 改了工具，想确认 index.json 没变：先下载已发布的（`gh release download index -p index.json`），再 `python tools/index.py --compare index.json`。没升版本的插件，每个字段都应该一模一样。

### 0.18 插件格式

网页搜索 2.x 使用 `webSearch: true` 和空的 `commands`，由宿主管理网站配置。只允许 `winshun.web` 使用这个能力，且不能声明 `runtime`。图片文字搜索 `winshun.ocr-search` 使用新增的官方原生白名单和 `commands[].contentSearch`，内容搜索命令必须有插件进程。两个新包最低要求 WinShun 0.18.0，发布时使用主仓库构建生成的清单。编辑器 Schema 和 `tools/check.py` 同步维护这些规则。
