"""Stage only application assets for Android; never include local logs or keys."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "packaging/android/app"


def main():
    from importlib.util import find_spec

    subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    for name in ("renmon", "profiles"):
        shutil.copytree(
            ROOT / name,
            DEST / name,
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "native", ".DS_Store"
            ),
        )
    shutil.copy2(ROOT / "packaging/android/main.py", DEST / "main.py")
    webview = find_spec("webview")
    if webview is None:
        raise SystemExit("Install pywebview==6.2.1 in the build environment first")
    jar = Path(webview.origin).parent / "lib/pywebview-android.jar"
    vendor = DEST.parent / "vendor"
    vendor.mkdir(exist_ok=True)
    shutil.copy2(jar, vendor / jar.name)
    print(f"Android source staged: {DEST}")


if __name__ == "__main__":
    main()
