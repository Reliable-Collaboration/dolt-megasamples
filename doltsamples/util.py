"""Paths, process helpers and the small things every command needs."""
import fcntl, json, os, subprocess, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DATA = os.path.join(ROOT, "data")
EXPORTS = os.path.join(BUILD, "exports")
VERSIONS_PATH = os.path.join(ROOT, "versions.json")
STORES = os.path.join(BUILD, "stores.json")
LOCK_PATH = os.path.join(BUILD, "build.lock")
TRANSIENT = "doltsamples.transient=true"      # every throwaway container carries this label


def versions():
    return json.load(open(VERSIONS_PATH, encoding="utf-8"))


def lite_image(v=None):
    return f"doltsamples-doltlite:{(v or versions())['doltlite']['version']}"


def run(*args, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(list(args), **kw)


def mem(limit):
    """Docker arguments capping a container's memory with swap off: a load that outgrows its limit
    is killed on its own rather than dragging the machine into swap with it."""
    return ["--memory", limit, "--memory-swap", limit]


def host_memory_gb():
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 8.0


def default_build_memory():
    """What a build container may use when the config does not say: the machine's memory less
    what the host keeps for itself, between 2 and 16 GiB."""
    return f"{max(2, min(16, int(host_memory_gb() - 2.75)))}g"


def human(n):
    """Bytes in binary units, labelled as binary units (what `du -h` and `docker stats` print)."""
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        shown = round(abs(n)) if unit == "B" else round(abs(n), 1)
        if shown < 1000 or unit == "TiB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024


def duration(v):
    if round(v, 1) < 10:
        return f"{v:.1f} s"
    r = int(round(v))
    if r < 60:
        return f"{r} s"
    if r < 3600:
        m, s = divmod(r, 60)
        return f"{m} min {s:02d} s"
    h, rem = divmod(r, 3600)
    return f"{h} h {rem // 60:02d} min"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def rel(path):
    return os.path.relpath(path, ROOT)


def ensure_dir(path):
    """Created as this user before Docker can create it as root."""
    os.makedirs(path, exist_ok=True)
    return path


def remove_tree(host_dir, image=None):
    """Remove a directory a container wrote into. On rootful Docker its files belong to root, so it
    is emptied from inside a container; on a rootless engine that works the same way."""
    if not os.path.exists(host_dir):
        return
    parent, name = os.path.dirname(host_dir), os.path.basename(host_dir)
    p = run("docker", "run", "--rm", "--label", TRANSIENT, "-v", f"{parent}:/p", "--entrypoint", "sh",
            image or lite_image(), "-c", f"rm -rf '/p/{name}'")
    if p.returncode != 0 and os.path.exists(host_dir):
        raise RuntimeError(f"could not remove {rel(host_dir)}: {p.stderr.strip()[:200]}")


def lock(what):
    """Hold build/build.lock for the life of the process: (file, None), or (None, who holds it).
    A build and `make up` must not run at once -- the stack would mount stores being rewritten."""
    ensure_dir(BUILD)
    fh = open(LOCK_PATH, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.seek(0)
        holder = fh.read().strip() or "another process"
        fh.close()
        return None, holder
    fh.seek(0)
    fh.truncate()
    fh.write(f"{what}, pid {os.getpid()}, since {now()}\n")
    fh.flush()
    return fh, None


def lock_held():
    fh, holder = lock("a check")
    if fh is None:
        return holder
    fh.close()
    return None


def load_json(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path, data):
    ensure_dir(os.path.dirname(path))
    with open(path + ".part", "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(path + ".part", path)
