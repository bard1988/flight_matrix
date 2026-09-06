"""Emit the final diverging green<->red ramp as CSS custom properties.

Arms are deliberately ASYMMETRIC in lightness. Measured with Machado-Oliveira-Fernandes
severity 1.0: symmetric arms give a deuteranopia Delta E of 0.7-1.5 between the mirrored
pairs, i.e. cheapest and dearest are indistinguishable to a red-green colour-blind reader
despite a normal-vision Delta E of 30. Pushing the green arm dark and the red arm light
lifts the worst mirrored pair to ~7 and the poles to 19-31, so the scale survives when hue
is lost. Every cell also carries its price as text, which is the real backstop.

Run:  py -3 data/emit_ramp_css.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_ramp import hex_to_oklch  # noqa: E402
from make_ramp_diverging import build, contrast, ink_for  # noqa: E402


def arms(cheap: str, dear: str, l_cheap: float, l_dear: float, l_mid: float) -> list[str]:
    mid = build(cheap, dear, l_cheap, l_mid)[3]
    left = build(cheap, cheap, l_cheap, l_mid)[:3]
    right = build(dear, dear, l_dear, l_mid)[:3][::-1]
    return left + [mid] + right


GREEN, RED = "#008300", "#d03b3b"
RAMPS = {
    # light surface: cheap = dark green, mid = near-white neutral, dear = light red
    "light": arms(GREEN, RED, l_cheap=0.40, l_dear=0.70, l_mid=0.93),
    # dark surface: mirrored about the dark surface, same asymmetry
    "dark": arms(GREEN, RED, l_cheap=0.78, l_dear=0.52, l_mid=0.34),
}
SURFACE = {"light": "#fcfcfb", "dark": "#1a1a19"}

for mode, ramp in RAMPS.items():
    inks = [ink_for(c) for c in ramp]
    print(f"/* {mode} */")
    for i, (fill, ink) in enumerate(zip(ramp, inks)):
        print(f"  --q{i}: {fill};  --qi{i}: {ink};")
    print(f"  /* L: {[round(hex_to_oklch(c)[0], 2) for c in ramp]}")
    print(f"     label contrast: {[round(contrast(c, i), 2) for c, i in zip(ramp, inks)]}")
    print(f"     vs surface:     {[round(contrast(c, SURFACE[mode]), 2) for c in ramp]} */")
    print()
