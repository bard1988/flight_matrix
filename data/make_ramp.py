"""Derive the sequential green ramp used by the fare heatmap.

The board encodes *cheapness* as magnitude: dark green = cheapest, fading toward the
surface as price rises. That keeps the dataviz rule (one hue, light -> dark, monotonic
lightness, never a rainbow) while giving the cheapest cell the green the board is for.

Interpolating in sRGB desaturates the middle into grey, so steps are built in OKLCH at a
fixed green hue with chroma pushed to just inside the sRGB gamut at each lightness.

Run:  py -3 data/make_ramp.py
"""
from __future__ import annotations

import math

M1 = [
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005],
]
M2 = [
    [0.2104542553, 0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050, 0.4505937099],
    [0.0259040371, 0.7827717662, -0.8086757660],
]
M2_INV = [
    [1.0, 0.3963377774, 0.2158037573],
    [1.0, -0.1055613458, -0.0638541728],
    [1.0, -0.0894841775, -1.2914855480],
]
M1_INV = [
    [4.0767416621, -3.3077115913, 0.2309699292],
    [-1.2684380046, 2.6097574011, -0.3413193965],
    [-0.0041960863, -0.7034186147, 1.7076147010],
]


def _mul(m, v):
    return [sum(row[i] * v[i] for i in range(3)) for row in m]


def s2lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin2s(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def hex_to_oklch(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    rgb = [s2lin(int(value[i : i + 2], 16) / 255) for i in (0, 2, 4)]
    lms = [max(x, 0.0) ** (1 / 3) for x in _mul(M1, rgb)]
    L, a, b = _mul(M2, lms)
    return L, math.hypot(a, b), math.atan2(b, a)


def oklch_to_rgb(L: float, C: float, h: float) -> list[float]:
    lms = _mul(M2_INV, [L, C * math.cos(h), C * math.sin(h)])
    return _mul(M1_INV, [x**3 for x in lms])


def in_gamut(rgb: list[float], tol: float = 1e-4) -> bool:
    return all(-tol <= c <= 1 + tol for c in rgb)


def max_chroma(L: float, h: float) -> float:
    lo, hi = 0.0, 0.5
    for _ in range(40):
        mid = (lo + hi) / 2
        if in_gamut(oklch_to_rgb(L, mid, h)):
            lo = mid
        else:
            hi = mid
    return lo


def to_hex(L: float, C: float, h: float) -> str:
    rgb = oklch_to_rgb(L, C, h)
    return "#" + "".join(f"{max(0, min(255, round(lin2s(max(0.0, min(1.0, c))) * 255))):02x}" for c in rgb)


def build(anchor: str, lightest: float, darkest: float, steps: int, headroom: float) -> list[str]:
    _, _, hue = hex_to_oklch(anchor)
    out = []
    for i in range(steps):
        t = i / (steps - 1)
        L = lightest + (darkest - lightest) * t
        # Ease chroma up toward the dark end so the cheap cells read as saturated green
        # while the expensive end recedes politely toward the surface.
        want = 0.05 + (0.18 - 0.05) * (t**0.7)
        out.append(to_hex(L, min(want, max_chroma(L, hue) * headroom), hue))
    return out


if __name__ == "__main__":
    for mode, lightest, darkest in (("light", 0.965, 0.44), ("dark", 0.30, 0.72)):
        ramp = build("#008300", lightest, darkest, 7, headroom=0.94)
        print(f"{mode}: " + ",".join(ramp))
        print("   L:", [round(hex_to_oklch(c)[0], 3) for c in ramp])
        print("   C:", [round(hex_to_oklch(c)[1], 3) for c in ramp])
