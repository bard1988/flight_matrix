"""Derive and validate the fare-heatmap ramp, and print it as CSS custom properties.

The board encodes price as magnitude. The ramp runs green -> amber -> red, but the real
work is done by LIGHTNESS: it is strictly monotonic cheapest -> dearest, so the scale
still separates every step when hue is lost (deuteranopia / protanopia / greyscale /
print). The cheap end also carries the salience the board is for - the deepest, most
saturated green on the light surface, the brightest green on the dark one - while the
dear end recedes toward the surface. Every cell additionally prints its price, so colour
is never the only signal.

This supersedes make_ramp.py / make_ramp_diverging.py / emit_ramp_css.py, which built the
earlier one-hue and diverging ramps. It is self-contained (no bundled-skill path).

Run:  py -3 data/emit_fare_ramp.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_ramp import hex_to_oklch, max_chroma, to_hex  # OKLCH <-> sRGB helpers  # noqa: E402

RAD = math.pi / 180

# --- sRGB -> OKLab, WCAG contrast, Machado-Oliveira-Fernandes CVD (severity 1.0) -------

_M1 = [[0.4122214708, 0.5363325363, 0.0514459929],
       [0.2119034982, 0.6806995451, 0.1073969566],
       [0.0883024619, 0.2817188376, 0.6299787005]]
_M2 = [[0.2104542553, 0.7936177850, -0.0040720468],
       [1.9779984951, -2.4285922050, 0.4505937099],
       [0.0259040371, 0.7827717662, -0.8086757660]]
_MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868],
               [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968],
               [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
}


def _mul(m, v):
    return [sum(m[r][i] * v[i] for i in range(3)) for r in range(3)]


def _s2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _hex_rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _oklab(h):
    lin = [_s2lin(c) for c in _hex_rgb(h)]
    lms = [max(x, 0.0) ** (1 / 3) for x in _mul(_M1, lin)]
    return _mul(_M2, lms)


def contrast(a, b):
    def lum(h):
        r, g, bl = (_s2lin(c) for c in _hex_rgb(h))
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    la, lb = sorted((lum(a), lum(b)))
    return (lb + 0.05) / (la + 0.05)


def delta_e(a, b, cvd=None):
    def prep(h):
        if not cvd:
            return _oklab(h)
        lin = [_s2lin(c) for c in _hex_rgb(h)]
        sim = [min(1.0, max(0.0, x)) for x in _mul(_MACHADO[cvd], lin)]
        s = [12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055 for x in sim]
        hx = "#" + "".join(f"{round(max(0, min(1, x)) * 255):02x}" for x in s)
        return _oklab(hx)
    pa, pb = prep(a), prep(b)
    return 100 * math.dist(pa, pb)


# Off-black and off-white, never pure #000/#fff: pure values flatten the depth the warm
# neutrals carry, and #fcfcfb is already the system's raised-paper white, so the ramp inks
# reuse a palette value instead of introducing an eighth near-white.
INK_DARK = "#0b0b0b"
INK_LIGHT = "#fcfcfb"


def ink_for(fill):
    return INK_DARK if contrast(fill, INK_DARK) >= contrast(fill, INK_LIGHT) else INK_LIGHT


# --- the ramp -------------------------------------------------------------------------

HUE = [158, 152, 148, 70, 46, 32, 22]        # green ... gold pivot ... warm red (deg)
CHR = [0.145, 0.150, 0.145, 0.125, 0.124, 0.120, 0.090]
L = {
    # cheap dark -> dear light, tuned to the warm-white surface
    "light": [0.435, 0.502, 0.568, 0.638, 0.710, 0.776, 0.842],
    # mirrored for the near-black surface: cheap bright -> dear deep
    "dark":  [0.830, 0.760, 0.688, 0.618, 0.548, 0.478, 0.405],
}
SURFACE = {"light": "#fcfcfb", "dark": "#1a1a19"}


def build(mode: str) -> list[str]:
    out = []
    for Lv, Hv, Cv in zip(L[mode], HUE, CHR):
        cap = max_chroma(Lv, Hv * RAD) * 0.92
        out.append(to_hex(Lv, min(Cv, cap), Hv * RAD))
    return out


def check(mode: str, ramp: list[str]) -> bool:
    inks = [ink_for(c) for c in ramp]
    Ls = [hex_to_oklch(c)[0] for c in ramp]
    dL = [Ls[i + 1] - Ls[i] for i in range(6)]
    mono = all(d > 0 for d in dL) if mode == "light" else all(d < 0 for d in dL)
    labels = [contrast(c, k) for c, k in zip(ramp, inks)]
    ok = mono and min(abs(d) for d in dL) >= 0.06 and min(labels) >= 4.5

    print(f"\n=== {mode} ===  monotonic L: {mono}   min |dL|: {min(abs(d) for d in dL):.3f}")
    print("  fills:", ",".join(ramp))
    print("  inks :", ",".join(inks))
    print("  L    :", [round(x, 3) for x in Ls])
    print("  label contrast:", [round(x, 2) for x in labels], " (WCAG AA floor 4.5)")
    print("  vs surface    :", [round(contrast(c, SURFACE[mode]), 2) for c in ramp],
          " (dear end relieved by the price label + table view)")
    print("  adjacent ΔE  normal / protan / deutan:")
    for i in range(6):
        n = delta_e(ramp[i], ramp[i + 1])
        p = delta_e(ramp[i], ramp[i + 1], "protan")
        d = delta_e(ramp[i], ramp[i + 1], "deutan")
        print(f"    q{i}-q{i+1}: {n:5.1f} / {p:5.1f} / {d:5.1f}")
    print("  cheapest vs dearest ΔE (deutan):",
          f"{delta_e(ramp[0], ramp[6], 'deutan'):.1f}  (near-poles q1-q5: "
          f"{delta_e(ramp[1], ramp[5], 'deutan'):.1f})")
    print("  CSS:")
    for i, (f, k) in enumerate(zip(ramp, inks)):
        print(f"    --q{i}: {f};  --qi{i}: {k};")
    return ok


if __name__ == "__main__":
    good = all(check(m, build(m)) for m in ("light", "dark"))
    print("\nOK" if good else "\nFAIL: a hard check did not pass")
    sys.exit(0 if good else 1)
