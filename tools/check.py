"""Reproducible local checks; never connects to a physical adapter."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    commands = [
        [sys.executable, "-m", "ruff", "check", "renmon", "tools", "packaging"],
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "renmon",
            "tools",
            "packaging",
            "tests",
        ],
        ["npm.cmd" if sys.platform == "win32" else "npm", "run", "check"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
    ]
    if sys.platform != "win32":
        commands += [
            [sys.executable, str(path)]
            for path in (
                ROOT / "tests/test_end_to_end.py",
                ROOT / "tests/test_probe.py",
            )
        ]
    for command in commands:
        print(" ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
