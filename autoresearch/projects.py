"""The projects registry: every arx project on this machine, so one loopback dashboard serves them all.

`~/.arx/projects.json` (or `$ARX_HOME/projects.json`) maps a short key to a project root. `arx init` and `arx up`
register the project they run in; `arx projects` lists, adds and removes entries. The dashboard serves the project
it was started in at `/` and every registered project at `/p/<key>/`. Only registered roots are ever served.
"""
from __future__ import annotations

import os, re
from pathlib import Path

from .core import _read, _write


def home() -> Path:
    return Path(os.environ.get("ARX_HOME") or Path.home() / ".arx")


def registry() -> dict[str, dict]:
    """key -> {root}; entries whose research.json is gone are left out (the file keeps them)."""
    reg = _read(home() / "projects.json", {}) or {}
    return {k: v for k, v in reg.items() if isinstance(v, dict) and (Path(v.get("root", "")) / "research.json").exists()}


def key_for(root: Path) -> str | None:
    root = str(Path(root).resolve())
    return next((k for k, v in (_read(home() / "projects.json", {}) or {}).items() if isinstance(v, dict) and v.get("root") == root), None)


def register(root: Path) -> str:
    """Add a project (idempotent); returns its key, a slug of the folder name, made unique."""
    root = Path(root).resolve()
    reg = _read(home() / "projects.json", {}) or {}
    have = key_for(root)
    if have:
        return have
    base = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-") or "project"
    key, i = base, 2
    while key in reg:
        key, i = f"{base}-{i}", i + 1
    reg[key] = dict(root=str(root))
    _write(home() / "projects.json", reg)
    return key


def unregister(key: str) -> bool:
    reg = _read(home() / "projects.json", {}) or {}
    if key not in reg:
        return False
    del reg[key]
    _write(home() / "projects.json", reg)
    return True


def root(key: str) -> Path:
    reg = registry()
    if key not in reg:
        raise KeyError(f"unknown project {key!r}")
    return Path(reg[key]["root"])
