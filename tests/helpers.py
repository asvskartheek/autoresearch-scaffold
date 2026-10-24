"""Shared test plumbing. Import this module FIRST: it points HOME at a temp dir before `autoresearch` is imported,
so ~/.arx/servers.json never touches the real one."""
from __future__ import annotations

import atexit, http.client, json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = Path(tempfile.mkdtemp(prefix="arx-test-home-"))
os.environ["HOME"] = str(HOME)
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

BOOT = f"import sys; sys.path.insert(0, {str(REPO)!r}); from autoresearch.cli import main; main()"


def env(**extra) -> dict:
    e = {k: v for k, v in os.environ.items() if k != "ARX_PARENT"}
    return e | {"HOME": str(HOME), "PYTHONDONTWRITEBYTECODE": "1"} | extra


def arx(cwd, *args, check=True, timeout=60, **envx) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, "-c", BOOT, *map(str, args)], cwd=cwd, env=env(**envx), capture_output=True,
                       text=True, timeout=timeout)
    if check and r.returncode:
        raise AssertionError(f"arx {' '.join(map(str, args))} exited {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(port: int, path: str, raw: bool = False):
    """GET -> (status, body). http.client sends odd paths (../, %2e) exactly as written."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        if raw:
            return r.status, body
        return r.status, (json.loads(body) if "json" in (r.getheader("Content-Type") or "") else body.decode())
    finally:
        c.close()


def wait_for(cond, timeout=10.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(out) and not out.startswith("Z")  # a zombie still answers kill(0)


def registry() -> list:
    try:
        return json.loads((HOME / ".arx" / "servers.json").read_text())
    except (OSError, ValueError):
        return []


def kill_all_servers():
    """Hard-stop every dashboard registered in the temp HOME."""
    for r in registry():
        try:
            os.kill(r["pid"], 9)
        except OSError:
            pass


def _cleanup():
    kill_all_servers()
    shutil.rmtree(HOME, ignore_errors=True)


atexit.register(_cleanup)


def new_project(parent, name="proj", **cfg) -> Path:
    """A minimal project: research.json + .research/, no dashboard, no vendored copy."""
    root = Path(parent) / name
    root.mkdir(parents=True, exist_ok=True)
    base = json.loads((REPO / "autoresearch" / "templates" / "research.json").read_text())
    (root / "research.json").write_text(json.dumps(base | {"name": name} | cfg))
    (root / ".research").mkdir(exist_ok=True)
    return root
