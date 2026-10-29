"""Check both modes through the entry point actually configured by Docker."""

import json
import runpy
import sys
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def docker_main():
    command = next(line[4:] for line in (ROOT / "Dockerfile").read_text().splitlines()
                   if line.startswith("CMD "))
    entrypoint = ROOT / PurePosixPath(json.loads(command)[1]).relative_to("/app")
    return runpy.run_path(str(entrypoint))["main"]


class DockerStartupTests(unittest.TestCase):
    def test_web_starts_both_services_and_stops_when_one_exits(self):
        child = Mock()
        child.poll.return_value = 7
        with patch.dict("os.environ", {"NEURON_MODE": "web"}, clear=True), \
                patch("sys.argv", ["start.py"]), \
                patch("runner.run", side_effect=AssertionError("web mode reached arena runner")), \
                patch("signal.signal"), patch("subprocess.Popen", return_value=child) as spawn:
            self.assertEqual(docker_main()(), 7)
        self.assertEqual(spawn.call_count, 2)
        backend, frontend = spawn.call_args_list
        self.assertIn("uvicorn", backend.args[0])
        self.assertEqual(backend.kwargs["cwd"], ROOT / "backend")
        self.assertEqual(frontend.args[0], ["node", "server.js"])
        self.assertEqual(frontend.kwargs["cwd"], ROOT / "frontend")
        self.assertEqual(frontend.kwargs["env"]["PORT"], "3000")

    def test_default_arena_uses_mounted_paths_and_honors_overrides(self):
        for overrides in ({}, {"ARENA_INPUT": "/custom/in.csv", "ARENA_LEXICON": "/custom/lex.json",
                               "ARENA_OUTPUT": "/custom/out.csv"}):
            with self.subTest(overrides=overrides), \
                    patch.dict("os.environ", overrides, clear=True), \
                    patch("sys.argv", ["start.py"]), \
                    patch("runner.run", side_effect=AssertionError("arena launcher skipped exec")), \
                    patch("os.execv", side_effect=SystemExit(0)) as execute:
                with self.assertRaises(SystemExit) as stopped:
                    docker_main()()
                self.assertEqual(stopped.exception.code, 0)
            execute.assert_called_once_with(sys.executable, [
                sys.executable, str(ROOT / "runner.py"),
                "--universe", overrides.get("ARENA_INPUT", "/universe/universe.csv"),
                "--lexicon", overrides.get("ARENA_LEXICON", "/universe/lexicon.json"),
                "--output", overrides.get("ARENA_OUTPUT", "/output/output.csv"),
            ])


if __name__ == "__main__":
    unittest.main()
