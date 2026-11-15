"""Run on the target OS: python packaging/build_portable.py."""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform not in ("darwin", "win32"):
        raise SystemExit(
            "Build on macOS or Windows; cross-compilation is not supported."
        )
    subprocess.run(
        ["npm.cmd" if sys.platform == "win32" else "npm", "run", "build"],
        cwd=ROOT,
        check=True,
    )
    name = "macOS" if sys.platform == "darwin" else "Windows"
    output = ROOT / "dist" / f"Renmon-{name}-{platform.machine()}"
    output.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "Renmon",
        "--distpath",
        str(output),
        "--workpath",
        str(ROOT / "build" / name),
        "--specpath",
        str(ROOT / "build"),
        "--paths",
        str(ROOT),
        "--add-data",
        f"{ROOT / 'renmon/static'}:renmon/static",
        "--add-data",
        f"{ROOT / 'renmon/ui.bundle.js'}:renmon",
        "--exclude-module",
        "PyQt5",
        "--exclude-module",
        "PyQt6",
        "--exclude-module",
        "PySide2",
        "--exclude-module",
        "PySide6",
    ]
    if sys.platform == "darwin":
        helper = ROOT / "renmon/native/bluetooth-connect"
        subprocess.run(
            [
                "xcrun",
                "swiftc",
                str(helper.with_name("bluetooth.swift")),
                "-o",
                str(helper),
            ],
            check=True,
        )
        cmd.extend(
            [
                "--osx-bundle-identifier",
                "local.renmon.desktop",
                "--add-binary",
                f"{helper}:renmon/native",
            ]
        )
    cmd.append(str(ROOT / "packaging/desktop_entry.py"))
    subprocess.run(cmd, cwd=ROOT, check=True)
    # macOS: .app plus adjacent profiles; Windows: exe + _internal plus profiles.
    portable = output if sys.platform == "darwin" else output / "Renmon"
    shutil.copytree(ROOT / "profiles", portable / "profiles", dirs_exist_ok=True)
    shutil.copy2(ROOT / "PORTABLE-UA.txt", portable / "PORTABLE-UA.txt")
    shutil.copytree(ROOT / "docs", portable / "docs", dirs_exist_ok=True)
    if sys.platform == "darwin":
        # COLLECT output is redundant once PyInstaller has built the .app bundle.
        shutil.rmtree(output / "Renmon")
    print(f"Portable folder: {portable}")


if __name__ == "__main__":
    main()
