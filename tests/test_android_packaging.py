"""The APK path scrubber must preserve executable bytecode and archive integrity."""

import importlib.util
import io
import marshal
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "android_privacy",
    Path(__file__).resolve().parents[1] / "packaging/android/privacy.py",
)
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


class AndroidPackagingTests(unittest.TestCase):
    def test_bytecode_remains_valid_and_preserves_semantics(self):
        prefix = b"/Users/private-builder"
        code = compile("answer = 42", prefix.decode() + "/app/main.py", "exec")
        original = marshal.dumps(code)
        clean = privacy.scrub(original, prefix)
        self.assertEqual(len(clean), len(original))
        self.assertNotIn(prefix, clean)
        restored = marshal.loads(clean)
        namespace = {}
        exec(restored, namespace)
        self.assertEqual(namespace["answer"], 42)
        self.assertTrue(restored.co_filename.startswith("/build"))

    def test_nested_archive_crc_remains_valid(self):
        prefix = b"/Users/private-builder"
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("module", b"trace=" + prefix + b"/app/module.py")
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("stdlib.zip", inner.getvalue())
        with zipfile.ZipFile(
            io.BytesIO(privacy.scrub(outer.getvalue(), prefix))
        ) as archive:
            self.assertIsNone(archive.testzip())
            with zipfile.ZipFile(io.BytesIO(archive.read("stdlib.zip"))) as nested:
                self.assertIsNone(nested.testzip())
                self.assertNotIn(prefix, nested.read("module"))
