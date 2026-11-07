# GUI 插件自包含包

`build_desktop.py` 为 `day.ocr` 和 `day.rename` 构建 Windows x64 目录包。运行时、Tcl/Tk 与图片和界面依赖随插件更新统一维护，插件通过标准输入输出与 Win顺 通信。

构建使用 CPython 3.15.2 x64 和 `desktop-requirements.txt` 中固定版本、带 SHA256 的 Windows wheel。已验证的运行时为 python-build-standalone 20261026 的 `cpython-3.15.2+20261026-x86_64-pc-windows-msvc-install_only_stripped.tar.gz`，SHA256 为 `02e532b60e720aa3d77e757c349ae9cc945441c05851fa646336fc9ff0403041`。[运行时发布](https://github.com/astral-sh/python-build-standalone/releases/tag/20261026)

在仓库根目录执行以下命令，`python.exe` 使用上述运行时的完整路径。

```powershell
python.exe -m pip install --require-hashes -r tools/desktop-requirements.txt
python.exe tools/build_desktop.py day.ocr day.rename --build-dir build/desktop --out dist/desktop
```

构建器从 `--source-ref` 指向的提交导出源码，默认使用 HEAD 和该提交中插件清单的版本。`--version 1.1.0` 可为本地候选包指定版本。产物包括 `.wsplugin`、`.sha256`、`.build.json` 和供发布流程使用的 `desktop.tsv`。收据记录源码提交、源码文件哈希、工具链版本、包校验值和最终解包后 EXE 的自检结果。临时构建在成功或失败后均自动回收。

包的 ID、命令和设置键沿用脚本版，发布版本由源码清单统一管理，正式更新须高于已发布版本。构建清单切换到包内 EXE，并声明最低 Win顺 0.22.0。源码目录的 Python 清单继续用于源码调试。

EXE 采用 PyInstaller onedir 和 console 子系统，宿主以 `CREATE_NO_WINDOW` 启动，保留 JSON-RPC 标准输入输出。自检从最终包解压到中文目录中运行，使用空白配置及仅含系统目录的 PATH。构建器还执行插件库的未审核原生包检查。

发布前还须使用真实 Host → Runner 验证关键词启动、窗口显示和脚本版升级，并确认已有配置、数据与权限记录。线上条目须带 `review: "unreviewed-native"`，按现有流程由 `entry.py --unreviewed-native` 生成。安装及每次更新均需用户确认。

`legacy/<id>/desktop.json` 将对应插件交给 Windows 自包含构建任务，普通 legacy 打包器会跳过它。发布流程使用 `--pending`，只构建版本高于当前条目的插件，并将同版本的 Release、SHA256 和构建收据一起上传。原生 Release 标签指向收据中的源码提交，线上条目通过 `entry.py --unreviewed-native` 更新。
