"""Sign a test APK with a persistent project-only certificate (CN=Renmon)."""

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path


def main():
    source = Path(sys.argv[1]).resolve()
    match = re.fullmatch(r"renmon-([0-9.]+)-arm64-v8a-debug\.apk", source.name)
    if not match:
        raise SystemExit("Expected a Buildozer arm64 debug APK")
    output = source.with_name(f"Renmon-{match[1]}-android-arm64.apk")
    if source == output:
        raise SystemExit("Specify the Buildozer debug APK as input")
    java = Path(os.environ["JAVA_HOME"]) / "bin/keytool"
    sdk = Path.home() / ".buildozer/android/platform/android-sdk"
    signers = sorted((sdk / "build-tools").glob("*/apksigner"))
    if not signers:
        raise SystemExit("Android build-tools are missing")
    keys = Path.home() / ".config/renmon/android-signing"
    keys.mkdir(parents=True, exist_ok=True, mode=0o700)
    keys.chmod(0o700)
    password = keys / "keystore-password"
    keystore = keys / "renmon-test.jks"
    if keystore.exists() and not password.exists():
        raise SystemExit(
            "Keystore password file is missing; refusing to replace the key"
        )
    if not password.exists():
        fd = os.open(password, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(secrets.token_urlsafe(32))
    if not keystore.exists():
        subprocess.run(
            [
                str(java),
                "-genkeypair",
                "-keystore",
                str(keystore),
                "-storepass:file",
                str(password),
                "-keypass:file",
                str(password),
                "-alias",
                "renmon",
                "-dname",
                "CN=Renmon",
                "-keyalg",
                "RSA",
                "-keysize",
                "3072",
                "-validity",
                "10000",
            ],
            check=True,
        )
        keystore.chmod(0o600)
    subprocess.run(
        [
            str(signers[-1]),
            "sign",
            "--ks",
            str(keystore),
            "--ks-key-alias",
            "renmon",
            "--ks-pass",
            f"file:{password}",
            "--out",
            str(output),
            str(source),
        ],
        check=True,
    )
    subprocess.run(
        [str(signers[-1]), "verify", "--print-certs", str(output)], check=True
    )
    print(output)


if __name__ == "__main__":
    main()
