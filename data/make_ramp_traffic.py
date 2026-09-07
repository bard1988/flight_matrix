"""Derive the green -> orange -> red price ramp now used by the board.

Supersedes the neutral-midpoint diverging ramp (make_ramp_diverging.py / emit_ramp_css.py):
the product decision was a plain traffic-light scale, cheap = green, mid = orange,
dear = red.

Green / orange / red is the worst case for red-green colour blindness - under
deuteranopia the three hues collapse together - so hue is explicitly NOT the only
signal. WCAG relative luminance is kept STRICTLY MONOTONIC from q0 (cheapest) to q6
(dearest), so the ramp still reads as a light -> dark gradient with hue fully removed.
Every cell also prints its price, which is the real backstop.

This script just re-checks a hand-picked ramp: luminance monotonicity, the per-step
ink (black/white by contrast), contrast vs the surface, and a rough deutan/protan
delta-E for the mirrored pairs. Adjust RAMPS and re-run.

Run:  py -3 data/make_ramp_traffic.py
"""
from __future__ import annotations

import math

# Hand-picked, matched to frontend/styles.css. Keep the two in sync.
RAMPS = {
    "light": (
        ["#54b95c", "#4f9e3c", "#7f8a2f", "#b0742a", "#a95a2c", "#903a27", "#6a2a20"],
        "#fcfcfb",
    ),
    "dark": (
        ["#63c96a", "#69b544", "#9ba23f", "#cf8b3c", "#c56b34", "#b04a30", "#94382b"],
        "#1a1a19",
    ),
}


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(h: str) -> float:
    r, g, b = (_lin(x) for x in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    lo, hi = min(la, lb), max(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ink_for(fill: str) -> str:
    return "#0b0b0b" if contrast(fill, "#0b0b0b") >= contrast(fill, "#ffffff") else "#ffffff"


def _lab(h: str) -> tuple[float, float, float]:
    r, g, b = (_lin(x) for x in _rgb(h))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _sim(h: str, kind: str) -> str:
    r, g, b = (_lin(x) for x in _rgb(h))
    L = 17.8824 * r + 43.5161 * g + 4.11935 * b
    M = 3.45565 * r + 27.1554 * g + 3.86714 * b
    S = 0.0299566 * r + 0.184309 * g + 1.46709 * b
    if kind == "deutan":
        M = 0.494207 * L + 1.24827 * S
    else:  # protan
        L = 2.02344 * M - 2.52581 * S
    R = 0.0809 * L - 0.1305 * M + 0.1167 * S
    G = -0.0102 * L + 0.0540 * M - 0.1136 * S
    B = -0.0004 * L - 0.0041 * M + 0.6935 * S

    def enc(c: float) -> str:
        c = max(0.0, min(1.0, c))
        c = 1.055 * c ** (1 / 2.4) - 0.055 if c > 0.0031308 else 12.92 * c
        return f"{round(max(0, min(255, c * 255))):02x}"

    return "#" + enc(R) + enc(G) + enc(B)


def _dE(a: str, b: str) -> float:
    return math.dist(_lab(a), _lab(b))


def report(label: str, ramp: list[str], surface: str) -> None:
    lums = [luminance(c) for c in ramp]
    mono = all(lums[i] > lums[i + 1] for i in range(len(lums) - 1))
    print(f"\n{label}   monotonic cheap->dear: {mono}")
    print("  ", ",".join(ramp))
    print("   luminance   ", [round(x, 3) for x in lums])
    print("   ink         ", [ink_for(c) for c in ramp])
    print("   label contr ", [round(contrast(c, ink_for(c)), 2) for c in ramp])
    print("   vs surface  ", [round(contrast(c, surface), 2) for c in ramp])
    n = len(ramp)
    for i in range(n // 2):
        j = n - 1 - i
        a, b = ramp[i], ramp[j]
        print(f"   q{i} vs q{j}: normal {_dE(a, b):5.1f}  "
              f"deutan {_dE(_sim(a, 'deutan'), _sim(b, 'deutan')):5.1f}  "
              f"protan {_dE(_sim(a, 'protan'), _sim(b, 'protan')):5.1f}")


if __name__ == "__main__":
    for mode, (ramp, surface) in RAMPS.items():
        report(mode, ramp, surface)
