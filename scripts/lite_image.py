#!/usr/bin/env python3
"""Build the DoltLite image from the release packages versions.json names.

  python3 scripts/lite_image.py [--record]

DoltLite ships no container image, so this repository builds one: docker/doltlite/Dockerfile over
the two Debian packages of one release and sqlite.org's source tarball of one release -- the
sqlite3 shell, the SQLite baseline, built from source so the pair compares the newest SQLite with
the newest DoltLite -- each downloaded and checked against the sha256 versions.json records
(`make new-run` records them). With `--record` (what `make new-run` does) the version the built
shell reports goes into versions.json; without it, a shell that differs from the recorded one is
reported, because the SQLite units of the current run were measured with the recorded one.
"""
import argparse, hashlib, json, os, subprocess, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pairs import LITE_IMAGE, LITE_PACKAGES, LITE_VERSION, ROOT  # noqa: E402
from common import VERSIONS, VERSIONS_PATH  # noqa: E402

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
                 f"The release's package may have changed -- check before recording a new value in versions.json.")
    print(f"  . {name} {os.path.getsize(path):,} bytes, sha256 verified", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", action="store_true", help="record the sqlite3 shell the image carries in versions.json")
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    for name, url, sha in LITE_PACKAGES:
        fetch(name, url, sha)
    tarball = VERSIONS["sqlite"].get("tarball")
    if not tarball:
        sys.exit("versions.json names no SQLite source tarball: `make new-run` resolves the newest release and records it")
    fetch(tarball["name"], tarball["url"], tarball["sha256"])
    print(f"  . building {LITE_IMAGE} (DoltLite {LITE_VERSION}, SQLite {VERSIONS['sqlite']['version']} from source)", flush=True)
    p = subprocess.run(["docker", "build", "-q", "-f", os.path.join(ROOT, "docker", "doltlite", "Dockerfile"),
                        "--build-arg", f"LITE_VERSION={LITE_VERSION}", "--build-arg", f"SQLITE_TARBALL={tarball['name']}",
                        "-t", LITE_IMAGE, WORK], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(p.stderr or p.stdout)
    v = subprocess.run(["docker", "run", "--rm", "--label", "doltsamples.transient=true", LITE_IMAGE,
                        "sh", "-c", "doltlite -version; sqlite3 -version"], capture_output=True, text=True)
    lines = [l for l in v.stdout.splitlines() if l.strip()]
    print("  . " + " / ".join(lines))
    shell = (lines[1].split() or [""])[0] if len(lines) > 1 else ""
    # the shell must carry what the corpus's files use; a build without FTS5 would refuse their full-text tables
    opts = subprocess.run(["docker", "run", "--rm", "--label", "doltsamples.transient=true", "--entrypoint", "sqlite3", LITE_IMAGE,
                           ":memory:", "pragma compile_options"], capture_output=True, text=True).stdout.split()
    needed = {"ENABLE_FTS5", "ENABLE_FTS4", "ENABLE_FTS3", "ENABLE_RTREE", "ENABLE_GEOPOLY", "ENABLE_MATH_FUNCTIONS",
              "ENABLE_COLUMN_METADATA", "ENABLE_DBSTAT_VTAB", "ENABLE_SESSION", "SECURE_DELETE", "USE_URI"}
    missing = sorted(needed - set(opts))
    if missing:
        sys.exit(f"the built sqlite3 lacks {', '.join(missing)}: the Dockerfile's feature flags no longer match Debian's package")
    print(f"  . sqlite3 built with {', '.join(sorted(needed))}")
    recorded = VERSIONS["sqlite"]
    if shell and shell != recorded["version"]:
        if a.record:
            recorded.update(version=shell, since=__import__("time").strftime("%Y-%m-%d", __import__("time").gmtime()))
            tmp = VERSIONS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(VERSIONS, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp, VERSIONS_PATH)
            print(f"  . recorded the sqlite3 shell the image carries, {shell}, in versions.json")
        else:
            print(f"  ! the image carries sqlite3 {shell}; versions.json records {recorded['version']}, the shell the current "
                  f"run's SQLite units were measured with. `make new-run` records the new one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
