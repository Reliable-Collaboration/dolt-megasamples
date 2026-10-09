"""Build the DoltLite image from the release packages versions.json names.

  python3 -m doltsamples lite-image [--record]

DoltLite ships no container image, so this repository builds one: docker/doltlite/Dockerfile over
the two Debian packages of one release and sqlite.org's source tarball of one release -- the sqlite3
shell, built from source with the features the corpus's files use (FTS5 above all) -- each
downloaded and checked against the sha256 versions.json records. With `--record` the version the
built shell reports goes into versions.json.
"""
import argparse, hashlib, json, os, subprocess, sys, time, urllib.request

from doltsamples.util import BUILD, ROOT, VERSIONS_PATH, lite_image, versions

WORK = os.path.join(BUILD, "doltlite")


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


def build(v=None, record=False, versions_path=VERSIONS_PATH):
    """Build the image for the versions `v` names (versions.json by default); returns the image tag."""
    VERSIONS = v or versions()
    LITE_VERSION = VERSIONS["doltlite"]["version"]
    LITE_IMAGE = lite_image(VERSIONS)
    os.makedirs(WORK, exist_ok=True)
    for pkg in VERSIONS["doltlite"]["packages"]:
        fetch(pkg["name"], pkg["url"], pkg["sha256"])
    tarball = VERSIONS["sqlite"].get("tarball")
    if not tarball:
        sys.exit("versions.json names no SQLite source tarball: `make update` resolves the newest release and records it")
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
        if record:
            recorded.update(version=shell, since=time.strftime("%Y-%m-%d", time.gmtime()))
            tmp = versions_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(VERSIONS, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp, versions_path)
            print(f"  . recorded the sqlite3 shell the image carries, {shell}, in {os.path.basename(versions_path)}")
        else:
            print(f"  ! the image carries sqlite3 {shell}; versions.json records {recorded['version']} (--record records it)")
    return LITE_IMAGE


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", action="store_true", help="record the sqlite3 shell the image carries in versions.json")
    a = ap.parse_args(argv)
    build(record=a.record)
    return 0
