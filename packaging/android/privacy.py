"""Remove host home-directory build prefixes before APK signing.

Native/bytecode replacements preserve byte lengths and binary offsets. ZIP and
TAR containers are rebuilt so their checksums and sizes remain correct. This
only maps the build host's absolute home prefix, never arbitrary user text.
"""

import gzip
import io
import tarfile
import zipfile
from pathlib import Path


def scrub(data, prefix):
    replacement = b"/build".ljust(len(prefix), b"_")
    if len(replacement) != len(prefix):
        raise ValueError("Build prefix is too short")
    if data.startswith(b"PK\x03\x04"):
        output = io.BytesIO()
        with (
            zipfile.ZipFile(io.BytesIO(data)) as source,
            zipfile.ZipFile(output, "w") as target,
        ):
            for entry in source.infolist():
                target.writestr(entry, scrub(source.read(entry), prefix))
        return output.getvalue()
    if data.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(data)
        # p4a private.tar is gzip-compressed despite its filename.
        if len(raw) > 262 and raw[257:262] == b"ustar":
            output = io.BytesIO()
            with (
                tarfile.open(fileobj=io.BytesIO(raw)) as source,
                tarfile.open(fileobj=output, mode="w") as target,
            ):
                for entry in source:
                    entry.uid = entry.gid = 0
                    entry.uname = entry.gname = ""
                    if entry.isfile():
                        content = scrub(source.extractfile(entry).read(), prefix)
                        entry.size = len(content)
                        target.addfile(entry, io.BytesIO(content))
                    else:
                        target.addfile(entry)
            return gzip.compress(output.getvalue(), mtime=0)
        return gzip.compress(scrub(raw, prefix), mtime=0)
    return data.replace(prefix, replacement)


def before_apk_assemble(toolchain):
    dist = Path(toolchain._dist.dist_dir)
    prefix = str(Path.home()).encode()
    for directory in (dist / "src/main/assets", dist / "libs"):
        for path in directory.rglob("*"):
            if path.is_file():
                original = path.read_bytes()
                clean = scrub(original, prefix)
                if clean != original:
                    path.write_bytes(clean)
