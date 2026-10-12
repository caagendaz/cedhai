from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from cedhai.cloud_setup import extract_engine
from cedhai.run_bridge import java_classpath, java_tools


class CloudSetupTests(unittest.TestCase):
    def test_platform_java_paths_and_classpath(self):
        with patch("cedhai.run_bridge.os.pathsep", ":"):
            java, javac = java_tools(Path("jdk"), platform="posix")
            self.assertEqual(java.name, "java")
            self.assertEqual(javac.name, "javac")
            self.assertEqual(java_classpath(Path("classes"), "lib/*"), "classes:lib/*")
        java, _ = java_tools(Path("jdk"), platform="nt")
        self.assertEqual(java.name, "java.exe")

    def test_engine_extraction_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "engine.zip"
            with zipfile.ZipFile(archive, "w") as writer:
                writer.writestr("xmage/lib/test.jar", b"test")
            extract_engine(archive, root / "good")
            self.assertEqual((root / "good/xmage/lib/test.jar").read_bytes(), b"test")
            with zipfile.ZipFile(archive, "w") as writer:
                writer.writestr("xmage/../../escape", b"bad")
            with self.assertRaises(ValueError):
                extract_engine(archive, root / "bad")
