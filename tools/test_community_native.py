"""Native packages are labelled unreviewed, bounded and never silently trusted."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check
import registry
import index
import update


def package(extra=None, **manifest_changes):
    manifest = {"manifest": 1, "id": "community.native", "name": "Native", "version": "1.0.0",
                "description": "Native fixture", "author": "Community", "license": "MIT", "minWinShun": "0.22.0",
                "runtime": {"mode": "once", "program": "bin/tool.exe", "qt": "host", "qtVersion": "6.12"},
                "commands": [{"id": "go", "keyword": "native"}]}
    manifest.update(manifest_changes)
    files = {"plugin.json": json.dumps(manifest).encode(), "README.md": b"Open source native plugin.",
             "bin/tool.exe": b"MZfixture", "bin/helper.dll": b"MZfixture"}
    files.update(extra or {})
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return result.getvalue()


def inspect(data, **options):
    return check.check_package(data, "community.native", "1.0.0", "fixture", **options)


def entry():
    return {**inspect(package(), unreviewed_native=True).fields, "id": "community.native", "repo": "Community/Native",
            "review": "unreviewed-native", "autoUpdate": True, "bundled": False, "hosted": False,
            "url": "https://github.com/Community/Native/releases/download/v1.0.0/community.native-1.0.0.wsplugin",
            "releaseDate": "2026-11-06T00:00:00Z", "dateAdded": "2026-11-06T00:00:00Z"}


class CommunityNative(unittest.TestCase):
    def test_explicit_category_required(self):
        self.assertTrue(inspect(package()).errors)
        accepted = inspect(package(), unreviewed_native=True)
        self.assertEqual(accepted.errors, [])
        self.assertTrue(accepted.warnings)

    def test_bad_entry_and_old_client_rejected(self):
        for change in ({"minWinShun": "0.21.0"}, {"minWinShun": ""},
                       {"runtime": {"mode": "once", "program": "../escape.exe"}},
                       {"runtime": {"mode": "once", "program": "absent.exe"}},
                       {"runtime": {"mode": "once", "program": "start.cmd"}},
                       {"permissions": ["elevated"]}):
            with self.subTest(change=change):
                self.assertTrue(inspect(package(**change), unreviewed_native=True).errors)

    def test_other_binary_types_and_path_traversal_stay_rejected(self):
        for name in ("../escape.dll", "/absolute.exe", "driver.sys", "start.cmd", "encoded.pyc"):
            with self.subTest(name=name):
                self.assertTrue(inspect(package({name: b"payload"}), unreviewed_native=True).errors)

    def test_size_limit_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with (folder / "huge.dll").open("wb") as file:
                file.truncate(registry.MAX_PACKAGE + 1)
            result = check.Result(folder)
            check.check_files(result, folder, True, unreviewed_native=True)
            self.assertTrue(result.errors)

    def test_entry_and_index_keep_review(self):
        e = entry()
        with tempfile.TemporaryDirectory() as tmp:
            report = check.Report(e["id"])
            check.check_entry_fields(report, e, Path(tmp))
            self.assertEqual(report.errors, [])
            self.assertEqual(index.item_of(e)["review"], "unreviewed-native")
            legacy = dict(e, id="community.legacy", repo=registry.REPO, hosted=True)
            legacy.pop("review")
            self.assertEqual(index.item_of(legacy)["review"], "reviewed")
            for fake_review in ("reviewed", "official", True):
                invalid = dict(e, review=fake_review)
                report = check.Report(e["id"])
                check.check_entry_fields(report, invalid, Path(tmp))
                self.assertTrue(report.errors)
            report = check.Report(e["id"])
            check.check_entry_fields(report, dict(e, runtime={"mode": "once", "program": []}), Path(tmp))
            self.assertTrue(report.errors)

    def test_release_download_still_checks_digest(self):
        data = package()
        release = {"draft": False, "prerelease": False, "published_at": "2026-11-06T00:00:00Z",
                   "assets": [{"name": "community.native-1.0.0.wsplugin", "digest": "sha256:" + hashlib.sha256(data).hexdigest()}]}
        with patch.object(registry, "fetch", return_value=data):
            accepted = check.check_asset(entry()["url"], release=release, unreviewed_native=True)
            self.assertEqual(accepted.errors, [])
            release["assets"][0]["digest"] = "sha256:" + "0" * 64
            self.assertTrue(check.check_asset(entry()["url"], release=release, unreviewed_native=True).errors)

    def test_review_cannot_disappear_in_author_pr(self):
        e = entry()
        report = check.Report(e["id"])
        report.old = e
        report.entry = {k: v for k, v in e.items() if k != "review"}
        with patch.object(check, "check_entry_online", return_value=None):
            check.check_pr_entry(report)
        self.assertTrue(any("review" in error for error in report.errors))

    def release_of(self, data):
        return {"draft": False, "prerelease": False, "published_at": "2026-11-06T00:00:00Z",
                "assets": [{"name": "community.native-1.0.0.wsplugin", "digest": "sha256:" + hashlib.sha256(data).hexdigest()}]}

    def test_registry_update_accepts_native_release_keeping_its_label(self):
        # Win顺 asks the user before installing or updating it: the library only checks it.
        e = entry()
        data = package()
        release = self.release_of(data)
        with patch.object(registry, "fetch", return_value=data), patch.object(registry, "release_by_tag", return_value=release):
            action, finding, accepted = update.look(e, "1.0.0", release, {"browser_download_url": e["url"]})
        self.assertIsNone(finding)
        self.assertEqual(accepted["review"], "unreviewed-native")

    def test_script_plugin_turning_native_is_labelled_not_refused(self):
        e = {k: v for k, v in entry().items() if k != "review"}
        data = package()
        release = self.release_of(data)
        with patch.object(registry, "fetch", return_value=data), patch.object(registry, "release_by_tag", return_value=release):
            action, finding, accepted = update.look(e, "1.0.0", release, {"browser_download_url": e["url"]})
        self.assertIsNone(finding)
        self.assertEqual(accepted["review"], "unreviewed-native")

    def test_native_is_told_by_its_files(self):
        self.assertTrue(check.looks_native(package()))
        self.assertTrue(check.looks_native(package(extra={"bin/tool.exe": b"MZ"}, runtime={"mode": "once", "program": "python"})))
        script = io.BytesIO()
        with zipfile.ZipFile(script, "w") as archive:
            archive.writestr("plugin.json", json.dumps({"id": "a.b", "runtime": {"mode": "once", "program": "python"}}))
            archive.writestr("main.py", "print(1)")
        self.assertFalse(check.looks_native(script.getvalue()))
        self.assertFalse(check.looks_native(b"not a zip"))

    def test_entry_of_native_package_needs_the_label(self):
        e = entry()
        data = package()
        report = check.Report(e["id"])
        report.entry = {k: v for k, v in e.items() if k != "review"}
        with patch.object(registry, "fetch", return_value=data), patch.object(registry, "release_by_tag", return_value=self.release_of(data)):
            check.check_entry_online(report)
        self.assertTrue(any("unreviewed-native" in error for error in report.errors))
        report = check.Report(e["id"])
        report.entry = e
        with patch.object(registry, "fetch", return_value=data), patch.object(registry, "release_by_tag", return_value=self.release_of(data)):
            check.check_entry_online(report)
        self.assertEqual(report.errors, [])


if __name__ == "__main__":
    unittest.main()
