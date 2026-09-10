#!/usr/bin/env python3
"""Build the DoltLite image from the pinned release packages.

  python3 scripts/lite_image.py

DoltLite ships no container image, so this repository builds one: docker/doltlite/Dockerfile over
the two Debian packages of one release, downloaded from the GitHub release and checked against
the sha256 recorded here before anything is built. The pin is deliberate -- DoltLite is a beta
with near-daily releases -- and changing it means changing the version, the URLs and the
checksums together, then re-running the loads.
"""
import hashlib, os, subprocess, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pairs import LITE_IMAGE, LITE_PACKAGES, LITE_VERSION, ROOT  # noqa: E402

WORK = os.path.join(ROOT, "build", "doltlite")


def fetch(name, url, sha256):
    path = os.path.join(WORK, name)
    if not os.path.exists(path):
        print(f"  . downloading {name}", flush=True)
        with urllib.request.urlopen(url, timeout=300) as r, open(path + ".part", "wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(path + ".part", path)
    got = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if got != sha256:
        os.remove(path)
        sys.exit(f"{name}: sha256 {got} is not the recorded {sha256}; removed it. "
                 f"The release may have changed under the pin -- check before recording a new value.")
    print(f"  . {name} {os.path.getsize(path):,} bytes, sha256 verified", flush=True)


def main():
    os.makedirs(WORK, exist_ok=True)
    for name, url, sha in LITE_PACKAGES:
        fetch(name, url, sha)
    print(f"  . building {LITE_IMAGE} (DoltLite {LITE_VERSION})", flush=True)
    p = subprocess.run(["docker", "build", "-q", "-f", os.path.join(ROOT, "docker", "doltlite", "Dockerfile"),
                        "-t", LITE_IMAGE, WORK], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(p.stderr or p.stdout)
    v = subprocess.run(["docker", "run", "--rm", "--label", "doltsamples.transient=true", LITE_IMAGE,
                        "sh", "-c", "doltlite -version; sqlite3 -version"], capture_output=True, text=True)
    print("  . " + " / ".join(l for l in v.stdout.splitlines() if l.strip()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
