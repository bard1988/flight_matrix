"""Responsive / a11y audit harness: drive every view at every breakpoint and assert.

    py -3 data/audit_responsive.py [port]

Runs against a DEMO server (FM_DEMO=1), so it costs no provider calls and is
deterministic. Captures screenshots into shots/audit/ and prints machine-checked
findings for the things eyeballing a screenshot reliably misses:

  * horizontal overflow at each viewport
  * touch targets under 44x44 (WCAG 2.5.5 / 2.5.8)
  * the mobile detail layer having no way back to the list
  * text that overflows its row

Viewports bracket the three breakpoints in styles.css (720, 860, max-height 480).
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "shots" / "audit"
PORT = sys.argv[1] if len(sys.argv) > 1 else "8799"

DEPART = (date.today() + timedelta(days=30)).isoformat()
RETURN = (date.today() + timedelta(days=59)).isoformat()

VIEWPORTS = [
    ("phone-360", 360, 740),      # smallest realistic phone
    ("phone-390", 390, 844),      # iPhone 14/15
    ("phone-land", 740, 400),     # landscape phone -> max-height: 480 branch
    ("tablet-768", 768, 1024),    # between 720 and 860
    ("edge-860", 860, 900),       # exactly on the master-detail breakpoint
    ("laptop-1280", 1280, 800),
    ("desktop-1680", 1680, 1050),
]

# Elements that are genuinely interactive and therefore need a real touch target.
TOUCH_SELECTOR = (
    "button:not([disabled]), a[href], input:not([type=hidden]), select, "
    "summary, [role='button']:not(td), [tabindex]:not([tabindex='-1']):not(td)"
)

findings: list[tuple[str, str, str]] = []   # (severity, viewport/view, message)


def note(sev: str, where: str, msg: str) -> None:
    findings.append((sev, where, msg))
    print(f"  [{sev}] {where}: {msg}")


def overflow(page, where: str) -> None:
    data = page.evaluate("""() => {
      const el = document.scrollingElement;
      const over = [];
      for (const n of document.querySelectorAll('body *')) {
        const r = n.getBoundingClientRect();
        if (r.width && r.right > window.innerWidth + 1)
          over.push((n.tagName + '.' + (n.className || '')).slice(0, 60)
                    + ' right=' + Math.round(r.right));
      }
      return {doc: el.scrollWidth, win: window.innerWidth, over: over.slice(0, 5)};
    }""")
    if data["doc"] > data["win"] + 1:
        note("P1", where,
             f"horizontal overflow: document {data['doc']}px > viewport {data['win']}px"
             + (f"; first offenders {data['over']}" if data["over"] else ""))


def touch_targets(page, where: str, touch: bool = True, limit: int = 6) -> None:
    """Grade against the standard that actually applies.

    WCAG 2.5.8 (AA) is 24x24 CSS px and applies everywhere - anything under it is a real
    violation. 44x44 is 2.5.5 (AAA) and only meaningful where the pointer is a finger, so
    on a mouse viewport it is reported as polish, not a defect. Reporting the dense desktop
    chrome as a failure against 44 is how this kind of harness cries wolf.
    """
    small = page.evaluate(f"""() => {{
      const out = [];
      for (const n of document.querySelectorAll("{TOUCH_SELECTOR}")) {{
        const r = n.getBoundingClientRect();
        if (!r.width || !r.height) continue;                 // hidden
        if (getComputedStyle(n).visibility === 'hidden') continue;
        if (r.width < 44 || r.height < 44)
          out.push({{tag: n.tagName.toLowerCase(),
                    id: n.id || '', cls: (n.className || '').toString().slice(0, 34),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (n.textContent || '').trim().slice(0, 22)}});
      }}
      return out;
    }}""")
    fails_aa = [s for s in small if s["w"] < 24 or s["h"] < 24]
    if fails_aa:
        shown = "; ".join(f"{s['tag']}#{s['id'] or s['cls']} {s['w']}x{s['h']}"
                          for s in fails_aa[:limit])
        note("P1", where,
             f"{len(fails_aa)} target(s) under 24x24 - WCAG 2.5.8 AA failure: {shown}")
    rest = [s for s in small if s not in fails_aa]
    if rest and touch:
        shown = "; ".join(f"{s['tag']}#{s['id'] or s['cls']} {s['w']}x{s['h']}"
                          for s in rest[:limit])
        note("P3", where, f"{len(rest)} target(s) under the 44x44 touch comfort bar "
                          f"(AA-compliant): {shown}")


def shoot(page, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)


def run_search(page) -> None:
    # Set the fields directly: on mobile the date inputs live inside the collapsed
    # Options panel, so they are not visible and Playwright's fill() cannot reach them.
    page.evaluate(
        """([d, r]) => {
          const set = (id, v) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.value = v;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
          };
          set('depart', d); set('ret', r); set('dests', '8');
        }""",
        [DEPART, RETURN],
    )
    page.click("#go")


def main() -> int:
    env_server = subprocess.Popen(
        [sys.executable, str(ROOT / "run.py"), "--demo", "--no-open",
         "--port", PORT, "--host", "127.0.0.1"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(4)
    url = f"http://127.0.0.1:{PORT}/"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, w, h in VIEWPORTS:
                mobile = w <= 860
                # Emulate touch on the phone-class viewports. Without it `pointer: coarse`
                # does not match, the touch-comfort rules never apply, and every run
                # reports targets the real device would never see.
                ctx = browser.new_context(
                    viewport={"width": w, "height": h},
                    has_touch=mobile, is_mobile=mobile,
                    device_scale_factor=3 if mobile else 1,
                )
                page = ctx.new_page()
                page.goto(url, wait_until="networkidle")
                print(f"\n== {name} ({w}x{h}) ==")

                # 1. First run / empty state
                overflow(page, f"{name}/firstrun")
                touch_targets(page, f"{name}/firstrun", touch=mobile)
                shoot(page, f"{name}-1-firstrun")

                # 2. Preview state: the list exists, grids have not landed yet
                run_search(page)
                try:
                    page.wait_for_selector(".lrow", timeout=20000)
                    shoot(page, f"{name}-2-previews")
                    overflow(page, f"{name}/previews")
                    pv = page.evaluate(
                        "() => document.querySelectorAll('.lrow-when').length "
                        "&& [...document.querySelectorAll('.lrow-when')]"
                        ".filter(e => /finding dates/.test(e.textContent)).length")
                    print(f"     preview rows showing 'finding dates': {pv}")
                    # The mobile trap: open the detail layer while the grid is still empty.
                    if mobile and pv:
                        page.click(".lrow")
                        page.wait_for_timeout(250)
                        state = page.evaluate("""() => {
                          const open = document.body.classList.contains('detail-open');
                          const back = document.querySelector('.detail-back');
                          const vis = back && back.getBoundingClientRect().height > 0;
                          const listHidden = getComputedStyle(
                            document.getElementById('dlist')).display === 'none';
                          return {open, back: !!back, vis: !!vis, listHidden,
                                  text: (document.getElementById('ddetail').textContent||'')
                                        .trim().slice(0,60)};
                        }""")
                        shoot(page, f"{name}-3-detail-preview")
                        if state["open"] and state["listHidden"] and not state["vis"]:
                            note("P0", f"{name}/detail-preview",
                                 "detail layer covers the list with NO visible back control "
                                 f"(content: {state['text']!r}) - user is trapped until the "
                                 "grid arrives")
                        page.evaluate(
                            "() => document.body.classList.remove('detail-open')")
                except Exception as exc:
                    note("P1", f"{name}/previews", f"no list rows appeared: {exc}")

                # 3. Settled board. On a phone the grid lives in the detail layer and is
                # correctly hidden until a destination is opened, so wait for it in the
                # DOM rather than for visibility, or every mobile run reports a false
                # "no grid rendered".
                try:
                    page.wait_for_selector("table.matrix",
                                           state="attached" if mobile else "visible",
                                           timeout=60000)
                    page.wait_for_timeout(600)
                    shoot(page, f"{name}-4-board")
                    overflow(page, f"{name}/board")
                    touch_targets(page, f"{name}/board", touch=mobile)
                except Exception as exc:
                    note("P1", f"{name}/board", f"no grid rendered: {exc}")

                # 4. Detail layer with a real grid (mobile) / grid pane (desktop)
                if mobile:
                    page.click(".lrow")
                    page.wait_for_timeout(350)
                    shoot(page, f"{name}-5-detail")
                    overflow(page, f"{name}/detail")
                    back_ok = page.evaluate(
                        "() => {const b=document.querySelector('.detail-back');"
                        " return !!b && b.getBoundingClientRect().height>0;}")
                    if not back_ok:
                        note("P0", f"{name}/detail", "filled detail layer has no visible back control")

                # 5. Table view. Close the phone detail layer first: it is a fixed
                # full-screen layer that legitimately covers the board tools, so clicking
                # through it would be testing the harness, not the product.
                try:
                    page.evaluate("() => document.body.classList.remove('detail-open')")
                    page.wait_for_timeout(150)
                    page.click("#tabletoggle")
                    page.wait_for_timeout(400)
                    shoot(page, f"{name}-6-table")
                    overflow(page, f"{name}/table")
                    # On a phone the table is a fixed full-screen layer that covers the
                    # toolbar toggle, so leaving it is the table's own control's job.
                    if mobile:
                        exit_ok = page.evaluate(
                            "() => {const b=document.querySelector('.table-back');"
                            " return !!b && b.getBoundingClientRect().height>0;}")
                        if not exit_ok:
                            note("P1", f"{name}/table",
                                 "table layer covers the Table/Matrix toggle and offers no "
                                 "control of its own - no way back to the board")
                        else:
                            page.click(".table-back")
                    else:
                        page.click("#tabletoggle")
                except Exception as exc:
                    note("P2", f"{name}/table", f"table view check failed: {exc}")

                # 6. Region tree popover
                try:
                    page.evaluate("() => document.body.classList.remove('detail-open')")
                    page.click("#ctrybtn")
                    page.wait_for_timeout(300)
                    shoot(page, f"{name}-7-regions")
                    overflow(page, f"{name}/regions")
                    clipped = page.evaluate("""() => {
                      const p = document.querySelector('#ctrypop, .ctrypop, [id*=ctry]');
                      if (!p) return null;
                      const r = p.getBoundingClientRect();
                      return {off: r.right > window.innerWidth + 1 || r.left < -1,
                              tall: r.bottom > window.innerHeight + 1,
                              w: Math.round(r.width), h: Math.round(r.height)};
                    }""")
                    if clipped and (clipped["off"] or clipped["tall"]):
                        note("P2", f"{name}/regions",
                             f"region popover clipped by viewport ({clipped})")
                except Exception:
                    pass

                page.close()
                ctx.close()
            browser.close()
    finally:
        env_server.terminate()

    print("\n================ SUMMARY ================")
    if not findings:
        print("No machine-checkable findings.")
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    for sev, where, msg in sorted(findings, key=lambda f: order.get(f[0], 9)):
        print(f"{sev}  {where}\n     {msg}")
    print(f"\n{len(findings)} finding(s). Screenshots: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
