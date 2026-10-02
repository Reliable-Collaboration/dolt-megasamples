"""Which release of each engine this checkout builds with, and moving to the newest.

  python3 -m doltsamples versions          each engine here beside the newest release upstream
  python3 -m doltsamples update [ENGINE]   move every engine (or one) to its newest release

versions.json names each one exactly: Dolt and DoltgreSQL by the image digest Docker Hub publishes for
the release's tag, DoltLite by the SHA-256 of its two Debian packages (DoltLite ships no image, so
`make lite-image` builds one from them), and the sqlite3 shell that image carries -- built from
sqlite.org's newest release, since the exports use it to dump the corpus's SQLite files -- by its
source tarball's checksums. Nothing moves on its own. After `update`, `make lite-image` if DoltLite or
SQLite moved, then `make build`: a store built with an older release is shown as stale by
`make status` and built again.
"""
import argparse, hashlib, json, os, re, sys, time, urllib.error, urllib.request

from doltsamples.util import BUILD, VERSIONS_PATH, lock_held, run

VERSIONS = json.load(open(VERSIONS_PATH, encoding="utf-8"))

RELEASES = {"doltlite": "dolthub/doltlite", "doltgres": "dolthub/doltgresql", "dolt": "dolthub/dolt"}
IMAGES = {"doltgres": "dolthub/doltgresql", "dolt": "dolthub/dolt-sql-server"}
# the baselines' official images, the tag shape that names a release (not a variant like 9.7.2-oraclelinux9),
# and the track tag a release must share an image with, if any. MySQL publishes two tracks, Innovation
# (`latest`, 26.7.0 on 2026-09-29) and LTS (`lts`, 9.7.2); the maintainer chose LTS on 2026-10-01, the
# release production users run and the one the corpus builds its dumps with.
HUB = {}
SQLITE_DOWNLOADS = "https://sqlite.org/download.html"
ENGINES = ("dolt", "doltgres", "doltlite", "sqlite")
WORK = os.path.join(BUILD, "doltlite")     # the DoltLite image's build context: its packages and the SQLite tarball


def github(path):
    req = urllib.request.Request(f"https://api.github.com/{path}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "dolt-megasamples"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def hub_tags(repo):
    """Every tag of an official Docker Hub image, newest first, as (name, last_updated date, digest)."""
    url = f"https://hub.docker.com/v2/repositories/library/{repo}/tags?page_size=100&ordering=last_updated"
    out = []
    for _ in range(10):
        req = urllib.request.Request(url, headers={"User-Agent": "dolt-megasamples"})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.load(r)
        out += [(t["name"], (t.get("last_updated") or "")[:10], t.get("digest") or "") for t in page.get("results", [])]
        url = page.get("next")
        if not url:
            break
    return out


def version_key(v):
    return tuple(int(x) for x in v.split("."))


def newest(engine):
    """(version, published date, release record) of the newest release of an engine upstream."""
    if engine in RELEASES:
        rel = github(f"repos/{RELEASES[engine]}/releases/latest")
        return rel["tag_name"].lstrip("v"), rel.get("published_at", "")[:10], rel
    if engine in HUB:
        repo, pattern, track = HUB[engine]
        every = hub_tags(repo)
        tags = [(n, d) for n, d, _ in every if re.fullmatch(pattern, n)]
        if track:
            image = next((g for n, _, g in every if n == track), "")
            tags = [(n, d) for n, d, g in every if re.fullmatch(pattern, n) and g and g == image]
        if not tags:
            raise RuntimeError(f"no release tag of library/{repo} matches {pattern}"
                               + (f" on the image `{track}` names" if track else ""))
        name, date = max(tags, key=lambda t: version_key(t[0]))
        return name, date, {"tag": name}
    # sqlite.org's download page carries a machine-readable line per product:
    #   PRODUCT,3.53.4,2026/sqlite-autoconf-3530400.tar.gz,3283177,<sha3-256>
    req = urllib.request.Request(SQLITE_DOWNLOADS, headers={"User-Agent": "dolt-megasamples"})
    with urllib.request.urlopen(req, timeout=60) as r:
        page = r.read().decode("utf-8", "replace")
    m = re.search(r"^PRODUCT,([\d.]+),(\d{4}/sqlite-autoconf-\d+\.tar\.gz),(\d+),([0-9a-f]{64})$", page, re.M)
    if not m:
        raise RuntimeError("sqlite.org's download page no longer carries the PRODUCT line for the autoconf tarball")
    version, path, size, sha3 = m.groups()
    return version, "", {"url": f"https://sqlite.org/{path}", "size": int(size), "sha3_256": sha3}


def check():
    print(f"{'engine':10s} {'here':10s} {'since':11s} {'newest upstream':18s} published")
    for engine in ENGINES:
        here = VERSIONS[engine]
        try:
            up, date, _ = newest(engine)
        except Exception as exc:                                       # noqa: BLE001
            up, date = f"? ({type(exc).__name__})", ""
        flag = "" if up == here["version"] else "   <- newer upstream; `make update` moves it"
        print(f"{engine:10s} {here['version']:10s} {here['since']:11s} {up:18s} {date}{flag}")
    return 0


def sha256_of(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def download(url, path, digest=None):
    """Fetch fresh -- never trust a file already on disk -- and check it against the release's digest
    when the API publishes one (GitHub does, as sha256:...)."""
    print(f"  . downloading {os.path.basename(path)}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "dolt-megasamples"})
    with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    got = sha256_of(path + ".part")
    if digest and digest.split(":", 1)[-1] != got:
        os.remove(path + ".part")
        sys.exit(f"{os.path.basename(path)}: downloaded sha256 {got} is not the release's {digest}")
    os.replace(path + ".part", path)
    return got


def pulled_digest(repo, tag):
    """`repo@sha256:...` for the image just pulled as repo:tag: the digest Docker Hub names for the tag
    (the multi-platform index, which every platform pulls by), checked against what the engine recorded.
    Docker records `repo@digest`; Podman records `docker.io/library/repo@digest` and the platform
    manifest's digest beside it, so the recorded names are compared without the registry prefix."""
    path = repo if "/" in repo else f"library/{repo}"
    req = urllib.request.Request(f"https://hub.docker.com/v2/repositories/{path}/tags/{tag}",
                                 headers={"User-Agent": "dolt-megasamples"})
    with urllib.request.urlopen(req, timeout=60) as r:
        want = json.load(r).get("digest") or ""
    recorded = run("docker", "image", "inspect", "--format", "{{join .RepoDigests \" \"}}", f"{repo}:{tag}").stdout.split()
    bare = {re.sub(r"^docker\.io/(library/)?", "", d) for d in recorded}
    if not want or f"{repo}@{want}" not in bare:
        sys.exit(f"the pulled {repo}:{tag} is not the image Docker Hub names ({want or 'no digest'}): {recorded}")
    return f"{repo}@{want}"


def resolve(engine):
    """Move one engine's entry in VERSIONS to its newest release. Returns (was, now) or None if unchanged."""
    here = VERSIONS[engine]
    was = here["version"]
    version, date, rel = newest(engine)
    if version == was:
        print(f"  . {engine} {version} is the newest release (published {date})")
        return None
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if engine == "sqlite":
        os.makedirs(WORK, exist_ok=True)
        name = os.path.basename(rel["url"])
        path = os.path.join(WORK, name)
        sha = download(rel["url"], path)
        got3 = hashlib.sha3_256(open(path, "rb").read()).hexdigest()
        if got3 != rel["sha3_256"]:
            os.remove(path)
            sys.exit(f"{name}: sha3-256 {got3} is not the {rel['sha3_256']} sqlite.org's download page names")
        here.update(version=version, since=today, tarball={"name": name, "url": rel["url"], "sha256": sha, "sha3_256": got3},
                    named_by=f"built from sqlite.org's {name} (sha3-256 verified against its download page) into the DoltLite image")
        print(f"  . {name} {os.path.getsize(path):,} bytes, sha3-256 as sqlite.org's page names it")
    elif engine in HUB:
        ref = f"{HUB[engine][0]}:{version}"
        print(f"  . pulling {ref}", flush=True)
        if run("docker", "pull", ref).returncode != 0:
            sys.exit(f"could not pull {ref}")
        digest = pulled_digest(HUB[engine][0], version)
        here.update(version=version, since=today, image=digest, named_by=f"the official image {ref}, by digest")
    elif engine == "doltlite":
        work = WORK
        os.makedirs(work, exist_ok=True)
        assets = {a["name"]: a for a in rel.get("assets", [])}
        packages = []
        for name in (f"libdoltlite0_{version}_amd64.deb", f"doltlite_{version}_amd64.deb"):
            if name not in assets:
                sys.exit(f"release v{version} has no asset {name}; the packaging changed, so versions.json needs a hand")
            path = os.path.join(work, name)
            sha = download(assets[name]["browser_download_url"], path, assets[name].get("digest"))
            packages.append({"name": name, "url": assets[name]["browser_download_url"], "sha256": sha})
            print(f"  . {name} {os.path.getsize(path):,} bytes, sha256 {sha}"
                  + (" (the release's digest)" if assets[name].get("digest") else ""))
        here.update(version=version, since=today, packages=packages)
    else:
        ref = f"{IMAGES[engine]}:{version}"
        print(f"  . pulling {ref}", flush=True)
        if run("docker", "pull", ref).returncode != 0:
            sys.exit(f"could not pull {ref}")
        digest = pulled_digest(IMAGES[engine], version)
        here.update(version=version, since=today, image=digest)
    print(f"  . {engine}: {was} -> {version} (published {date})")
    return was, version


def write_versions():
    tmp = VERSIONS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(VERSIONS, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, VERSIONS_PATH)


def latest(engines):
    holder = lock_held()
    if holder:
        sys.exit(f"{holder} holds build/build.lock; move nothing while a build runs")
    moved = {}
    for engine in engines:
        try:
            r = resolve(engine)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            sys.exit(f"{engine}: could not reach the release: {exc}")
        if r:
            moved[engine] = r
    if not moved:
        print("\nEvery engine is on its newest release; nothing changed.")
        return 0
    write_versions()
    print(f"\nversions.json updated: " + ", ".join(f"{e} {was} -> {now}" for e, (was, now) in moved.items()) + ".\n"
          "Next: `make lite-image` if DoltLite or SQLite moved, then `make build`, which rebuilds every store "
          "an older release wrote, then `make up`.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="report the newest upstream release beside each version here")
    ap.add_argument("--latest", nargs="?", const="all", choices=list(ENGINES) + ["all"], metavar="ENGINE",
                    help="move every engine (or one) to its newest release")
    a = ap.parse_args(argv)
    if a.latest:
        return latest(list(ENGINES) if a.latest == "all" else [a.latest])
    return check()
