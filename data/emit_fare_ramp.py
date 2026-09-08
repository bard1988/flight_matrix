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

HUE = [158, 152, 148, 82, 46, 32, 22]        # green ... gold pivot ... warm red (deg)
# The gold pivot sits at 82, not 70. Protanopia collapses the red-green axis, so the
# green -> gold step is the weakest adjacency in the whole ramp under simulation; at hue 70
# it measured 2.3 dE, and moving the pivot to 82 lifts it to 2.8, slightly better than the
# 2.6 the previous ramp managed. This adjacency is why the monotonic-lightness rule and the
# printed price in every cell both exist: hue alone was never going to carry this step.

# The warm end asks for more chroma than sRGB can hold, so build() clips each step to 92%
# of the gamut boundary at its own lightness. Writing 0.26 for the dearest step is a way of
# saying "as saturated as this lightness allows", not a literal target.
#
# Why this matters: the dearest cell used to be #fbb7b4, a pale pink that made the board
# look cheap. That pink was not a choice. At its old lightness of 0.842 the gamut caps red
# chroma at 0.088, so it was ALREADY maxed out. Pale was a consequence of being light, and
# it was light because lightness has to climb monotonically for the ramp to survive hue
# loss. The only way to a redder red is a darker dear end, which costs lightness range.
CHR = [0.145, 0.150, 0.145, 0.125, 0.124, 0.180, 0.260]
L = {
    # cheap dark -> dear light. Range tightened from 0.435-0.842 to 0.400-0.790: deepening
    # the cheap end buys the headroom to pull the dear end down to a coral-red (#fa9d9a)
    # while still clearing the 0.06 minimum step. Every guarantee holds; nothing regresses.
    # A true red (#f8696b) needs L 0.700, which drops the step to 0.048 and adjacent CVD
    # separation from 6.8 to 5.3, so it was measured and rejected.
    "light": [0.400, 0.465, 0.530, 0.595, 0.660, 0.725, 0.790],
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


# --- the diverging alternative -----------------------------------------------------------
#
# The sequential ramp above is dullest at its ends, because sRGB caps chroma hardest at
# extreme lightness: measured, its cheapest step has the LOWEST chroma of all seven (0.086
# against 0.142 in the middle). So the most obviously green cell is a mid-priced one, not
# the cheapest, which is the opposite of what the board is for.
#
# This ramp puts vivid green at cheapest and vivid red at dearest, with the mid-price steps
# receding toward the canvas (pale on the light surface, dark on the near-black one).
#
# The cost is real and is why the sequential version existed. Lightness is no longer
# monotonic, so it cannot be checked the same way. A NAIVE symmetric diverging ramp is
# disqualifying: with both ends at equal lightness they are identical in greyscale, and
# cheapest-vs-dearest separation under deuteranopia collapses to 5.1 dE, meaning a
# red-green colour-blind user cannot tell the best date from the worst. Measured.
#
# So the arms are deliberately ASYMMETRIC: the dear end sits at a different lightness from
# the cheap end, which restores greyscale ranking and lifts end separation back to ~20 dE.
# Still below the sequential ramp's 39.7, and that is the trade being made knowingly. It is
# affordable only because colour was never the sole signal here: every cell prints its
# price, the cheapest carries a reserved-yellow marker, and destinations are ordered
# cheapest-first.
DIV_HUE = [155, 152, 148, 85, 40, 28, 25]
DIV_CHR = [0.17, 0.14, 0.10, 0.025, 0.10, 0.14, 0.18]
DIV_L = {
    # light: deep green -> cream middle -> clear red. Cream recedes into the warm canvas.
    "light": [0.420, 0.545, 0.670, 0.880, 0.730, 0.665, 0.600],
    # dark: bright green -> near-black middle -> bright red. The middle recedes again, this
    # time by going dark, so the same "extremes pop, middle steps back" logic holds.
    "dark": [0.740, 0.593, 0.447, 0.300, 0.373, 0.447, 0.520],
}

# Floors for the diverging ramp. Monotonic lightness is not one of them by design; the
# ends-apart checks stand in for it.
DIV_MIN_ENDS_DL = 0.12       # cheapest vs dearest must still rank in greyscale
DIV_MIN_ENDS_DE_CVD = 15.0   # ... and must stay far apart under deuteranopia


def build_diverging(mode: str) -> list[str]:
    out = []
    for Lv, Hv, Cv in zip(DIV_L[mode], DIV_HUE, DIV_CHR):
        cap = max_chroma(Lv, Hv * RAD) * 0.92
        out.append(to_hex(Lv, min(Cv, cap), Hv * RAD))
    return out


def check_diverging(mode: str, ramp: list[str]) -> bool:
    inks = [ink_for(c) for c in ramp]
    Ls = [hex_to_oklch(c)[0] for c in ramp]
    labels = [contrast(c, k) for c, k in zip(ramp, inks)]
    ends_dl = abs(Ls[0] - Ls[6])
    ends_de = delta_e(ramp[0], ramp[6], "deutan")
    worst_de = worst_adjacent_de(ramp)
    ok = (min(labels) >= 4.5 and worst_de >= MIN_ADJACENT_DE
          and ends_dl >= DIV_MIN_ENDS_DL and ends_de >= DIV_MIN_ENDS_DE_CVD)

    print(f"\n=== {mode} (diverging) ===")
    print("  fills:", ",".join(ramp))
    print("  inks :", ",".join(inks))
    print("  L    :", [round(x, 3) for x in Ls])
    print(f"  label contrast: {[round(x, 2) for x in labels]}  (AA floor 4.5)")
    print(f"  worst adjacent dE (any vision): {worst_de:.1f}  (floor {MIN_ADJACENT_DE})")
    print(f"  cheapest vs dearest |dL|: {ends_dl:.3f}  (floor {DIV_MIN_ENDS_DL}) "
          f"<- greyscale still ranks them")
    print(f"  cheapest vs dearest dE deutan: {ends_de:.1f}  (floor {DIV_MIN_ENDS_DE_CVD})")
    print("  CSS:")
    for i, (f, k) in enumerate(zip(ramp, inks)):
        print(f"    --q{i}: {f};  --qi{i}: {k};")
    return ok


# Floor for the weakest adjacent pair under ANY simulated vision (normal, protan, deutan).
# Set to what the previous ramp actually achieved, so the gate means "never ship worse
# separation than we already had". This check used to only PRINT the delta-E table while
# asserting on lightness and label contrast, which let a ramp with a 2.3 green-to-gold step
# report OK. Adjacency is the property most easily lost when retuning hue or chroma, so it
# is now a hard gate rather than a number for a human to notice.
MIN_ADJACENT_DE = 2.6


def worst_adjacent_de(ramp: list[str]) -> float:
    return min(
        min(delta_e(ramp[i], ramp[i + 1]),
            delta_e(ramp[i], ramp[i + 1], "protan"),
            delta_e(ramp[i], ramp[i + 1], "deutan"))
        for i in range(6)
    )


def check(mode: str, ramp: list[str]) -> bool:
    inks = [ink_for(c) for c in ramp]
    Ls = [hex_to_oklch(c)[0] for c in ramp]
    dL = [Ls[i + 1] - Ls[i] for i in range(6)]
    mono = all(d > 0 for d in dL) if mode == "light" else all(d < 0 for d in dL)
    labels = [contrast(c, k) for c, k in zip(ramp, inks)]
    worst_de = worst_adjacent_de(ramp)
    ok = (mono and min(abs(d) for d in dL) >= 0.06 and min(labels) >= 4.5
          and worst_de >= MIN_ADJACENT_DE)

    print(f"\n=== {mode} ===  monotonic L: {mono}   min |dL|: {min(abs(d) for d in dL):.3f}"
          f"   worst adjacent dE (any vision): {worst_de:.1f} (floor {MIN_ADJACENT_DE})")
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
    seq = [check(m, build(m)) for m in ("light", "dark")]
    div = [check_diverging(m, build_diverging(m)) for m in ("light", "dark")]
    good = all(seq) and all(div)
    print("\nOK (both ramps)" if good else "\nFAIL: a hard check did not pass")
    sys.exit(0 if good else 1)
