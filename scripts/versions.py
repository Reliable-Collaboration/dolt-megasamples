#!/usr/bin/env python3
"""What versions.json names, what is newer upstream, and how to move one engine forward.

  python3 scripts/versions.py --check              # each engine: the version here, the newest upstream
  python3 scripts/versions.py --latest doltlite     # move one engine to its newest release
  python3 scripts/versions.py --latest doltgres
  python3 scripts/versions.py --latest dolt

One version per result set (the maintainer's rule, 2026-09-12): every number in this repository
belongs to the versions in versions.json, and nothing is pinned. `--check` only reports; nothing
moves on its own. `--latest` rewrites versions.json for one engine -- DoltLite: the newest GitHub
release's two amd64 Debian packages, downloaded and checksummed; DoltgreSQL and Dolt: the newest
GitHub release's image tag, pulled and resolved to its digest -- and says what follows: `make
lite-image` for DoltLite, `make up` for the served stack, and a run with `--accept-version-change`,
which supersedes every recorded unit of that engine and measures them all again. `--check` also
fails if compose.yaml's documented image defaults drift from versions.json.
"""
import argparse, hashlib, json, os, re, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, VERSIONS, VERSIONS_PATH, run  # noqa: E402

RELEASES = {"doltlite": "dolthub/doltlite", "doltgres": "dolthub/doltgresql", "dolt": "dolthub/dolt"}
IMAGES = {"doltgres": "dolthub/doltgresql", "dolt": "dolthub/dolt-sql-server"}
COMPOSE = os.path.join(ROOT, "compose.yaml")


def github(path):
    req = urllib.request.Request(f"https://api.github.com/{path}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "dolt-megasamples"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def newest(engine):
    """(version, published date, release record) of the newest GitHub release."""
    rel = github(f"repos/{RELEASES[engine]}/releases/latest")
    return rel["tag_name"].lstrip("v"), rel.get("published_at", "")[:10], rel


def check():
    drift = []
    text = open(COMPOSE, encoding="utf-8").read()
    print(f"{'engine':10s} {'here':10s} {'since':11s} {'newest upstream':18s} published")
    for engine in ("dolt", "doltgres", "doltlite"):
        here = VERSIONS[engine]
        try:
            up, date, _ = newest(engine)
        except Exception as exc:                                       # noqa: BLE001
            up, date = f"? ({type(exc).__name__})", ""
        flag = "" if up == here["version"] else "   <- newer upstream; `--latest " + engine + "` moves it"
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
    print("\nOne version per result set: moving one means every unit of that engine is measured again.")
    return 0


def sha256_of(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def download(url, path):
    print(f"  . downloading {os.path.basename(path)}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "dolt-megasamples"})
    with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    os.replace(path + ".part", path)


def latest(engine):
    here = VERSIONS[engine]
    was = here["version"]
    version, date, rel = newest(engine)
    if version == here["version"]:
        print(f"{engine} {version} is already the newest release (published {date}); nothing changed")
        return 0
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if engine == "doltlite":
        work = os.path.join(ROOT, "build", "doltlite")
        os.makedirs(work, exist_ok=True)
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        packages = []
        for name in (f"libdoltlite0_{version}_amd64.deb", f"doltlite_{version}_amd64.deb"):
            if name not in assets:
                sys.exit(f"release v{version} has no asset {name}; the packaging changed, so versions.json needs a hand")
            path = os.path.join(work, name)
            if not os.path.exists(path):
                download(assets[name], path)
            packages.append({"name": name, "url": assets[name], "sha256": sha256_of(path)})
            print(f"  . {name} {os.path.getsize(path):,} bytes, sha256 {packages[-1]['sha256']}")
        here.update(version=version, since=today, packages=packages)
        follow = "make lite-image, then run the SQLite/DoltLite pair with --accept-version-change"
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
        follow = ("run the PostgreSQL/DoltgreSQL pair with --accept-version-change" if engine == "doltgres"
                  else "make run with --accept-version-change")
    json.dump(VERSIONS, open(VERSIONS_PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    with open(VERSIONS_PATH, "a", encoding="utf-8") as fh:
        fh.write("\n")
    text = open(COMPOSE, encoding="utf-8").read()
    if engine in IMAGES:
        text = re.sub(rf"image: {re.escape(IMAGES[engine])}@sha256:[0-9a-f]{{64}}", f"image: {here['image']}", text)
    else:
        text = re.sub(r"image: doltsamples-doltlite:\S+", f"image: doltsamples-doltlite:{version}", text)
    open(COMPOSE, "w", encoding="utf-8").write(text)
    print(f"\n{engine}: {version} since {today} (was {was}); versions.json and compose.yaml's default updated.\n"
          f"One version per result set: every recorded {engine} unit is now superseded. Next: {follow}; "
          f"then `make report`. Record the move in knowledge/ (an Update on the engine's tool record and log.md).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="report the newest upstream release beside each version here")
    ap.add_argument("--latest", choices=sorted(RELEASES), metavar="ENGINE",
                    help="move one engine (dolt, doltgres, doltlite) to its newest release")
    a = ap.parse_args()
    if a.latest:
        return latest(a.latest)
    return check()


if __name__ == "__main__":
    sys.exit(main())
