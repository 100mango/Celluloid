#!/usr/bin/env python3
"""Check our literal Bash run blocks without executing tools or installing YAML packages."""
from pathlib import Path
import re
import subprocess
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run_blocks(source):
    lines = source.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r'(\s*)run:\s*\|[-+]?\s*', line)
        if not match:
            if re.match(r'\s*run:', line):
                raise ValueError('Every native workflow run must use an auditable literal block')
            continue
        indent = len(match.group(1))
        end = index + 1
        while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > indent):
            end += 1
        yield index + 1, textwrap.dedent('\n'.join(lines[index + 1:end])) + '\n'


class NativeWorkflowSyntaxTests(unittest.TestCase):
    def test_every_native_shell_block_parses(self):
        workflow = ROOT / '.github/workflows/apple-platforms.yml'
        blocks = list(run_blocks(workflow.read_text()))
        self.assertGreaterEqual(len(blocks), 10)
        for line, body in blocks:
            with self.subTest(line=line):
                result = subprocess.run(['bash', '-n'], input=body, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, f'{workflow.name}:{line}\n{result.stderr}')

    def test_missing_tee_quote_is_rejected_without_execution(self):
        fixture = 'steps:\n  - name: Build\n    run: |\n      set -euo pipefail\n      echo test | tee "$RUNNER_TEMP/tv-build.log\n  - name: Next\n    uses: owner/action@sha\n'
        blocks = list(run_blocks(fixture))
        self.assertEqual(len(blocks), 1)
        result = subprocess.run(['bash', '-n'], input=blocks[0][1], text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unexpected EOF', result.stderr)


if __name__ == '__main__':
    unittest.main()
