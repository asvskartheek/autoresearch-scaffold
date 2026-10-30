"""AXI output: compact TOON-style text for agents, with next-step hints and fix-it errors."""
from __future__ import annotations

import json
import sys


def _cell(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4g}"
    s = str(v)
    if any(c in s for c in ",\n\""):
        s = '"' + s.replace('"', "'").replace("\n", " ") + '"'
    return s


def table(name: str, rows: list[dict], fields: list[str], total: int | None = None) -> str:
    total = len(rows) if total is None else total
    head = f"{name}[{len(rows)}" + (f" of {total}" if total != len(rows) else "") + "]{" + ",".join(fields) + "}:"
    if not rows:
        return f"{name}: 0 found"
    return "\n".join([head] + ["  " + ",".join(_cell(r.get(f)) for f in fields) for r in rows])


def kv(d: dict) -> str:
    return "\n".join(f"{k}: {_cell(v)}" for k, v in d.items() if v is not None)


def clip(text: str, n: int = 600) -> str:
    if text is None or len(text) <= n:
        return text
    return text[:n] + f"… ({len(text)} chars, --full)"


def emit(*blocks: str, help: list[str] | None = None, as_json=None) -> None:
    if as_json is not None:
        print(json.dumps(as_json, indent=1, default=str))
        return
    out = "\n".join(b for b in blocks if b)
    if help:
        out += "\nhelp[" + str(len(help)) + "]:\n" + "\n".join("  " + h for h in help)
    print(out)


def fail(msg: str, fix: str | None = None, code: int = 1):
    print(f"error: {msg}" + (f"\nfix: {fix}" if fix else ""))
    sys.exit(code)
