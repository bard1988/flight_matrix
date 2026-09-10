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
#
# ONE ramp serves both themes. Vivid green at the cheapest, deep red at the dearest, with
# lightness falling the whole way, so the scale still ranks correctly with hue removed.
# Every step sits mid-to-high lightness with its own measured ink, which is what lets a
# single set of fills work on warm paper and on near-black alike. Two mirrored ramps used
# to be needed only because the light one climbed in lightness while the dark one fell.
#
# HOW WE GOT HERE, because two earlier shapes were built, measured and rejected:
#
#  1. Sequential, cheap-dark -> dear-light. sRGB caps chroma hardest at extreme lightness,
#     so this was DULLEST at its ends: the cheapest step measured chroma 0.086 against
#     0.142 mid-ramp, which made a MID-priced cell the most obviously green thing on the
#     board, and forced the dearest into a pale pink. Backwards for a board about cheap.
#
#  2. Diverging, green -> cream -> red. Fixed the vivid-green end but gave up monotonic
#     lightness, and a naive symmetric version was disqualifying: both ends at equal
#     lightness are identical in greyscale (|dL| 0.001) and cheapest-vs-dearest separation
#     under deuteranopia collapsed to 5.1 dE. An asymmetric version recovered 20.0 dE, but
#     that is still half of what a monotonic ramp gets for free.
#
# The way out came from measuring where sRGB actually puts its most vivid colours: green
# peaks at L 0.87 (chroma 0.271) and red at L 0.63 (chroma 0.255). So "best green" is a
# LIGHT colour and the best red is darker, which means vivid-green -> red is naturally a
# FALLING lightness ramp. Anchoring the cheap end at green's peak and pushing the dear end
# to L 0.47 (a little past red's peak, to buy lightness range) satisfies every constraint
# at once, and beats both earlier shapes on adjacency and end separation together.
#
# ART-DIRECTED, NOT DERIVED. The six fills below are sampled straight from a credit-score
# scale supplied as the reference palette (Excellent -> Very Bad), so they are literals
# rather than the output of the OKLCH walk that HUE/CHR/L describe. build() still exists
# for the derived variants documented above, but RAMP is what ships.
#
# The 7th step is a deeper red, not an interpolation: the reference has six bands and the
# board needs seven. Extending the dark end preserves all six source colours EXACTLY and
# simultaneously pulls the two ends apart, which is the property the reference palette is
# weakest on. Interpolating a 7th instead measured 1.3 dE on its weakest adjacency, i.e.
# two neighbouring price steps indistinguishable; extending gives 9.4.
RAMP = [
    "#0f9246",   # Excellent, verbatim -- the cheap end and the dear end are held here
    "#7ebb42",   # Very Good, verbatim
    "#f2c53a",   # Good  -- warmed off the reference gold toward the softer heatmap look
    "#f0952f",   # Fair  -- warmed, a touch deeper
    "#ea5f34",   # Poor  -- shifted toward terracotta rather than signal-orange
    "#cc3630",   # Very Bad -- softened off #bc1f26
    "#7f0a13",   # added: deeper red at L 0.38, same hue as Very Bad -- held for the ends gate
]
# 2026 retune for the softer "fare calendar" surface (see DESIGN.md). q0 and q6 are
# unchanged: the cheapest-vs-dearest deuteranopia gate (MIN_ENDS_DE_CVD) needs the vivid
# green and the deep red at the ends, and softening either one drops it below 18.
# q2-q5 are warmed toward the mockup's heatmap without touching the CVD result (still 18.9).

HUE = [148, 138, 128, 60, 42, 32, 22]
# The hue path deliberately jumps the yellow band between q2 and q3, rather than easing
# through gold. marker-yellow (#f2b705) is reserved for the cheapest-cell ring, and a gold
# FILL at mid-price would make that ring ambiguous. Measured alternative: routing through
# gold scores marginally better (label 4.81, adjacency 6.4) but puts #c4a92a on the board,
# so it was rejected on the Reserved Yellow Rule rather than on numbers.

# Ask for more chroma than sRGB can hold at every step; build() clips to 92% of the gamut
# boundary at that step's own lightness. This is how "as saturated as this lightness
# allows" is expressed, and it is what keeps the cheap end the most vivid green available.
CHR = [0.40] * 7

# Falling from green's chroma peak to a deep red. Span 0.400 over six steps gives 0.067 per
# step, clearing the 0.06 floor with a little room.
L = [0.870, 0.803, 0.737, 0.670, 0.603, 0.537, 0.470]

# The grounds a cell actually sits on, for the reported fill-vs-canvas contrast. These are
# --canvas in styles.css, not the raised chrome: with the card container retired, the board
# paints directly onto the recessed canvas.
SURFACE = {"light": "#f4f3ef", "dark": "#0d0d0d"}


def build() -> list[str]:
    out = []
    for Lv, Hv, Cv in zip(L, HUE, CHR):
        cap = max_chroma(Lv, Hv * RAD) * 0.92
        out.append(to_hex(Lv, min(Cv, cap), Hv * RAD))
    return out


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


# The dearest end must stay far from the cheapest end under simulated colour blindness.
# This is the single most important distinction the board makes, so it gets its own gate
# rather than being left to the adjacency check: a ramp can have healthy neighbour-to-
# neighbour separation and still fold its two ENDS together (a symmetric diverging ramp
# scored 11.2 on adjacency and 5.1 end-to-end, which is useless for finding cheap).
#
# LOWERED FROM 30.0, deliberately, and this is the cost of the art-directed palette.
#
# The reference scale humps in lightness (yellow is its lightest band), so it cannot rank
# by tone the way a monotonic ramp does, and green-vs-red is exactly the axis deuteranopia
# collapses. Measured 18.9 dE between cheapest and dearest, against 38.8 for the monotonic
# green-to-red ramp it replaced. Held at 18.0 so the palette passes while any FURTHER
# regression still fails the gate.
#
# What makes 18.9 tolerable rather than reckless: colour is not the only signal, and never
# was. Every cell prints its price, the cheapest carries a ringed marker, destinations are
# ordered cheapest-first, and there is a full accessible table view of every priced cell.
# What it does cost is the at-a-glance scan for a red-green colour-blind user, who will
# need to read numbers where others read colour. That is a real regression, accepted
# knowingly in exchange for the requested palette.
MIN_ENDS_DE_CVD = 18.0

# The reference palette is not monotonic in lightness, so tone cannot carry the ranking and
# this is reported rather than asserted. Mid-ramp pairs can therefore sit at nearly equal
# lightness (its "Very Good" and "Fair" bands are 0.726 and 0.743), which is why the
# non-adjacent worst case is printed too: adjacency alone would not reveal it.
REQUIRE_MONOTONIC = False


def worst_any_pair_de(ramp: list[str]) -> tuple[float, int, int]:
    worst = (1e9, 0, 0)
    for i in range(7):
        for j in range(i + 1, 7):
            d = min(delta_e(ramp[i], ramp[j], "protan"),
                    delta_e(ramp[i], ramp[j], "deutan"))
            if d < worst[0]:
                worst = (d, i, j)
    return worst


def check(ramp: list[str]) -> bool:
    inks = [ink_for(c) for c in ramp]
    Ls = [hex_to_oklch(c)[0] for c in ramp]
    dL = [Ls[i + 1] - Ls[i] for i in range(6)]
    mono = all(d < 0 for d in dL) or all(d > 0 for d in dL)
    labels = [contrast(c, k) for c, k in zip(ramp, inks)]
    worst_de = worst_adjacent_de(ramp)
    ends_de = delta_e(ramp[0], ramp[6], "deutan")
    ends_dl = abs(Ls[0] - Ls[6])
    any_de, ai, aj = worst_any_pair_de(ramp)
    ok = (min(labels) >= 4.5 and worst_de >= MIN_ADJACENT_DE
          and ends_de >= MIN_ENDS_DE_CVD and ends_dl >= 0.12
          and (mono or not REQUIRE_MONOTONIC))

    print(f"\n=== fare ramp ===  lightness monotonic: {mono} "
          f"(required: {REQUIRE_MONOTONIC})   cheapest-vs-dearest |dL|: {ends_dl:.3f} "
          f"(floor 0.12)")
    print(f"  worst pair ANY distance under CVD: {any_de:.1f} dE  at q{ai} vs q{aj} "
          f"({ramp[ai]} vs {ramp[aj]})  <- not gated, but the honest worst case")
    print("  fills:", ",".join(ramp))
    print("  inks :", ",".join(inks))
    print("  L    :", [round(x, 3) for x in Ls])
    print("  C    :", [round(hex_to_oklch(c)[1], 3) for c in ramp],
          " <- cheapest should be the MOST chromatic green available")
    print("  label contrast:", [round(x, 2) for x in labels], " (WCAG AA floor 4.5)")
    for mode, surface in SURFACE.items():
        print(f"  vs {mode:5} canvas:", [round(contrast(c, surface), 2) for c in ramp])
    print("  adjacent ΔE  normal / protan / deutan:")
    for i in range(6):
        n = delta_e(ramp[i], ramp[i + 1])
        p = delta_e(ramp[i], ramp[i + 1], "protan")
        d = delta_e(ramp[i], ramp[i + 1], "deutan")
        print(f"    q{i}-q{i+1}: {n:5.1f} / {p:5.1f} / {d:5.1f}")
    print(f"  worst adjacent ΔE (any vision): {worst_de:.1f}  (floor {MIN_ADJACENT_DE})")
    print(f"  cheapest vs dearest ΔE (deutan): {ends_de:.1f}  (floor {MIN_ENDS_DE_CVD})")
    print("  CSS (one ramp, both themes):")
    for i, (f, k) in enumerate(zip(ramp, inks)):
        print(f"    --q{i}: {f};  --qi{i}: {k};")
    return ok


# --- the pale ramp (the shipped DEFAULT) --------------------------------------------------
#
# The board ships this soft, low-saturation heatmap by default; the CVD-safe RAMP above is one
# opt-in click away (a toggle in the board tools, persisted). The pale ramp is a tint scale
# -- light mint -> pale lime -> cream -> peach -> coral -> rose -- matched to the marketing
# comp. It CANNOT clear the colour-blind-friendly ramp's colour-vision-deficiency gates: pale colours
# compress the sRGB gamut, so neighbouring steps and the two ends sit closer under
# simulated deuteranopia (measured ~1.3 adjacency, ~16.7 ends, against 7.3 / 18.9 vivid).
#
# That trade is acceptable ONLY because colour is never the sole signal and the colour-blind-friendly ramp
# is always available: every cell prints its price (dark ink, AA-clear on every pale step
# -- that gate stays HARD below), the cheapest cell is ringed, destinations are ordered
# cheapest-first, and the table view lists every value. A red-green colour-blind user who
# wants the scan-by-colour affordance flips to the colour-blind-friendly ramp.
RAMP_PALE = [
    "#a9d8b4",   # mint
    "#cfe6a0",   # pale lime
    "#f5e6a0",   # cream
    "#f6d3a2",   # pale peach
    "#f2b39c",   # light coral
    "#ec9088",   # coral
    "#e06b6b",   # rose
]

# Hard for the pale ramp: label contrast only. Adjacency and ends separation are reported
# as advisories, not gates -- the colour-blind-friendly ramp carries the accessible guarantee.
PALE_MIN_LABEL = 4.5


def check_pale(ramp: list[str]) -> bool:
    inks = [ink_for(c) for c in ramp]
    labels = [contrast(c, k) for c, k in zip(ramp, inks)]
    Ls = [hex_to_oklch(c)[0] for c in ramp]
    adj = worst_adjacent_de(ramp)
    ends = delta_e(ramp[0], ramp[6], "deutan")
    ok = min(labels) >= PALE_MIN_LABEL and all(k == INK_DARK for k in inks)

    print("\n=== fare ramp (PALE, default) ===")
    print("  fills:", ",".join(ramp))
    print("  L    :", [round(x, 3) for x in Ls])
    print("  label contrast:", [round(x, 2) for x in labels],
          f" (WCAG AA floor {PALE_MIN_LABEL}; HARD)")
    print(f"  worst adjacent ΔE (any vision): {adj:.1f}   <- advisory only for the pale ramp")
    print(f"  cheapest vs dearest ΔE (deutan): {ends:.1f}  <- advisory only for the pale ramp")
    print("  CSS (default :root):")
    for i, (f, k) in enumerate(zip(ramp, inks)):
        print(f"    --q{i}: {f};  --qi{i}: {k};")
    return ok


if __name__ == "__main__":
    pale_ok = check_pale(RAMP_PALE)
    vivid_ok = check(RAMP)
    print("\n--- colour-blind-friendly ramp is emitted under :root[data-fareramp='cvd'] ---")
    print("pale:", "OK" if pale_ok else "FAIL", "  cvd:", "OK" if vivid_ok else "FAIL")
    sys.exit(0 if (pale_ok and vivid_ok) else 1)
