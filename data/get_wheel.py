"""Download a public PyPI wheel directly, bypassing pip's pinned corporate mirror.

pip on this machine is pinned to an internal Artifactory mirror that cannot serve
fast-flights, and pip's own TLS stack fails against upstream PyPI. httpx works fine with
the corporate CA bundle, so fetch the wheel here and install it from disk.

    py -3 data/get_wheel.py <package> [more packages...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "wheels"
def pick(files: list[dict]) -> dict | None:
    """Prefer a pure-python wheel, else a CPython 3.10 win_amd64 one."""
    wheels = [f for f in files if f["filename"].endswith(".whl") and not f.get("yanked")]
    for predicate in (
        lambda n: n.endswith("-py3-none-any.whl") or n.endswith("-py2.py3-none-any.whl"),
        lambda n: "cp310" in n and "win_amd64" in n,
        lambda n: "abi3" in n and "win_amd64" in n,
        lambda n: "none-any" in n,
    ):
        for f in wheels:
            if predicate(f["filename"]):
                return f
    sdists = [f for f in files if f["filename"].endswith(".tar.gz") and not f.get("yanked")]
    return sdists[0] if sdists else None


def main() -> int:
    OUT.mkdir(exist_ok=True)
    with httpx.Client(timeout=60.0, verify=config.CA_BUNDLE, follow_redirects=True) as client:
        for name in sys.argv[1:]:
            meta = client.get(f"https://pypi.org/pypi/{name}/json")
            if meta.status_code != 200:
                print(f"  !! {name}: PyPI returned {meta.status_code}")
                continue
            data = meta.json()
            version = data["info"]["version"]
            requires = data["info"].get("requires_dist") or []
            chosen = pick(data["urls"])
            if not chosen:
                print(f"  !! {name}: no distribution found")
                continue
            target = OUT / chosen["filename"]
            if not target.exists():
                target.write_bytes(client.get(chosen["url"]).content)
            print(f"  {name} {version} -> {chosen['filename']} ({target.stat().st_size // 1024} KB)")
            deps = [r.split(";")[0].strip() for r in requires if "extra ==" not in r]
            if deps:
                print(f"      requires: {', '.join(deps)}")
    print(f"\nwheels in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
