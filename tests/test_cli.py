import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from morice import __version__
from morice import cli


class CliEntryPointTests(unittest.TestCase):
    def test_help_exits_without_starting_interactive_chat(self):
        output = io.StringIO()
        with patch.object(cli, "run_cli") as run_cli, redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Run MORICE in an interactive local terminal.", output.getvalue())
        run_cli.assert_not_called()

    def test_version_exits_without_starting_interactive_chat(self):
        output = io.StringIO()
        with patch.object(cli, "run_cli") as run_cli, redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn(__version__, output.getvalue())
        run_cli.assert_not_called()

    def test_no_arguments_starts_interactive_chat(self):
        with patch.object(cli, "run_cli") as run_cli:
            self.assertEqual(cli.main([]), 0)
        run_cli.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
