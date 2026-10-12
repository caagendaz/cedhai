"""Install the pinned XMage distribution and a Java 21 compiler in Colab/Linux."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import urllib.request
import zipfile

from .run_bridge import ROOT

URL = "https://github.com/WillWroble/MageZero/releases/download/v0.2.0-alpha/magezero-xmage-v0.2.0-alpha.zip"
SHA256 = "c0242f186c312db81d0240d1e7479ce0f4306523ebec11d92d616a4f289926a3"


def extract_engine(archive: Path, target: Path):
    with zipfile.ZipFile(archive) as reader:
        for item in reader.infolist():
            parts = PurePosixPath(item.filename).parts
            if not parts or parts[0] != "xmage" or ".." in parts or "\\" in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Unsafe engine archive entry")
            path = target.joinpath(*parts)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with reader.open(item) as source, path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)


def find_java21():
    candidates = list(Path("/usr/lib/jvm").glob("*21*"))
    compiler = shutil.which("javac")
    if compiler:
        candidates.append(Path(compiler).resolve().parents[1])
    for path in candidates:
        if (path / "bin/javac").exists():
            version = subprocess.check_output([str(path / "bin/java"), "-version"], stderr=subprocess.STDOUT, text=True)
            if re.search(r'version "21[.\"]', version):
                return path.resolve()
    return None


def setup():
    if os.name != "posix":
        raise ValueError("Cloud setup requires Colab/Linux; use install_bridge.ps1 on Windows")
    jdk = find_java21()
    if jdk is None:
        subprocess.run(["apt-get", "update", "-qq"], check=True)
        subprocess.run(["apt-get", "install", "-y", "-qq", "openjdk-21-jdk-headless"], check=True,
                       env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"})
        jdk = find_java21()
    if jdk is None:
        raise ValueError("Java 21 JDK was not installed")
    link = ROOT / "tools/jdk/jdk-colab"
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(jdk, target_is_directory=True)
    downloads = ROOT / "tools/downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / "magezero-xmage-v0.2.0-alpha.zip"
    if not archive.exists():
        temporary = archive.with_suffix(".partial")
        request = urllib.request.Request(URL, headers={"User-Agent": "cedhai-research/0.1"})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as writer:
            shutil.copyfileobj(response, writer)
        temporary.replace(archive)
    digest = hashlib.sha256()
    with archive.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError("Pinned engine download checksum mismatch")
    engine = ROOT / "tools/magezero"
    if not (engine / "xmage/lib/mage-1.4.58.jar").exists():
        extract_engine(archive, engine)
    print(json.dumps({"jdk": str(jdk), "engine": str(engine / "xmage"), "archive_sha256": SHA256}, indent=2))


if __name__ == "__main__":
    setup()
