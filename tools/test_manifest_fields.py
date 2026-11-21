"""plugin.json 的 translate（顶层）和 run.suggest（program 型 run）：照 Win顺 的 Manifest.cpp 检查。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check


def manifest(**top):
    """一个带 runtime 的有效清单：ask 由插件自己的程序回答，open 是零代码的 program 命令。"""
    m = {"manifest": 1, "id": "me.fixture", "name": "Fixture", "version": "1.0.0",
         "runtime": {"mode": "once", "program": "python"},
         "commands": [{"id": "ask", "keyword": "ask"},
                      {"id": "open", "keyword": "open", "run": {"program": "notepad.exe", "args": "%s"}}]}
    m.update(top)
    return m


def errors(m):
    e = check.Errors()
    check.validate_manifest(m, e)
    return e.items


def with_run(**run):
    m = manifest()
    m["commands"][1]["run"] = {"program": "notepad.exe", **run}
    return m


class Translate(unittest.TestCase):
    def test_a_command_of_the_plugin_itself_is_accepted(self):
        self.assertEqual(errors(manifest(translate="ask")), [])
        self.assertEqual(errors(manifest()), [])  # 可以不写
        self.assertEqual(errors(manifest(translate=None)), [])
        self.assertIn("translate", check.KNOWN_TOP)

    def test_it_must_name_one_of_the_commands(self):
        for value in ("nope", "", 5, True, ["ask"], {"id": "ask"}):
            with self.subTest(translate=value):
                self.assertEqual(errors(manifest(translate=value)), ["translate 要写 commands 里一个命令的 id"])

    def test_a_zero_code_command_cannot_answer_it(self):
        self.assertEqual(errors(manifest(translate="open")), ["translate 的命令要由插件自己的程序回答，不能是零代码命令"])


class Suggest(unittest.TestCase):
    def test_each_kind_with_a_placeholder_is_accepted(self):
        for kind in ("files", "folders", "paths"):
            with self.subTest(suggest=kind):
                self.assertEqual(errors(with_run(suggest=kind, args='--open "%s"')), [])
        self.assertEqual(errors(with_run(args="%s")), [])  # 不写 suggest 照旧
        self.assertEqual(errors(with_run(suggest=None, args="x")), [])

    def test_the_kind_must_be_files_folders_or_paths(self):
        for kind in ("file", "Files", "", 1, True, ["files"]):
            with self.subTest(suggest=kind):
                self.assertEqual(errors(with_run(suggest=kind, args="%s")),
                                 ["commands[1].run.suggest 要是 files、folders 或 paths"])

    def test_args_must_have_the_placeholder(self):
        for run in ({"suggest": "files"}, {"suggest": "paths", "args": ""}, {"suggest": "folders", "args": "--open"}):
            with self.subTest(run=run):
                self.assertEqual(errors(with_run(**run)), ["commands[1].run.suggest 要 args 里有 %s，选中的路径填在那里"])


def with_number(**fields):
    return manifest(settings=[{"key": "n", "type": "number", "title": "N", **fields}])


class NumberRange(unittest.TestCase):
    """number 设置的 min、max、step、unit（LingCore/WinShun#359）。"""

    def test_a_range_is_accepted(self):
        for fields in ({}, {"min": 0, "max": 100}, {"min": 0.5, "max": 2, "step": 0.1, "unit": "秒", "default": 1},
                       {"min": 10}, {"max": 10, "step": 5}, {"min": 0, "max": 1}):
            with self.subTest(fields=fields):
                self.assertEqual(errors(with_number(**fields)), [])

    def test_bad_ranges_are_refused(self):
        cases = [({"min": "0", "max": 5}, "settings[0].min 要是数字"),
                 ({"min": 6, "max": 5, "step": 0.5}, "settings[0].min 要小于 max"),
                 ({"step": 0}, "settings[0].step 要大于 0"),
                 ({"min": 0, "max": 0.5}, "settings[0].step 不能大于 max − min（不写 step 时是 1）"),
                 ({"min": 0, "max": 10, "default": "3"}, "settings[0].default 要是数字")]
        for fields, message in cases:
            with self.subTest(fields=fields):
                self.assertEqual(errors(with_number(**fields))[:1], [message])

    def test_other_types_ignore_them(self):
        m = manifest(settings=[{"key": "t", "type": "text", "title": "T", "min": "x"}])
        self.assertEqual(errors(m), [])


if __name__ == "__main__":
    unittest.main()


def with_setting(**setting):
    return manifest(settings=[{"key": "k", "title": "K", **setting}])


class SettingFields(unittest.TestCase):
    def test_multiline_is_for_text(self):
        self.assertEqual(errors(with_setting(type="text", multiline=True)), [])
        self.assertEqual(errors(with_setting(type="bool", multiline=False)), [])
        self.assertEqual(errors(with_setting(type="bool", multiline=True)), ["settings[0].multiline 只用于 text"])
        self.assertEqual(errors(with_setting(type="text", multiline=1)), ["settings[0].multiline 要是 true 或 false"])

    def test_hidden_is_for_values_the_plugin_can_set(self):
        for kind in ("text", "number", "bool", "choice"):
            with self.subTest(type=kind):
                self.assertEqual(errors(with_setting(type=kind, hidden=True)), [])
        for kind in ("password", "folder", "file", "hotkey"):
            with self.subTest(type=kind):
                self.assertEqual(errors(with_setting(type=kind, hidden=True)), ["settings[0].hidden 只用于 text、number、bool、choice"])
                self.assertEqual(errors(with_setting(type=kind, hidden=False)), [])
        self.assertEqual(errors(with_setting(type="text", hidden="true")), ["settings[0].hidden 要是 true 或 false"])


class Permissions(unittest.TestCase):
    def test_system_power_is_known(self):
        self.assertEqual(errors(manifest(permissions=["ui", "system:power"])), [])
        self.assertIn("system:power", check.PERMISSIONS)
        self.assertIn("system:power", check.RISKY)

    def test_selection_read_is_known_and_last(self):
        self.assertEqual(errors(manifest(permissions=["ui", "selection:read"])), [])
        self.assertEqual(check.PERMISSIONS[-1], "selection:read")
        self.assertIn("selection:read", check.RISKY)
