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
import index


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

    def test_ocr_search_allows_only_its_official_binaries(self):
        manifest = {
            "manifest": 1, "id": "winshun.ocr-search", "name": "Image text search", "version": "1.0.0",
            "author": "LingCore", "license": "MIT", "description": "Search images",
            "runtime": {"mode": "resident", "program": "WinShunOcrSearch.exe"},
            "commands": [{"id": "find", "keyword": "ocr", "contentSearch": True}],
        }
        files = {"plugin.json": json.dumps(manifest).encode(), "README.md": b"Offline image text search.",
                 "WinShunOcrSearch.exe": b"MZfixture", "WinShunOcrSearchApp.dll": b"MZfixture"}
        def archive():
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as z:
                for name, data in files.items():
                    z.writestr(name, data)
            return output.getvalue()
        self.assertEqual(check.check_package(archive(), manifest["id"], "1.0.0", "fixture", official_native=True).errors, [])
        self.assertTrue(check.check_package(archive(), manifest["id"], "1.0.0", "fixture").errors)
        files["extra.exe"] = b"MZfixture"
        self.assertTrue(check.check_package(archive(), manifest["id"], "1.0.0", "fixture", official_native=True).errors)


class ManifestPolicy(unittest.TestCase):
    def manifest(self):
        return {"manifest": 1, "id": "winshun.web", "name": "Web search", "version": "2.0.0",
                "webSearch": True, "commands": []}

    def errors(self, manifest):
        errors = check.Errors()
        check.validate_manifest(manifest, errors)
        return errors.items

    def test_web_search_has_no_static_commands_or_process(self):
        self.assertEqual(self.errors(self.manifest()), [])
        for changes in [{"id": "other.web"}, {"webSearch": "true"}, {"webSearch": False},
                        {"runtime": {"mode": "resident", "program": "python"}},
                        {"commands": [{"id": "url", "run": {"url": "https://example.com"}}]}]:
            with self.subTest(changes=changes):
                self.assertTrue(self.errors(self.manifest() | changes))

    def test_content_search_requires_a_process_and_boolean(self):
        manifest = self.manifest() | {"id": "author.search", "webSearch": False,
                                     "runtime": {"mode": "resident", "program": "python"},
                                     "commands": [{"id": "find", "contentSearch": True}]}
        self.assertEqual(self.errors(manifest), [])
        self.assertTrue(self.errors(manifest | {"runtime": None}))
        manifest["commands"][0]["contentSearch"] = "true"
        self.assertTrue(self.errors(manifest))

    def test_web_source_preserves_the_bundled_sample_link(self):
        entry = {"repo": registry.REPO, "id": "winshun.web"}
        self.assertTrue(index.source_of(entry).endswith("src/web-plugin"))
        self.assertTrue(index.source_of(entry | {"bundled": True}).endswith("plugins/winshun.web"))


if __name__ == "__main__":
    unittest.main()
