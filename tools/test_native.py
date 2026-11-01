"""Official native assets keep the community rules and archive checks intact."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import check
import registry


def package(extra=None, program="WinShunCapture.exe"):
    manifest = {"manifest": 1, "id": "winshun.capture", "name": "Capture", "version": "1.0.0",
                "description": "Capture", "author": "LingCore", "license": "MIT", "minWinShun": "0.17.0",
                "runtime": {"mode": "resident", "program": program}, "permissions": ["ui"],
                "commands": [{"id": "capture", "keyword": ["cap"], "title": "Capture"}]}
    files = {"plugin.json": json.dumps(manifest).encode(), "README.md": b"Capture with ui permission.",
             "WinShunCapture.exe": b"MZfixture", "WinShunCaptureApp.dll": b"MZfixture"}
    files.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


class NativePolicy(unittest.TestCase):
    def asset(self, repo):
        data = package()
        release = {"draft": False, "prerelease": False, "published_at": "2026-11-01T00:00:00Z",
                   "assets": [{"name": "winshun.capture-1.0.0.wsplugin", "digest": "sha256:" + hashlib.sha256(data).hexdigest()}]}
        url = f"https://github.com/{repo}/releases/download/winshun.capture-v1.0.0/winshun.capture-1.0.0.wsplugin"
        with patch.object(registry, "fetch", return_value=data):
            return check.check_asset(url, release=release)

    def test_official_asset_is_accepted(self):
        self.assertEqual(self.asset(registry.REPO).errors, [])

    def test_same_id_from_another_repo_stays_rejected(self):
        self.assertTrue(self.asset("attacker/WinShun-plugins").errors)

    def test_manifest_name_does_not_grant_an_exception(self):
        self.assertTrue(check.check_package(package(), "winshun.capture", "1.0.0", "fixture").errors)

    def test_only_named_binaries_are_allowed(self):
        for name in ["Qt6Core.dll", "extra.exe", "start.cmd", "driver.sys"]:
            with self.subTest(name=name):
                self.assertTrue(check.check_package(package({name: b"payload"}), "winshun.capture", "1.0.0", "fixture", official_native=True).errors)

    def test_wrong_entry_program_is_rejected(self):
        self.assertTrue(check.check_package(package(program="other.exe"), "winshun.capture", "1.0.0", "fixture", official_native=True).errors)

    def test_native_exception_does_not_bypass_path_validation(self):
        self.assertTrue(check.check_package(package({"../escape.exe": b"payload"}), "winshun.capture", "1.0.0", "fixture", official_native=True).errors)

    def test_native_file_limit_still_applies(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with (folder / "WinShunCapture.exe").open("wb") as stream:
                stream.truncate(registry.MAX_PACKAGE + 1)
            result = check.Result(folder, "fixture")
            check.check_files(result, folder, True, ("WinShunCapture.exe",))
            self.assertTrue(result.errors)

    def test_invalid_identity_never_grants_native_access(self):
        for repo, plugin_id in [(None, "winshun.capture"), (registry.REPO, []), (registry.REPO, "other.native")]:
            self.assertFalse(registry.official_native(repo, plugin_id))


if __name__ == "__main__":
    unittest.main()
