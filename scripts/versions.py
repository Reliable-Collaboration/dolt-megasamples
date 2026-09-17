#!/usr/bin/env python3
"""What versions.json names, what is newer upstream, and how a new run moves to the newest releases.

  python3 scripts/versions.py --check              # each engine: the version here, the newest upstream
  python3 scripts/versions.py --latest             # a new run: every engine to its newest release (make new-run)
  python3 scripts/versions.py --latest doltlite    # one engine only

One version per run, and no pins (the maintainer's rule, 2026-09-12, revised 2026-09-16 and again
that day: "we want all tools to be the newest during a run"): a run starts on the newest release of
every engine, the baselines included, and keeps those versions until it is complete. `--check` only
reports; nothing moves on its own. `--latest` resolves the newest release of each of the six --
Dolt and DoltgreSQL: the newest GitHub release's image tag, pulled and resolved to its digest;
DoltLite: the newest GitHub release's two amd64 Debian packages, downloaded fresh and checked
against the release's own digests; MySQL and PostgreSQL: the newest version tag of the official
Docker Hub image, pulled and resolved to its digest; SQLite: the newest release sqlite.org's
download page names, its source tarball downloaded and checked against the page's SHA3-256, to be
built into the DoltLite image as the pair's baseline shell -- rewrites versions.json and
compose.yaml's defaults, and retires the old run: every recorded unit and memory-study cell of an
engine that moved is dropped (git history keeps the old run), so the runners measure them again. It
refuses to run while a runner holds build/run.lock. `--check` also fails if compose.yaml's
documented image defaults drift from versions.json.
"""
import argparse, hashlib, json, os, re, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, VERSIONS, VERSIONS_PATH, lock_held, run  # noqa: E402

RELEASES = {"doltlite": "dolthub/doltlite", "doltgres": "dolthub/doltgresql", "dolt": "dolthub/dolt"}
IMAGES = {"doltgres": "dolthub/doltgresql", "dolt": "dolthub/dolt-sql-server"}
# the baselines' official images, and the tag shape that names a release (not a variant like 9.7.2-oraclelinux9)
HUB = {"mysql": ("mysql", r"^\d+\.\d+\.\d+$"), "postgres": ("postgres", r"^\d+\.\d+$")}
SQLITE_DOWNLOADS = "https://sqlite.org/download.html"
ENGINES = ("mysql", "dolt", "postgres", "doltgres", "sqlite", "doltlite")
WORK = os.path.join(ROOT, "build", "doltlite")     # the DoltLite image's build context: its packages and the SQLite tarball
COMPOSE = os.path.join(ROOT, "compose.yaml")
PROGRESS = os.path.join(ROOT, "build", "progress.json")
STUDIES = {"dolt": os.path.join(ROOT, "build", "memory.json"),
           "doltgres": os.path.join(ROOT, "build", "memory_pairs.json"),
           "doltlite": os.path.join(ROOT, "build", "memory_pairs.json")}


def github(path):
    req = urllib.request.Request(f"https://api.github.com/{path}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "dolt-megasamples"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def hub_tags(repo):
    """Every tag of an official Docker Hub image, newest first, as (name, last_updated date)."""
    url = f"https://hub.docker.com/v2/repositories/library/{repo}/tags?page_size=100&ordering=last_updated"
    out = []
    for _ in range(10):
        req = urllib.request.Request(url, headers={"User-Agent": "dolt-megasamples"})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.load(r)
        out += [(t["name"], (t.get("last_updated") or "")[:10]) for t in page.get("results", [])]
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
        repo, pattern = HUB[engine]
        tags = [(n, d) for n, d in hub_tags(repo) if re.fullmatch(pattern, n)]
        if not tags:
            raise RuntimeError(f"no release tag of library/{repo} matches {pattern}")
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
    drift = []
    text = open(COMPOSE, encoding="utf-8").read()
    print(f"{'engine':10s} {'here':10s} {'since':11s} {'newest upstream':18s} published")
    for engine in ENGINES:
        here = VERSIONS[engine]
        try:
            up, date, _ = newest(engine)
        except Exception as exc:                                       # noqa: BLE001
            up, date = f"? ({type(exc).__name__})", ""
        flag = "" if up == here["version"] else "   <- newer upstream; `make new-run` moves it"
        print(f"{engine:10s} {here['version']:10s} {here['since']:11s} {up:18s} {date}{flag}")
        if engine in IMAGES and here["image"] not in text:
            drift.append(f"compose.yaml does not carry versions.json's {engine} image {here['image']}")
    lite_tag = f"doltsamples-doltlite:{VERSIONS['doltlite']['version']}"
    if lite_tag not in text:
        drift.append(f"compose.yaml does not carry the DoltLite image tag {lite_tag}")
    if drift:
        print("\n" + "\n".join(drift) + "\n\nThe stack takes its images from versions.json through compose.override.yaml, "
              "but compose.yaml's documented defaults should say the same.")
        return 1
    print("\nOne version per run: `make new-run` moves every engine to its newest release and drops the old run's units.")
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
        digests = run("docker", "image", "inspect", "--format", "{{join .RepoDigests \" \"}}", ref).stdout.split()
        digest = next((d for d in digests if d.startswith(HUB[engine][0] + "@")), None)
        if not digest:
            sys.exit(f"no repository digest recorded for {ref}: {digests}")
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
        digests = run("docker", "image", "inspect", "--format", "{{join .RepoDigests \" \"}}", ref).stdout.split()
        digest = next((d for d in digests if d.startswith(IMAGES[engine] + "@")), None)
        if not digest:
            sys.exit(f"no repository digest recorded for {ref}: {digests}")
        here.update(version=version, since=today, image=digest)
    print(f"  . {engine}: {was} -> {version} (published {date})")
    return was, version


def write_versions():
    tmp = VERSIONS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(VERSIONS, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, VERSIONS_PATH)
    text = open(COMPOSE, encoding="utf-8").read()
    for engine, image in IMAGES.items():
        text = re.sub(rf"image: {re.escape(image)}@sha256:[0-9a-f]{{64}}", f"image: {VERSIONS[engine]['image']}", text)
    text = re.sub(r"image: doltsamples-doltlite:\S+", f"image: doltsamples-doltlite:{VERSIONS['doltlite']['version']}", text)
    open(COMPOSE, "w", encoding="utf-8").write(text)


def retire(moved):
    """The old run's records of the engines that moved go: the units in build/progress.json and the
    cells of the memory studies. The collectors withdraw their folded numbers on the next `make report`."""
    from common import current
    if os.path.exists(PROGRESS):
        p = json.load(open(PROGRESS, encoding="utf-8"))
        before = len(p.get("units") or {})
        p["units"] = {k: u for k, u in (p.get("units") or {}).items()
                      if current(k, u) or u.get("status") != "done"}
        p.pop("superseded", None)
        tmp = PROGRESS + ".tmp"
        json.dump(p, open(tmp, "w", encoding="utf-8"), indent=2, sort_keys=True)
        os.replace(tmp, PROGRESS)
        print(f"  . dropped {before - len(p['units'])} unit(s) measured on the old versions from build/progress.json")
    for engine in moved:
        path = STUDIES.get(engine)
        if not path or not os.path.exists(path):
            continue
        study = json.load(open(path, encoding="utf-8"))
        if engine == "dolt":
            study = {k: v for k, v in study.items() if k.startswith("_")}
        else:
            study.pop(engine, None)
        study.setdefault("_versions", {}).pop(engine, None)
        json.dump(study, open(path, "w", encoding="utf-8"), indent=1, sort_keys=True)
        print(f"  . dropped the {engine} cells of {os.path.relpath(path, ROOT)}")


def latest(engines):
    if lock_held():
        sys.exit("a runner holds build/run.lock: a run keeps its versions until it is complete; move nothing now")
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
    retire(moved)
    print(f"\nversions.json and compose.yaml's defaults updated: "
          + ", ".join(f"{e} {was} -> {now}" for e, (was, now) in moved.items()) + ".\n"
          "Next: `make lite-image` if DoltLite or SQLite moved (it builds the shell and records what the image carries), then the runs "
          "(`make run`, `make run-pg`, `make run-lite`, both index policies, `make memory-pairs`), then `make report`. "
          "Record the move in knowledge/ (an Update on the engine's tool record and log.md).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="report the newest upstream release beside each version here")
    ap.add_argument("--latest", nargs="?", const="all", choices=list(ENGINES) + ["all"], metavar="ENGINE",
                    help="a new run: move every engine (or one of the six) to its newest release")
    a = ap.parse_args()
    if a.latest:
        return latest(list(ENGINES) if a.latest == "all" else [a.latest])
    return check()


if __name__ == "__main__":
    sys.exit(main())
