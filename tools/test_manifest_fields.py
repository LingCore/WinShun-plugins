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


if __name__ == "__main__":
    unittest.main()
