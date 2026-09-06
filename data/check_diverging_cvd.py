"""How distinguishable are the two arms of the green<->red ramp under colour blindness?

The danger with a diverging green/red scale is that the mirrored pairs (cheapest vs
dearest) land on the same lightness and become identical once hue is lost. Measure the
mirrored pairs, and try asymmetric lightness to separate them.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path("C:/Users/BDUBOV~1/AppData/Local/Temp/claude/bundled-skills/2.1.251/"
             "bc617ad343d01a2a4ea5687a59511fa4/dataviz/scripts")
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_palette as vp  # noqa: E402
from make_ramp_diverging import build, ink_for  # noqa: E402


def report(label: str, ramp: list[str], surface: str) -> float:
    print(f"\n{label}")
    print("  ", ",".join(ramp))
    worst = 99.0
    n = len(ramp)
    for i in range(n // 2):
        j = n - 1 - i
        a, b = ramp[i], ramp[j]
        normal = vp.deltaE(a, b)
        prot = vp.deltaE(a, b, "protan")
        deut = vp.deltaE(a, b, "deutan")
        worst = min(worst, prot, deut)
        flag = "OK " if min(prot, deut) >= 8 else ("weak" if min(prot, deut) >= 6 else "FAIL")
        print(f"   q{i} vs q{j}: normal {normal:5.1f}  protan {prot:5.1f}  deutan {deut:5.1f}  {flag}")
    labels = [round(vp.contrast(c, ink_for(c)), 2) for c in ramp]
    print(f"   worst CVD pair {worst:.1f} | label contrast min {min(labels):.2f}")
    return worst


# Symmetric arms: the natural diverging shape.
report("symmetric (light)", build("#008300", "#d03b3b", 0.50, 0.93), "#fcfcfb")

# Asymmetric: push the arms apart in lightness so greyscale alone separates them.
for gl, rl in ((0.45, 0.62), (0.42, 0.66), (0.40, 0.70)):
    ramp = build("#008300", "#d03b3b", 0.50, 0.93)
    # rebuild each arm at its own pole lightness
    left = build("#008300", "#008300", gl, 0.93)[: len(ramp) // 2]
    right = build("#d03b3b", "#d03b3b", rl, 0.93)[: len(ramp) // 2][::-1]
    mixed = left + [ramp[len(ramp) // 2]] + right
    report(f"asymmetric green L={gl} red L={rl} (light)", mixed, "#fcfcfb")
