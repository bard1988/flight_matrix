"""Build the FlightMatrix brand SVGs.

Run after changing any geometry or copy:

    py brand/build_logo.py

Two things are deliberately resolved at build time rather than left to the renderer:

* The wordmark is converted to outlines, so the shipped files render identically on
  machines without the source font. Source face is Bahnschrift (the Windows DIN),
  instanced from its variable font at wght 700 for the wordmark, 500 for the tagline.
  DIN earns its place here: it is the transport-signage grotesque, and this is a fare board.
* The aircraft's rotation and scale are baked into its path coordinates. Chromium
  mis-carves a <mask> whose contents carry a rotate/scale transform, which left holes in
  the grid well away from the aircraft, so the masks here contain no transforms at all.
"""

import math
import pathlib
import re

from fontTools.misc.transform import Offset
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONT = pathlib.Path(r"C:\Windows\Fonts\bahnschrift.ttf")
OUT = pathlib.Path(__file__).parent
APP = OUT.parent / "frontend"    # served at /static, so app-facing copies have to live here

NAVY = "#0F3D73"
# A deep green-leaning teal, chosen over a brighter turquoise because the accent has two
# jobs that pull opposite ways: inside the mark it needs to separate from the navy, and in
# the wordmark it has to hold MATRIX at the same optical weight as FLIGHT against the
# off-white. Bright turquoise wins the first and loses the second badly (1.88:1 on paper).
# This sits at 3.06:1 on paper and 3.19:1 on navy, and its hue stays far from navy's.
ACCENT = "#0E9E77"
PAPER = "#F4F3EF"   # stands in for the navy on a near-black ground, where navy dies

WORD_A = "FLIGHT"            # set in the ink colour
WORD_B = "MATRIX"            # set in the accent
WORDMARK = WORD_A + WORD_B
TAGLINE = "SEARCH COMPARE FLY"

# --- mark geometry, in a 240x240 local box -----------------------------------------
CELLS = 4
STEP = 60
SPAN = CELLS * STEP          # 240
NODE_R = 13
GRID_W = 7
PATH_W = 10
PLANE_AT = (152, 88)         # sits on the 45-degree line y = 240 - x
PLANE_SCALE = 1.0
PLANE_GAP = 6                # clear space carved out of the grid around the aircraft
MONO_GAP = 4                 # clear space carved around the path too, single-ink only
PLANE_HALF = 66              # the aircraft path's half-length, nose to tail
LINE_BACK = 25               # where the path stops, measured back from the aircraft's
                             # centre. Well inside PLANE_HALF, so the path runs up under
                             # the fuselage and joins the aircraft with no seam.

# Aircraft in plan view, nose up, centred on the origin. Length 130, span 126.
# A slim spindle fuselage with a blunt-tipped tapered nose, thin hard-swept wings with
# blunt tips, and a small matching tailplane. Two things matter to the read: the wing
# root chord stays short, because broad wings turn the silhouette into a moth, and the
# fuselage runs straight for a stretch before each wing so the root reads as a definite
# angled junction rather than the nose flowing into the wing.
PLANE = (
    "M 0 -64 C 5 -63 8 -52 9 -42 L 10 -18 L 58 8 Q 63 12 57 16 L 12 14 L 9 44 "
    "L 24 58 Q 27 61 22 63 L 6 60 Q 2 64 0 66 Q -2 64 -6 60 L -22 63 Q -27 61 -24 58 "
    "L -9 44 L -12 14 L -57 16 Q -63 12 -58 8 L -10 -18 L -9 -42 C -8 -52 -5 -63 0 -64 Z"
)

# Same aircraft with the tailplane's trailing notch closed up, for the small-size icons
# where that detail is sub-pixel anyway and only muddies the silhouette.
PLANE_SM = (
    "M 0 -64 C 5 -63 8 -52 9 -42 L 10 -18 L 58 8 Q 63 12 57 16 L 12 14 L 10 46 "
    "L 25 60 Q 28 63 22 65 L 0 66 L -22 65 Q -28 63 -25 60 L -10 46 L -12 14 "
    "L -57 16 Q -63 12 -58 8 L -10 -18 L -9 -42 C -8 -52 -5 -63 0 -64 Z"
)

# The shape used to carve clear space, not to draw: the aircraft with both concave
# pockets closed off by a straight edge, the one ahead of each wing root and the one
# between each wing and tailplane. Carving the true outline instead leaves slivers of
# grid line stranded inside those pockets, which read as dirt.
PLANE_MASK = (
    "M 0 -64 C 5 -63 8 -52 9 -42 L 58 8 Q 63 12 57 16 L 22 63 L 6 60 Q 2 64 0 66 "
    "Q -2 64 -6 60 L -22 63 L -57 16 Q -63 12 -58 8 L -9 -42 C -8 -52 -5 -63 0 -64 Z"
)

TOKEN = re.compile(r"([MLCQZ])([^MLCQZ]*)")
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def bake(d, tx, ty, deg, scale):
    """Apply translate/rotate/scale to a path's coordinates, returning new path data.

    Only absolute M/L/C/Q/Z are handled, which is all the aircraft uses."""
    cos, sin = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    out = []
    for cmd, rest in TOKEN.findall(d):
        if cmd == "Z":
            out.append("Z")
            continue
        n = [float(v) for v in NUMBER.findall(rest)]
        pts = []
        for x, y in zip(n[::2], n[1::2]):
            x, y = x * scale, y * scale
            pts.append(f"{tx + x * cos - y * sin:.2f} {ty + x * sin + y * cos:.2f}")
        out.append(f"{cmd} " + " ".join(pts))
    return " ".join(out)


# --- type ---------------------------------------------------------------------------
def load(weight):
    return instancer.instantiateVariableFont(
        TTFont(FONT), {"wght": weight, "wdth": 100}, inplace=False, updateFontNames=False
    )


def outline(font, text, tracking=0.0, space_extra=0.0):
    """Return (svg path data, advance width) in font units, y-up."""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}")
    x = 0.0
    for i, ch in enumerate(text):
        glyphs[cmap[ord(ch)]].draw(TransformPen(pen, Offset(x, 0)))
        x += glyphs[cmap[ord(ch)]].width
        if i < len(text) - 1:
            x += tracking + (space_extra if ch == " " or text[i + 1] == " " else 0.0)
    return pen.getCommands(), x


def solve_tracking(font, text, target_units, space_ratio=0.6):
    """Tracking that makes `text` span exactly target_units, word gaps opened extra."""
    natural = outline(font, text)[1]
    gaps = len(text) - 1
    sides = sum(1 for i, ch in enumerate(text[:-1]) if ch == " " or text[i + 1] == " ")
    t = (target_units - natural) / (gaps + space_ratio * sides)
    return t, t * space_ratio


# --- mark ---------------------------------------------------------------------------
def line_end(ox, oy, back=LINE_BACK):
    """Where the flight path stops, `back` path-units down-line of the aircraft."""
    k = math.cos(math.radians(45)) * back * PLANE_SCALE
    return ox + PLANE_AT[0] - k, oy + PLANE_AT[1] + k


def mark(navy, teal, ox, oy, mask_id=None):
    """The mark, with every coordinate absolute in the page's own space."""
    m = f' mask="url(#{mask_id})"' if mask_id else ""
    ex, ey = line_end(ox, oy)
    h = "".join(f"M{ox} {oy + i * STEP}H{ox + SPAN}" for i in range(CELLS + 1))
    v = "".join(f"M{ox + i * STEP} {oy}V{oy + SPAN}" for i in range(CELLS + 1))
    dots = "\n".join(
        "      "
        + "".join(
            f'<circle cx="{ox + c * STEP}" cy="{oy + r * STEP}" r="{NODE_R}"/>'
            for c in range(CELLS + 1)
        )
        for r in range(CELLS + 1)
    )
    # Painted back to front: the path first, so the grid crosses over it and it reads as
    # running underneath the board; then the grid, carved back around the aircraft; then
    # the aircraft on top, which also hides where the path runs up under the fuselage.
    return f"""    <path d="M{ox} {oy + SPAN}L{ex:.2f} {ey:.2f}" fill="none" stroke="{teal}" stroke-width="{PATH_W}" stroke-linecap="round"/>
    <g{m} fill="none" stroke="{navy}" stroke-width="{GRID_W}">
      <path d="{h}"/>
      <path d="{v}"/>
    </g>
    <g{m} fill="{navy}">
{dots}
    </g>
    <path d="{bake(PLANE, ox + PLANE_AT[0], oy + PLANE_AT[1], 45, PLANE_SCALE)}" fill="{teal}"/>"""


def gap_mask(mask_id, w, h, ox, oy, plane_gap, line_gap=None):
    """Hides the grid near the aircraft, and optionally near the path as well.

    The aircraft always gets clear space: overlapping it directly on the grid reads as
    two graphics stacked rather than one object. The path only needs the same treatment
    in single ink, where it would otherwise be indistinguishable from a grid line."""
    ex, ey = line_end(ox, oy)
    line = (
        f'\n      <path d="M{ox} {oy + SPAN}L{ex:.2f} {ey:.2f}" fill="none" stroke="#000"'
        f' stroke-width="{PATH_W + 2 * line_gap}" stroke-linecap="round"/>'
        if line_gap
        else ""
    )
    return f"""  <defs>
    <mask id="{mask_id}" maskUnits="userSpaceOnUse" x="0" y="0" width="{w}" height="{h}">
      <rect width="{w}" height="{h}" fill="#fff"/>{line}
      <path d="{bake(PLANE_MASK, ox + PLANE_AT[0], oy + PLANE_AT[1], 45, PLANE_SCALE)}" fill="#000" stroke="#000" stroke-width="{2 * plane_gap}" stroke-linejoin="round"/>
    </mask>
  </defs>
"""


def small_mark(ox, oy, box, inset, cells, stroke, node_r, path_w, plane_scale,
               clear, line_back, ink, gap=0.0, mask_id="fm-gap"):
    """A reduction of the mark, drawn at ox,oy in the page's own space.

    The 4x4 matrix does not survive being shrunk, so the cell count drops with the
    canvas: 2x2 at 32px, and at 16px the interior lines go entirely and the bare square
    with its four corner nodes carries the matrix read. What survives at every size is
    the corner-to-corner accent path and the 45-degree climb.

    Returns (defs, body). `gap` of 0 skips the carve, which is right below about 40px
    where the clear space would be sub-pixel anyway."""
    lo_x, lo_y = ox + inset, oy + inset
    hi_x, hi_y = ox + box - inset, oy + box - inset
    step = (box - 2 * inset) / cells
    cos45 = math.cos(math.radians(45))
    # Slide the aircraft up the line until its nose stops `clear` units short of the
    # top-right corner, which has to be enough to miss the corner node.
    d = (box - inset) - clear - box / 2 - cos45 * PLANE_HALF * plane_scale
    at = (ox + box / 2 + d, oy + box / 2 - d)
    k = cos45 * line_back * plane_scale
    end = (at[0] - k, at[1] + k)
    plane = bake(PLANE_SM, at[0], at[1], 45, plane_scale)
    lines = "".join(
        f"M{lo_x:g} {lo_y + i * step:g}H{hi_x:g}" for i in range(cells + 1)
    ) + "".join(f"M{lo_x + i * step:g} {lo_y:g}V{hi_y:g}" for i in range(cells + 1))
    dots = "".join(
        f'<circle cx="{lo_x + c * step:g}" cy="{lo_y + r * step:g}" r="{node_r}"/>'
        for r in range(cells + 1)
        for c in range(cells + 1)
    )
    defs = (
        f"""  <defs>
    <mask id="{mask_id}" maskUnits="userSpaceOnUse">
      <rect x="{ox}" y="{oy}" width="{box}" height="{box}" fill="#fff"/>
      <path d="{bake(PLANE_MASK, at[0], at[1], 45, plane_scale)}" fill="#000" stroke="#000" stroke-width="{2 * gap}" stroke-linejoin="round"/>
    </mask>
  </defs>
"""
        if gap
        else ""
    )
    m = f' mask="url(#{mask_id})"' if gap else ""
    body = f"""  <path d="M{lo_x:g} {hi_y:g}L{end[0]:.2f} {end[1]:.2f}" fill="none" stroke="{ACCENT}" stroke-width="{path_w}" stroke-linecap="round"/>
  <path{m} d="{lines}" fill="none" stroke="{ink}" stroke-width="{stroke}"/>
  <g{m} fill="{ink}">{dots}</g>
  <path d="{plane}" fill="{ACCENT}"/>"""
    return defs, body


def icon(box, inset, cells, stroke, node_r, path_w, plane_scale, gap=0.0, clear=0.5,
         line_back=LINE_BACK, ink="currentColor", auto=True):
    defs, body = small_mark(0, 0, box, inset, cells, stroke, node_r, path_w,
                            plane_scale, clear, line_back, ink, gap)
    return f"""{head(box, box, "FlightMatrix", auto)}
  <!-- {box}px reduction of the mark. Generated by build_logo.py. -->
{defs}{body}
</svg>
"""


def head(w, h, label, auto):
    """Open the svg element, optionally theme-adaptive.

    Adaptive files paint their ink with currentColor and resolve it in three layers, each
    beating the one before, so the same file works everywhere:

      1. a `color` presentation attribute, for rasterisers that ignore <style> entirely;
      2. the internal stylesheet below, which is what makes the file follow the viewer's
         colour scheme when it is loaded as an image (<img src>, favicon, README);
      3. any host rule, because the internal selectors are wrapped in :where() and so
         carry zero specificity. Inline this in the app and `svg.fm-auto { color: ... }`
         wins, which is what a manual [data-theme] toggle needs, since a media query
         cannot see an attribute on the host document.

    The class is what scopes it: inlining a stylesheet that matched bare `svg` would
    leak the rule onto every other svg on the page."""
    if not auto:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{label}">'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" class="fm-auto" color="{NAVY}" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">
  <style>
    :where(.fm-auto){{color:{NAVY}}}
    @media (prefers-color-scheme:dark){{:where(.fm-auto){{color:{PAPER}}}}}
  </style>"""


def write(name, text, where=None):
    path = (where or OUT) / name
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")
    print("wrote", path.relative_to(OUT.parent).as_posix())


def inject(path, marker, payload):
    """Replace whatever sits between <!-- marker:start --> and <!-- marker:end -->.

    The header logo has to be inlined rather than referenced with <img>, because the app
    themes off `data-theme` on <html> and an image cannot see that. Inlining lets the
    mark inherit `color` from the page, so it tracks --text-primary through both the
    media query and the manual toggle. Injecting it here is what keeps that copy from
    drifting away from the generated one."""
    src = path.read_text(encoding="utf-8")
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    i, j = src.find(start), src.find(end)
    if i < 0 or j < 0:
        raise SystemExit(f"{path.name}: missing {start} or {end}")
    out = src[: i + len(start)] + payload + src[j:]
    if out != src:
        path.write_text(out, encoding="utf-8")
        print(f"injected {marker} -> {path.relative_to(OUT.parent).as_posix()}")


def main():
    bold, medium = load(700), load(500)
    upem = bold["head"].unitsPerEm
    cap = bold["OS/2"].sCapHeight

    pad = 30
    size = SPAN + 2 * pad

    for name, ink, auto in (
        ("flightmatrix-mark.svg", "currentColor", True),
        ("flightmatrix-mark-dark.svg", PAPER, False),
    ):
        write(
            name,
            f"""{head(size, size, "FlightMatrix", auto)}
  <!-- A 4x4 fare matrix, with a green flight path traced across it from the bottom-left
       corner node and an aircraft riding that path. The grid is carved back around the
       aircraft so the two read as one object. Generated by build_logo.py. -->
{gap_mask("fm-gap", size, size, pad, pad, PLANE_GAP)}{mark(ink, ACCENT, pad, pad, mask_id="fm-gap")}
</svg>
""",
        )

    write(
        "flightmatrix-mark-mono.svg",
        f"""{head(size, size, "FlightMatrix", False)}
  <!-- Single-ink silhouette, accent included: for one-colour print, engraving, stamps.
       Declares no colour at all, so it inherits whatever `color` is in force; set
       color:#0b0b0b on a light ground, color:#f4f3ef on near-black. That means it only
       resolves when inlined in the DOM or used as a CSS mask, never through <img src>.
       For a file that adapts by itself, use flightmatrix-mark.svg instead. The carved gap
       around the path and the aircraft is what keeps them legible once the hue separation
       is gone. Generated by build_logo.py. -->
{gap_mask("fm-gap", size, size, pad, pad, PLANE_GAP, line_gap=MONO_GAP)}{mark("currentColor", "currentColor", pad, pad, mask_id="fm-gap")}
</svg>
""",
    )

    # --- horizontal lockup ----------------------------------------------------------
    margin = 40
    mark_x = margin + NODE_R          # the outermost nodes, not the strokes, set the margin
    text_x = mark_x + SPAN + NODE_R + 88

    word_cap = 62.0
    word_scale = word_cap / cap
    # Set as two runs so MATRIX can carry the accent, but spaced as if it were one word:
    # the second run starts one tracking step after the first run's advance, so the
    # letterfit across the T-M seam is identical to setting FLIGHTMATRIX in one go.
    track = 20
    word_a_d, word_a_adv = outline(bold, WORD_A, tracking=track)
    word_b_d, word_b_adv = outline(bold, WORD_B, tracking=track)
    word_b_x = text_x + (word_a_adv + track) * word_scale
    word_w = (word_a_adv + track + word_b_adv) * word_scale

    dot_r, dot_gap, tag_cap = 9.0, 20.0, 24.0
    tag_scale = tag_cap / cap
    t, se = solve_tracking(medium, TAGLINE, (word_w - dot_gap - 2 * dot_r) / tag_scale)
    tag_d, _ = outline(medium, TAGLINE, tracking=t, space_extra=se)

    canvas_w = text_x + word_w + margin
    canvas_h = SPAN + 2 * NODE_R + 2 * margin
    axis = canvas_h / 2
    block_h = word_cap + 14 + tag_cap
    word_base = axis - block_h / 2 + word_cap
    tag_base = axis + block_h / 2

    def lockup(ink, auto):
        return f"""{head(f"{canvas_w:.0f}", f"{canvas_h:.0f}", "FlightMatrix - Search Compare Fly", auto)}
  <!-- Horizontal lockup: mark left, type right, both centred on one axis. Wordmark and
       tagline are flush at both edges, the tagline letterspaced to the wordmark's
       measure. Type is outlined, so no font is required. Generated by build_logo.py. -->
{gap_mask("fm-gap", f"{canvas_w:.0f}", f"{canvas_h:.0f}", mark_x, margin + NODE_R, PLANE_GAP)}{mark(ink, ACCENT, mark_x, margin + NODE_R, mask_id="fm-gap")}
  <g fill="{ink}">
    <path transform="translate({text_x:.1f} {word_base:.1f}) scale({word_scale:.6f} -{word_scale:.6f})" d="{word_a_d}"/>
    <path transform="translate({text_x:.1f} {tag_base:.1f}) scale({tag_scale:.6f} -{tag_scale:.6f})" d="{tag_d}"/>
  </g>
  <path fill="{ACCENT}" transform="translate({word_b_x:.1f} {word_base:.1f}) scale({word_scale:.6f} -{word_scale:.6f})" d="{word_b_d}"/>
  <circle cx="{text_x + word_w - dot_r:.1f}" cy="{tag_base - dot_r:.1f}" r="{dot_r}" fill="{ACCENT}"/>
</svg>
"""

    write("flightmatrix-lockup.svg", lockup("currentColor", True))
    write("flightmatrix-lockup-dark.svg", lockup(PAPER, False))

    # --- small-size icons -----------------------------------------------------------
    write(
        "flightmatrix-icon-32.svg",
        icon(32, 5.0, 2, 1.7, 2.1, 2.6, 0.125, gap=0.9, clear=3.2),
    )
    write("flightmatrix-icon-16.svg", icon(16, 2.6, 1, 1.5, 1.9, 1.8, 0.070, clear=2.0))

    # --- compact lockup for the app chrome ------------------------------------------
    # The full lockup cannot go in a control bar: at the ~28px the bar allows, its
    # wordmark caps land near 5px and the 4x4 matrix turns to mush. So the chrome gets
    # a reduced mark, the wordmark scaled up to balance it, and no tagline. Ink is plain
    # currentColor with no internal stylesheet, so inlined in the page it simply inherits
    # --text-primary and matches the rest of the chrome.
    #
    # The mark uses the 1-cell cut, not the 2x2. Rendered at 28px the 2x2's nine nodes
    # crowd the aircraft until it stops reading as one, and the node blobs dominate. The
    # bare square with four corner nodes leaves the aircraft room to be legible, which
    # matters more here than holding on to a literal grid: the wordmark is right next to
    # it doing the naming, and the 4x4 mark carries the matrix idea everywhere it fits.
    ui_box, ui_cap, ui_gap = 44.0, 24.0, 12.0
    ui_scale = ui_cap / cap
    ui_text_x = ui_box + ui_gap
    ui_b_x = ui_text_x + (word_a_adv + track) * ui_scale
    ui_w = ui_text_x + (word_a_adv + track + word_b_adv) * ui_scale
    ui_base = ui_box / 2 + ui_cap / 2
    _, ui_body = small_mark(0, 0, ui_box, 3.4, 1, 2.6, 3.4, 3.8, 0.215, 5.0,
                            LINE_BACK, "currentColor")
    ui = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ui_w:.0f} {ui_box:.0f}" role="img" aria-label="FlightMatrix">
  <!-- Compact lockup for UI chrome: no tagline, ink inherited. Generated by build_logo.py. -->
{ui_body}
  <path fill="currentColor" transform="translate({ui_text_x:.1f} {ui_base:.1f}) scale({ui_scale:.6f} -{ui_scale:.6f})" d="{word_a_d}"/>
  <path fill="{ACCENT}" transform="translate({ui_b_x:.1f} {ui_base:.1f}) scale({ui_scale:.6f} -{ui_scale:.6f})" d="{word_b_d}"/>
</svg>
"""
    write("flightmatrix-lockup-ui.svg", ui)

    # --- wire it into the app -------------------------------------------------------
    # The favicon takes the 16px cut, not the 32px one. A single SVG favicon cannot swap
    # geometry by rendered size, and the tab is the dominant case at 16-20px, where the
    # 2x2 grid smudges. The 16px cut just looks spare at 64px, which is the safer failure.
    write("favicon.svg", icon(16, 2.6, 1, 1.5, 1.9, 1.8, 0.070, clear=2.0), where=APP)

    def indented(svg, pad):
        return "\n" + pad + svg.strip().replace("\n", "\n" + pad) + "\n" + pad[:-2]

    # The app gets the compact lockup, inside the control row. The full lockup needs
    # ~112px to keep its tagline legible, and a permanent brand row that tall is a lot of
    # every screen to spend on a logo when the board is the point. Built with auto=False
    # so it carries no internal stylesheet and no color attribute: inlined, it inherits
    # the page's colour outright, which is what lets one copy serve both themes and the
    # manual toggle.
    inject(APP / "index.html", "fm-logo", indented(ui, "      "))

    print(f"\nwordmark {word_w:.1f} wide, tagline tracking {t / upem:.3f}em, "
          f"canvas {canvas_w:.0f}x{canvas_h:.0f}, ui lockup {ui_w:.0f}x{ui_box:.0f}")

main()
