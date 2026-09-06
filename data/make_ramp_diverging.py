"""Derive the diverging green<->red price ramp, and a readable ink for each step.

The board encodes price as a diverging scale: green = cheap, neutral = mid, red = expensive.
Green/red is the worst pair for red-green colour blindness, so hue is deliberately NOT the
only signal - lightness ramps along each arm as well, which keeps the scale readable when
hue is lost. The midpoint is a low-chroma neutral rather than yellow, so yellow stays
reserved for the "cheapest cell" marker and cannot be confused with a mid-priced cell.

Also emits the ink colour per step (black or white, whichever has more contrast against
that fill), so cell labels stay legible without a hand-tuned flip index.

Run:  py -3 data/make_ramp_diverging.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_ramp import hex_to_oklch, max_chroma, to_hex  # noqa: E402

STEPS = 7  # must be odd so there is a true middle


def contrast(hex_a: str, hex_b: str) -> float:
    def lum(h: str) -> float:
        h = h.lstrip("#")
        chan = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            chan.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]

    a, b = lum(hex_a), lum(hex_b)
    lo, hi = min(a, b), max(a, b)
    return (hi + 0.05) / (lo + 0.05)


def ink_for(fill: str) -> str:
    """Black or white, whichever is more readable on this fill."""
    return "#0b0b0b" if contrast(fill, "#0b0b0b") >= contrast(fill, "#ffffff") else "#ffffff"


def build(cheap_anchor: str, dear_anchor: str, l_pole: float, l_mid: float,
          headroom: float = 0.94) -> list[str]:
    """Diverging ramp: saturated pole -> neutral middle -> saturated pole.

    Lightness moves monotonically along each arm, so each half also reads as an ordinary
    sequential ramp under colour-blind simulation.
    """
    _, _, hue_cheap = hex_to_oklch(cheap_anchor)
    _, _, hue_dear = hex_to_oklch(dear_anchor)
    half = STEPS // 2
    out: list[str] = []

    for i in range(STEPS):
        if i == half:
            out.append(to_hex(l_mid, 0.012, hue_cheap))     # near-neutral midpoint
            continue
        cheap_side = i < half
        hue = hue_cheap if cheap_side else hue_dear
        # 1.0 at the pole, approaching 0 at the middle
        t = (half - i) / half if cheap_side else (i - half) / half
        L = l_mid + (l_pole - l_mid) * t
        want = 0.03 + 0.17 * (t ** 0.75)
        out.append(to_hex(L, min(want, max_chroma(L, hue) * headroom), hue))
    return out


if __name__ == "__main__":
    # Light surface: poles are dark and saturated, middle is light and neutral.
    light = build("#008300", "#d03b3b", l_pole=0.50, l_mid=0.93)
    # Dark surface: mirrored - poles bright, middle recedes toward the surface.
    dark = build("#008300", "#d03b3b", l_pole=0.72, l_mid=0.36)

    for name, ramp in (("light", light), ("dark", dark)):
        print(f"{name}:")
        print("  fills:", ",".join(ramp))
        print("  inks :", ",".join(ink_for(c) for c in ramp))
        print("  L    :", [round(hex_to_oklch(c)[0], 3) for c in ramp])
        print("  C    :", [round(hex_to_oklch(c)[1], 3) for c in ramp])
        surface = "#fcfcfb" if name == "light" else "#1a1a19"
        print("  contrast vs surface:", [round(contrast(c, surface), 2) for c in ramp])
        print("  label contrast     :", [round(contrast(c, ink_for(c)), 2) for c in ramp])
        print()
