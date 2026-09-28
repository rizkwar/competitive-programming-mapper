import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from Helper import run


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        field = self.root / "Main-Field"
        field.mkdir()
        self.source = field / "A.cpp"
        self.source.write_text(
            "#include <iostream>\nint main() { long long a, b; "
            "std::cin >> a >> b; std::cout << a + b << '\\n'; }\n",
            encoding="utf-8",
        )
        self.samples = self.root / "Problem" / "Practice" / "addition" / "samples"
        self.samples.mkdir(parents=True)
        (self.samples / "1.in").write_text("2 3\n", encoding="utf-8")
        (self.samples / "1.out").write_text("5\n", encoding="utf-8")
        root_patch = patch.object(run, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    @unittest.skipUnless(shutil.which("g++"), "g++ is required for the integration test")
    def test_compiles_and_reports_pass_or_wrong_answer(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(run.run_samples("A", "addition"), 0)
        self.assertIn("PASS 1.in", output.getvalue())

        (self.samples / "1.out").write_text("6\n", encoding="utf-8")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(run.run_samples("A", "addition"), 1)
        self.assertIn("WRONG ANSWER 1.in", output.getvalue())
        self.assertIn("Actual:\n5", output.getvalue())

    @unittest.skipUnless(shutil.which("g++"), "g++ is required for the integration test")
    def test_compilation_error_does_not_run_samples(self) -> None:
        self.source.write_text("int main( {\n", encoding="utf-8")
        error = StringIO()
        with redirect_stdout(StringIO()), redirect_stderr(error):
            self.assertEqual(run.run_samples("A", "addition"), 1)
        self.assertIn("Compilation failed", error.getvalue())

    def test_rejects_missing_samples_and_path_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "without a path"):
            run.run_samples("A", "../addition")
        (self.samples / "1.in").unlink()
        with self.assertRaisesRegex(ValueError, "No sample inputs"):
            run.run_samples("A", "addition")


if __name__ == "__main__":
    unittest.main()
