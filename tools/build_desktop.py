"""Build self-contained Windows packages from a committed legacy source snapshot.

Run with CPython 3.15.2 x64 and tools/desktop-requirements.txt installed.
Example: python tools/build_desktop.py day.ocr day.rename --version 1.1.0
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import check
import registry

PROGRAMS = {"day.ocr": "OCRStudio", "day.rename": "BatchRename"}
PYTHON_VERSION = "3.15.2"
REQUIREMENTS = Path(__file__).with_name("desktop-requirements.txt")


def toolchain() -> dict:
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise ValueError("Build with Windows x64 CPython")
    if platform.python_version() != PYTHON_VERSION:
        raise ValueError(f"Build with CPython {PYTHON_VERSION}")
    versions = {"python": PYTHON_VERSION}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, expected = line.split(" --hash=", 1)[0].split("==")
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise ValueError(f"Install {REQUIREMENTS}: {name} requires {expected}, found {actual}")
        versions[name] = actual
    return versions


def snapshot(plugin: str, commit: str, destination: Path) -> dict[str, str]:
    prefix = f"legacy/{plugin}/"
    archive = subprocess.run(["git", "-C", str(registry.ROOT), "archive", commit, prefix],
                             check=True, capture_output=True).stdout
    hashes = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source.getmembers():
            name = member.name.removeprefix(prefix)
            if not member.isfile() or "/" in name or not name:
                continue
            content = source.extractfile(member).read()
            (destination / name).write_bytes(content)
            hashes[name] = hashlib.sha256(content).hexdigest()
    return hashes


def self_test(executable: Path, work: Path) -> dict:
    # Exercise the extracted bundle with a fresh profile and no external runtime paths.
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith(("PYTHON", "TCL", "TK", "WS_"))}
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    for key in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP"):
        directory = work / "profile" / key
        directory.mkdir(parents=True, exist_ok=True)
        environment[key] = str(directory)
    completed = subprocess.run([str(executable), "--self-test"], env=environment,
                               capture_output=True, text=True, encoding="utf-8", timeout=30,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    if completed.returncode:
        raise RuntimeError(f"Bundle self-test failed\n{completed.stdout}\n{completed.stderr}")
    result = json.loads(completed.stdout)
    if not result.get("ok") or not result.get("frozen") or result.get("python") != PYTHON_VERSION:
        raise RuntimeError(f"Unexpected bundle self-test result {result}")
    return result


def build_one(plugin: str, version: str, commit: str, versions: dict, work: Path, out: Path) -> dict:
    target = out / f"{plugin}-{version}.wsplugin"
    for path in (target, out / f"{target.name}.sha256", out / f"{plugin}-{version}.build.json"):
        if path.exists():
            raise FileExistsError(f"Choose a fresh output directory, already exists: {path}")
    source = work / "source"
    source.mkdir()
    hashes = snapshot(plugin, commit, source)
    descriptor = source / "desktop.json"
    if descriptor.is_file() and json.loads(descriptor.read_text(encoding="utf-8")) != {"format": "pyinstaller-onedir"}:
        raise ValueError("Unsupported desktop build format")
    manifest = json.loads((source / "plugin.json").read_text(encoding="utf-8"))
    if registry.version_key(version) < registry.version_key(manifest["version"]):
        raise ValueError("The desktop package version must be at least the source version")
    program = PROGRAMS[plugin]
    manifest["version"] = version
    manifest["minWinShun"] = "0.22.0"
    manifest["runtime"]["program"] = f"{program}.exe"
    manifest["runtime"].pop("script", None)
    # A console-subsystem executable retains JSON-RPC pipes. The host uses
    # CREATE_NO_WINDOW, and direct self-tests use the same flag.
    command = [sys.executable, "-m", "PyInstaller", "--onedir", "--console", "--noupx",
               "--name", program, "--icon", "NONE", "--hide-console", "hide-early",
               "--distpath", str(work / "bundle"), "--workpath", str(work / "objects"),
               "--specpath", str(work), "--collect-data", "customtkinter",
               "--copy-metadata", "customtkinter", "--copy-metadata", "pillow",
               "--copy-metadata", "darkdetect", "--copy-metadata", "packaging",
               str(source / "main.py")]
    environment = dict(os.environ, SOURCE_DATE_EPOCH=subprocess.run(
        ["git", "-C", str(registry.ROOT), "show", "-s", "--format=%ct", commit],
        check=True, capture_output=True, text=True).stdout.strip())
    # PyInstaller's cache belongs to this disposable build as well.
    environment["PYINSTALLER_CONFIG_DIR"] = str(work / "cache")
    subprocess.run(command, check=True, cwd=source, env=environment)
    bundle = work / "bundle" / program
    (bundle / "plugin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(source / "LICENSE", bundle / "LICENSE")
    licenses = bundle / "licenses"
    licenses.mkdir()
    shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python.txt")
    distribution = importlib.metadata.distribution("pyinstaller")
    for file in distribution.files or ():
        if file.name == "COPYING.txt":
            shutil.copyfile(distribution.locate_file(file), licenses / "PyInstaller.txt")
    name = build.pick(manifest["name"])
    readme = f"""# {name} {version}

适用于 Windows 10/11 x64 和 Win顺 0.22.0 及以上版本。
Python {PYTHON_VERSION}、Tcl/Tk、Pillow 和 CustomTkinter 随插件包提供，由插件更新统一维护。

在 Win顺 设置 → 插件 → 从压缩包安装中选择本包，确认安装及所需权限，然后启用插件。
同 ID 的旧版会原位升级，配置和插件数据由 Win顺 保留。
插件库按未审核原生插件类别收录，安装及每次更新均需确认。
命令、功能、模型配置和权限说明见对应源码 README。

[源码和功能说明](https://github.com/LingCore/WinShun-plugins/tree/{commit}/legacy/{plugin})
[构建说明](https://github.com/LingCore/WinShun-plugins/blob/main/tools/desktop.md)

源码作者及许可证见 LICENSE，随包组件许可证见 licenses 和 _internal 中的组件目录。
"""
    (bundle / "README.md").write_text(readme, encoding="utf-8")
    metadata = {"id": plugin, "version": version, "review": "unreviewed-native",
                "sourceCommit": commit, "sourceSha256": hashes, "toolchain": versions,
                "requirementsSha256": hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()}
    (bundle / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    inspected = check.check_plugin(bundle, expected_id=plugin, packed=True, unreviewed_native=True)
    if inspected.errors:
        raise ValueError("\n".join(inspected.errors))
    package = work / f"{plugin}-{version}.wsplugin"
    build.pack(bundle, package, compression=zipfile.ZIP_DEFLATED)
    content = package.read_bytes()
    checked = check.check_package(content, plugin, version, package.name, unreviewed_native=True)
    if checked.errors:
        raise ValueError("\n".join(checked.errors))
    extracted = work / "验证安装包"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(extracted)
    result = self_test(extracted / f"{program}.exe", work)
    # Self-tests may report their executable path. Keep receipts independent of
    # the temporary directory that is removed when this build finishes.
    result.pop("executable", None)
    digest = hashlib.sha256(content).hexdigest()
    # On Windows rename atomically publishes a completed file and rejects an
    # existing destination, including another build of this same version.
    with tempfile.TemporaryDirectory(prefix=plugin + "-publish-", dir=out) as directory:
        staged = Path(directory) / package.name
        shutil.copyfile(package, staged)
        staged.rename(target)
    (out / f"{package.name}.sha256").write_text(f"{digest}  {package.name}\n", encoding="ascii", newline="\n")
    metadata.update(sha256=digest, size=len(content), selfTest=result)
    (out / f"{plugin}-{version}.build.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"package": str(target), "sha256": digest, "selfTest": result}, ensure_ascii=False), flush=True)
    return {"id": plugin, "version": version, "file": target.name, "sha256": digest,
            "name": " ".join(name.split())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugins", nargs="+", choices=PROGRAMS)
    parser.add_argument("--version", help="Override the committed source version for a local candidate")
    parser.add_argument("--source-ref", default="HEAD")
    parser.add_argument("--pending", action="store_true", help="Only build versions newer than the registry entries")
    parser.add_argument("--build-dir", type=Path, default=registry.ROOT / "build" / "desktop")
    parser.add_argument("--out", type=Path, default=registry.ROOT / "dist" / "desktop")
    args = parser.parse_args()
    if args.version and not registry.PLAIN_VERSION_RE.fullmatch(args.version):
        parser.error("--version requires a stable x.y.z version")
    commit = subprocess.run(["git", "-C", str(registry.ROOT), "rev-parse", "--verify", f"{args.source_ref}^{{commit}}"],
                            check=True, capture_output=True, text=True).stdout.strip()
    args.build_dir.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    planned = []
    for plugin in args.plugins:
        source = subprocess.run(["git", "-C", str(registry.ROOT), "show", f"{commit}:legacy/{plugin}/plugin.json"],
                                check=True, capture_output=True).stdout
        version = args.version or json.loads(source)["version"]
        published = registry.load_json(registry.ROOT / "plugins" / f"{plugin}.json")["version"]
        if args.pending and registry.version_key(version) <= registry.version_key(published):
            continue
        planned.append((plugin, version))
    versions = toolchain() if planned else {}
    rows = []
    for plugin, version in planned:
        with tempfile.TemporaryDirectory(prefix=plugin + "-", dir=args.build_dir.resolve()) as directory:
            built = build_one(plugin, version, commit, versions, Path(directory), args.out.resolve())
            rows.append("\t".join(built[key] for key in ("id", "version", "file", "sha256", "name")))
    (args.out / "desktop.tsv").write_bytes("".join(row + "\n" for row in rows).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
