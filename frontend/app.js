/* FlightMatrix board.

   One card per destination, each a departure-date x return-date matrix. The colour scale
   is computed PER MATRIX: every card runs its own cheapest cell (green) to its own
   dearest (red), so the colours show which dates suit that destination. Cross-destination
   comparison comes from the headline price, the cheapest-first ordering, and the yellow
   ring marking the cheapest cell on the whole board. */

const RAMP_STEPS = 7;

const state = {
  meta: null,
  destinations: new Map(), // IATA -> payload
  perPerson: false,
  source: null,
  searchId: null,
  globalBest: null,
  selected: null,          // IATA of the destination whose grid is shown in the detail pane
  countries: new Set(),    // ISO codes the results are narrowed to (empty = all countries)
  // Day-of-week / trip-length constraints, applied as a view over loaded cells.
  constraints: { dep: new Set(), ret: new Set(), min: null, max: null },
  // Currency is a display concern once the board is loaded: the board is priced in
  // `meta.currency`, and switching the dropdown just converts the numbers with FX
  // rates rather than re-running the whole search.
  fx: null,                // { eur: 1, usd: 1.08, ... } in units per 1 EUR
  displayCurrency: null,   // what the dropdown shows; defaults to meta.currency
  regions: new Set(),      // ISO country codes selected in the region tree (search filter)
};

// Rough offline fallback, only used if the FX fetch fails. Does not need to be exact.
const FX_FALLBACK = { eur: 1, usd: 1.16, gbp: 0.86, ils: 3.5 };

const $ = (id) => document.getElementById(id);

/* Board data comes from one of two aggregators; show their consumer-facing names. */
const sourceName = (s) =>
  s === 'kiwi' ? 'Kiwi.com' : s === 'travelpayouts' ? 'Aviasales' : s || 'the fare cache';

/* One phrasing for stop counts everywhere: tooltip, table, panel. */
const fmtStops = (n) =>
  n == null ? '' : n === 0 ? 'nonstop' : `${n} stop${n > 1 ? 's' : ''}`;

const REDUCE_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)');

/* ----------------------------------------------- shareable / bookmarkable board URL */

// query key -> element id. Everything a fresh search needs to reproduce this board.
const URL_FIELDS = {
  from: 'origin', depart: 'depart', ret: 'ret', adults: 'adults', children: 'children',
  places: 'dests', currency: 'currency',
  maxprice: 'maxprice', nmin: 'nmin', nmax: 'nmax',
  dephfrom: 'dephfrom', dephto: 'dephto', rethfrom: 'rethfrom', rethto: 'rethto',
};
const URL_FLAGS = { nonstop: 'nonstop', perperson: 'perperson' };

/** Write the current form to the address bar so the board can be bookmarked or shared. */
function boardToUrl() {
  const p = new URLSearchParams();
  for (const [key, id] of Object.entries(URL_FIELDS)) {
    const v = String($(id).value).trim();
    if (v !== '') p.set(key, v);
  }
  for (const [key, id] of Object.entries(URL_FLAGS)) if ($(id).checked) p.set(key, '1');
  if (!$('autoverify').checked) p.set('verify', '0');
  const qs = p.toString();
  history.replaceState(null, '', qs ? '?' + qs : location.pathname);
}

/** Populate the form from URL params. Returns the keys it recognised. */
function boardFromUrl(params) {
  const seen = new Set();
  for (const [key, id] of Object.entries(URL_FIELDS)) {
    if (params.has(key)) { $(id).value = params.get(key); seen.add(key); }
  }
  for (const [key, id] of Object.entries(URL_FLAGS)) {
    if (params.has(key)) { $(id).checked = params.get(key) === '1'; seen.add(key); }
  }
  if (params.has('verify')) { $('autoverify').checked = params.get('verify') !== '0'; seen.add('verify'); }
  return seen;
}

/* -------------------------------------------------- keyboard-operable matrix cells */

/** A screen-reader label for one fare cell. */
function cellAria(dest, cell) {
  const cur = state.meta && state.meta.currency;
  const dates = `${weekday(cell.depart)} ${shortDate(cell.depart)} to ${weekday(cell.ret)} ${shortDate(cell.ret)}`;
  let price;
  if (cell.total != null) price = `${fmtMoney(cell.total, cur)}, verified`;
  else if (cell.estimate != null) price = `${fmtMoney(cell.estimate, cur)}, estimated`;
  else price = 'no price yet';
  const stops = cell.transfers != null ? `, ${fmtStops(cell.transfers)}` : '';
  const stale = cell.stale ? ', price may be out of date' : '';
  return `${dest.city}, ${dates}. ${price}${stops}${stale}. Press Enter for the live price.`;
}

/** Make a matrix cell operable by keyboard: role, roving tab stop, Enter/Space + arrows. */
function wireCell(td, activate, aria) {
  td.tabIndex = -1;
  td.setAttribute('role', 'button');
  if (aria) td.setAttribute('aria-label', aria);
  td.addEventListener('click', activate);
  td.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); activate(); return; }
    const step = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[e.key];
    if (!step) return;
    e.preventDefault();
    const table = td.closest('table.matrix');
    const r = Number(td.dataset.r) + step[0];
    const c = Number(td.dataset.c) + step[1];
    const next = table && table.querySelector(`td[data-r="${r}"][data-c="${c}"][role="button"]`);
    if (!next) return;
    td.tabIndex = -1;
    next.tabIndex = 0;
    next.focus({ preventScroll: true });
    ensureVisible(next);
  });
}

/** Scroll a cell into its own viewport without moving the page. */
function ensureVisible(el) {
  const wrap = el.closest('.matrix-wrap');
  if (!wrap) return;
  const e = el.getBoundingClientRect();
  const w = wrap.getBoundingClientRect();
  if (e.left < w.left) wrap.scrollLeft -= w.left - e.left + 24;
  else if (e.right > w.right) wrap.scrollLeft += e.right - w.right + 24;
  if (e.top < w.top) wrap.scrollTop -= w.top - e.top + 24;
  else if (e.bottom > w.bottom) wrap.scrollTop += e.bottom - w.bottom + 24;
}

/** Give one cell per grid the roving tab stop (the cheapest, else the first priced). */
function seedGridTabstop(table) {
  const cell = table.querySelector('td.best-board[role="button"]')
    || table.querySelector('td.best-here[role="button"]')
    || table.querySelector('td.priced[role="button"]')
    || table.querySelector('td[role="button"]');
  if (cell) cell.tabIndex = 0;
}

/* ------------------------------------------------------------------ helpers */

/* Local calendar date as YYYY-MM-DD. Never via toISOString(): that converts to UTC first,
   so local midnight rolls back to the previous day in any timezone east of Greenwich, and
   the date fields end up a day early. */
function isoLocal(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function isoToday(offsetDays) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return isoLocal(d);
}

/* Convert an amount between currencies using the loaded FX table. `state.fx[x]` is
   units of x per 1 base, so from->to is value * fx[to] / fx[from]. Unknown currency or
   no table: pass the number through unconverted. */
function convert(value, from) {
  const to = state.displayCurrency || from;
  if (value == null || to === from) return value;
  const fx = state.fx || FX_FALLBACK;
  const rf = fx[from], rt = fx[to];
  if (!rf || !rt) return value;
  return value * (rt / rf);
}

function fmtMoney(value, currency) {
  if (value == null) return '';
  const to = state.displayCurrency || currency;
  const symbol = { ils: '₪', eur: '€', usd: '$', gbp: '£' }[to] || '';
  return symbol + Math.round(convert(value, currency)).toLocaleString();
}

/* Cell labels: always priced in meta.currency, shown in the display currency. */
function fmtCompact(value) {
  if (value == null) return '';
  const n = Math.round(convert(value, state.meta && state.meta.currency));
  if (n >= 10000) return Math.round(n / 1000) + 'k';
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(n);
}

/* Load FX rates once. Free, keyless, CORS-enabled source; cached in localStorage for
   12h, with a static fallback if it is unreachable. Rates only need to be roughly
   right: they re-label already-fetched prices, they don't drive any decision. */
async function loadFx() {
  const CACHE_KEY = 'flightmatrix.fx';
  const MAX_AGE = 12 * 3600 * 1000;
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
    if (cached && Date.now() - cached.ts < MAX_AGE && cached.rates) {
      state.fx = cached.rates;
      return;
    }
  } catch (e) { /* ignore */ }

  try {
    // exchangerate-api's free open endpoint: no key, CORS '*', daily ECB-ish rates.
    const r = await fetch('https://open.er-api.com/v6/latest/EUR');
    const data = await r.json();
    const src = data && data.rates ? data.rates : {};
    const rates = { eur: 1 };
    for (const c of ['USD', 'GBP', 'ILS']) if (src[c]) rates[c.toLowerCase()] = src[c];
    if (rates.ils && rates.usd && rates.gbp) {
      state.fx = rates;
      try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), rates })); } catch (e) { /* ignore */ }
      if (state.meta) render();   // refresh with real rates if a board is already up
      return;
    }
  } catch (e) { /* fall through */ }

  state.fx = FX_FALLBACK;
}

function shortDate(iso) {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function weekday(iso) {
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short' });
}

function isWeekend(iso) {
  const day = new Date(iso + 'T00:00:00').getDay();
  return day === 5 || day === 6; // Fri/Sat, the Israeli weekend
}

/** Price shown in a cell: a verified live total wins over the cached estimate. */
function cellValue(cell) {
  const total = cell.total != null ? cell.total : cell.estimate;
  if (!state.perPerson) return total;
  const pax = (state.meta?.adults || 1) + (state.meta?.children || 0);
  return total / Math.max(pax, 1);
}

/* The same figure for a preview card, which has no cells for cellValue() to price.
 *
 * `preview_price` is a party total from discovery, exactly like a cell's, so Per person has
 * to divide it the same way. Reading it raw put a party total and a per-person fare in the
 * same ranked list under the same currency symbol, which silently mis-ordered the board
 * whenever the toggle was on. */
function previewValue(dest) {
  if (dest.preview_price == null) return null;
  if (!state.perPerson) return dest.preview_price;
  const pax = (state.meta?.adults || 1) + (state.meta?.children || 0);
  return dest.preview_price / Math.max(pax, 1);
}

/* Ink is no longer chosen by a single flip index: the ramp is diverging, so BOTH ends are
   saturated and each step carries its own readable ink as a CSS variable. */

/* ------------------------------------------------------------- colour scale */

/** Break points for a rank (quantile) scale over one destination's cells.
 *
 * The scale is PER MATRIX: each card's own cheapest cell is green and its own dearest is
 * red, so the colours answer "which dates are good for this destination". The trade-off
 * is that colour no longer compares across cards - a green cell on an expensive
 * destination can cost more than a red cell on a cheap one. Cross-destination comparison
 * comes from the card headline price, the cheapest-first ordering, and the yellow ring on
 * the board-wide cheapest cell.
 *
 * Ranking rather than a linear price ramp: fares bunch tightly and one outlier drags a
 * linear scale into two shades (measured: 73% of cells in two of seven steps). Absolute
 * prices stay legible because every cell is labelled. */
function scaleDomain(cells) {
  const values = [];
  for (const cell of cells || []) {
    const v = cellValue(cell);
    if (v != null) values.push(v);
  }
  if (!values.length) return null;
  values.sort((a, b) => a - b);
  // Upper bound of each ramp step, cheapest step first.
  const breaks = [];
  for (let i = 1; i < RAMP_STEPS; i += 1) {
    breaks.push(values[Math.floor((values.length * i) / RAMP_STEPS)]);
  }
  return { breaks, lo: values[0], hi: values[values.length - 1] };
}

/** Ramp index 0 = cheapest (green) .. 6 = dearest (red), or null for "no scale".
 *
 * Returns null rather than a colour when there is nothing to scale against - if a
 * constraint excludes every cell, painting them all "dearest" is actively misleading:
 * it says "everything here is expensive" when it means "nothing matched". */
function rampIndex(value, domain) {
  if (!domain || value == null) return null;
  let bucket = 0;
  while (bucket < domain.breaks.length && value >= domain.breaks[bucket]) bucket += 1;
  return Math.min(bucket, RAMP_STEPS - 1);
}

/* ------------------------------------------------------------------ tooltip */

const tooltip = $('tooltip');

function showTooltip(event, html) {
  tooltip.innerHTML = html;
  tooltip.style.display = 'block';
  const box = tooltip.getBoundingClientRect();
  let x = event.clientX + 14;
  let y = event.clientY + 14;
  if (x + box.width > window.innerWidth - 8) x = event.clientX - box.width - 14;
  if (y + box.height > window.innerHeight - 8) y = event.clientY - box.height - 14;
  tooltip.style.left = x + 'px';
  tooltip.style.top = y + 'px';
}

function hideTooltip() {
  tooltip.style.display = 'none';
}

function tooltipFor(dest, cell) {
  const cur = state.meta.currency;
  const rows = [];
  rows.push(`<b>${dest.city} (${dest.destination})</b>`);
  rows.push(`${weekday(cell.depart)} ${shortDate(cell.depart)} &rarr; ${weekday(cell.ret)} ${shortDate(cell.ret)}, ${cell.nights} nights`);
  const who = `${state.meta.adults} adults` + (state.meta.children ? ` + ${state.meta.children} children` : '');
  if (cell.total != null) {
    rows.push(`<b>${fmtMoney(cell.total, cur)}</b> verified on Google Flights`);
  } else if (cell.is_total) {
    // Kiwi returns a real party total for the requested passenger mix, so it is not an
    // extrapolation and must not be labelled as one.
    rows.push(`<b>${fmtMoney(cell.estimate, cur)}</b> total for ${who} <span class="muted">via ${sourceName(cell.source)}</span>`);
  } else {
    rows.push(`<b>${fmtMoney(cell.estimate, cur)}</b> estimated total <span class="muted">(${fmtMoney(cell.unit_price, cur)} per ticket × party)</span>`);
  }
  if (cell.airline) rows.push(`<span class="muted">Airline ${cell.airline}</span>`);
  if (cell.transfers != null) {
    rows.push(`<span class="muted">${fmtStops(cell.transfers)}</span>`);
  }
  if (cell.stale) rows.push(`<span class="muted">cached ${Math.round(cell.age_hours)}h ago</span>`);
  rows.push(`<span class="muted">${cell.verified ? 'Click to re-check' : 'Click for the live price'}</span>`);
  return rows.join('<br>');
}

/* --------------------------------------------------------------- constraints */

const DOW = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const DOW_FULL = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/** Is this cell allowed by the day-of-week and trip-length constraints?
 *
 * A pure view constraint over cells already loaded, so it costs nothing and applies
 * instantly. Crucially the colour scale and the cheapest-cell markers are computed over
 * only the allowed cells, so "cheapest Thu to Sun" is a real answer rather than the board
 * merely hiding rows. */
function cellAllowed(cell) {
  const c = state.constraints;
  if (c.dep.size && !c.dep.has(new Date(cell.depart + 'T00:00:00').getDay())) return false;
  if (c.ret.size && !c.ret.has(new Date(cell.ret + 'T00:00:00').getDay())) return false;
  if (c.min != null && cell.nights < c.min) return false;
  if (c.max != null && cell.nights > c.max) return false;
  return true;
}

function constraintsActive() {
  const c = state.constraints;
  return c.dep.size > 0 || c.ret.size > 0 || c.min != null || c.max != null;
}

function describeConstraints() {
  const c = state.constraints;
  const bits = [];
  if (c.dep.size) bits.push(`depart ${[...c.dep].sort().map((d) => DOW_FULL[d]).join('/')}`);
  if (c.ret.size) bits.push(`return ${[...c.ret].sort().map((d) => DOW_FULL[d]).join('/')}`);
  if (c.min != null || c.max != null) {
    bits.push(`${c.min ?? 0}-${c.max ?? '∞'} nights`);
  }
  return bits.join(', ');
}

function buildDowPicker(hostId, key) {
  const host = $(hostId);
  host.replaceChildren(...DOW.map((label, day) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    b.title = DOW_FULL[day];
    b.onclick = () => {
      const set = state.constraints[key];
      if (set.has(day)) set.delete(day);
      else set.add(day);
      b.classList.toggle('on', set.has(day));
      if (state.meta) render();
    };
    return b;
  }));
}

/* ------------------------------------------------------------------- render */

/** Is this destination visible? Hidden only if its country chip is toggled off. */
function matchesFilter(dest) {
  return state.countries.size === 0 || state.countries.has((dest.country || '').toUpperCase());
}

function render() {
  const visible = [...state.destinations.values()].filter(matchesFilter);

  // Cheapest cell among the destinations actually on screen, so the yellow marker always
  // points at something visible rather than at a card the filter has hidden.
  // Everything below - colour scale, per-card best, board best, ordering - is computed
  // over the ALLOWED cells only, so a constraint changes the answer rather than just
  // hiding squares.
  for (const dest of visible) {
    dest.allowed = dest.cells.filter(cellAllowed);
    dest.shownBest = dest.allowed.reduce(
      (acc, c) => (acc === null || cellValue(c) < cellValue(acc) ? c : acc), null);
  }

  state.globalBest = null;
  for (const dest of visible) {
    for (const cell of dest.allowed) {
      const v = cellValue(cell);
      if (v == null) continue;
      if (!state.globalBest || v < state.globalBest.value) {
        state.globalBest = { value: v, dest: dest.destination, depart: cell.depart, ret: cell.ret };
      }
    }
  }

  // A preview card has no cells yet but discovery already priced it, so rank it on that.
  // Without this every not-yet-filled destination sorts to the bottom and the list
  // visibly reshuffles as each grid lands.
  const rank = (d) => {
    // A grid that is still streaming ranks on discovery's price, never on its partial
    // cells. Ranking a half-filled grid makes its row climb the list as cheaper columns
    // land, so the thing the user is reading moves under them, and the position it moves
    // to is not final anyway. It settles once the destination event lands.
    const pv = previewValue(d);
    if (d.filling && pv != null) return pv;
    if (d.shownBest) return cellValue(d.shownBest);
    return pv == null ? Infinity : pv;
  };
  const ordered = visible.sort((a, b) => rank(a) - rank(b));

  const active = constraintsActive();
  if (active) {
    const kept = ordered.reduce((n, d) => n + d.allowed.length, 0);
    const all = ordered.reduce((n, d) => n + d.cells.length, 0);
    // A constraint that excludes nothing has nothing to report. "170 of 170 cells" cost a
    // permanent line above the board to tell the user their filter was inert, and the
    // Nights fields in the bar above already show what is set.
    $('constraintnote').hidden = kept === all;
    let text = `${describeConstraints()}: ${kept} of ${all} cells`;
    // Explain an impossible constraint rather than showing a silently empty board. The
    // usual cause is treating the two date fields as a range: anchors far apart mean every
    // cell is a long trip, so a short-nights filter can never match.
    if (!kept && all) {
      const lengths = ordered.flatMap((d) => d.cells.map((c) => c.nights));
      const lo = Math.min(...lengths);
      const hi = Math.max(...lengths);
      const c = state.constraints;
      if ((c.min != null && c.min > hi) || (c.max != null && c.max < lo)) {
        text += `. This window only contains ${lo}-${hi} night trips. ` +
                `Your dates are ${Math.round((new Date(state.meta.return_dates[Math.floor(state.meta.return_dates.length / 2)]) - new Date(state.meta.depart_dates[Math.floor(state.meta.depart_dates.length / 2)])) / 86400000)} days apart. ` +
                `Move "Return around" closer to "Depart around" to look for short trips.`;
      } else {
        text += '. Nothing matches; try fewer days or a wider nights range.';
      }
    }
    $('constraintnote').textContent = text;
    $('constraintnote').classList.toggle('warn', !kept && all > 0);
  } else {
    $('constraintnote').hidden = true;
    $('constraintnote').textContent = '';
    $('constraintnote').classList.remove('warn');
  }

  syncCountryFilter(ordered);
  syncSelection(ordered);
  const selDest = ordered.find((d) => d.destination === state.selected) || null;

  // Once the board is settled, quietly live-price whichever destination is open.
  if (selDest && !state.source) fillOpenDestination(selDest);

  // A keyboard user navigating the grid loses focus when the detail pane is rebuilt (every
  // streamed destination, every verify fold-back). Remember which cell had it and put it
  // back on the equivalent cell afterwards.
  const af = document.activeElement;
  const keep = af && af.matches && af.matches('td[role="button"]')
    ? { dest: af.closest('.card') && af.closest('.card').dataset.dest, r: af.dataset.r, c: af.dataset.c }
    : null;

  // Left: the ranked list, one tight row per destination. Right: the selected one's grid.
  $('dlist').replaceChildren(...ordered.map((dest) => listRow(dest, dest === selDest)));
  const detail = $('ddetail');
  if (selDest && selDest.cells.length) {
    detail.replaceChildren(renderCard(selDest, scaleDomain(selDest.allowed)));
  } else if (selDest) {
    detail.replaceChildren(renderWaiting(selDest));
  } else {
    detail.replaceChildren();
  }
  const gridOnScreen = !!(selDest && selDest.cells.length);
  document.body.classList.toggle('has-board', ordered.length > 0);

  if (keep && keep.dest) {
    const cell = detail.querySelector(
      `.card[data-dest="${keep.dest}"] td[data-r="${keep.r}"][data-c="${keep.c}"][role="button"]`
    );
    if (cell) { cell.tabIndex = 0; cell.focus({ preventScroll: true }); ensureVisible(cell); }
  }

  state.lastOrdered = ordered;
  // The table view is the selected destination's grid as text, nothing else.
  renderTable(selDest ? [selDest] : ordered);
  refreshRegionCounts();
  $('boardtools').hidden = state.destinations.size === 0;
  $('footnote').hidden = ordered.length === 0;
  // The colour key describes the grid in the detail pane. That pane no longer always has
  // one: previews land first, so between discovery and the fill the key would be
  // explaining a ramp with nothing on screen using it.
  $('legend').hidden = !gridOnScreen;
}

/* The board's focal point: the cheapest find, then the two behind it.
 *
 * `ordered` is already sorted by each destination's own cheapest fare, so ordered[0] is the
 * board-wide winner and no separate search is needed. Every row jumps to the cell it
 * describes, which is the same thing the per-destination locate button does; without that
 * the band would be decoration restating what the first card already says.
 *
 * Buttons rather than divs with click handlers: these are the most likely thing on the page
 * to be reached by keyboard, and a real button gets focus, Enter and Space for free. */
/* Multi-select country filter in the toolbar. Empty selection = show all. */
function syncCountryFilter(ordered) {
  const total = state.destinations.size;
  $('btcount').textContent = total
    ? (state.countries.size
        ? `${ordered.length} of ${total} destinations`
        : `${total} destination${total === 1 ? '' : 's'}`)
    : '';

  const counts = new Map();       // code -> { name, n }
  for (const d of state.destinations.values()) {
    const c = (d.country || '').toUpperCase();
    if (!c) continue;
    const e = counts.get(c) || { name: d.country_name || c, n: 0 };
    e.n += 1;
    counts.set(c, e);
  }
  // Drop any selected country that's no longer on the board.
  for (const c of [...state.countries]) if (!counts.has(c)) state.countries.delete(c);

  const rows = [...counts.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name));
  const want = rows.map(([c, e]) => c + e.n).join('|');
  const pop = $('ctrypop');
  if (pop.dataset.opts !== want) {
    pop.dataset.opts = want;
    pop.replaceChildren(...rows.map(([code, { name, n }]) => {
      const lab = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = code;
      cb.checked = state.countries.has(code);
      cb.addEventListener('change', () => {
        cb.checked ? state.countries.add(code) : state.countries.delete(code);
        render();
      });
      lab.append(cb, ' ', name, Object.assign(document.createElement('span'),
        { className: 'ctry-n', textContent: n }));
      return lab;
    }));
  } else {
    for (const cb of pop.querySelectorAll('input')) cb.checked = state.countries.has(cb.value);
  }

  const picked = rows.filter(([c]) => state.countries.has(c)).map(([, e]) => e.name);
  $('ctrylabel').textContent =
    picked.length === 0 ? 'All countries'
      : picked.length <= 2 ? picked.join(', ')
      : `${picked.length} countries`;
  $('ctrycombo').hidden = rows.length < 2;
}

$('ctrybtn').addEventListener('click', () => {
  const open = $('ctrypop').hidden;
  $('ctrypop').hidden = !open;
  $('ctrybtn').setAttribute('aria-expanded', String(open));
});
document.addEventListener('mousedown', (e) => {
  if (!e.target.closest('#ctrycombo')) {
    $('ctrypop').hidden = true;
    $('ctrybtn').setAttribute('aria-expanded', 'false');
  }
});

// How much to trust the headline price. The board is built from a price calendar, which is
// a precomputed index that goes stale per date pair - TLV-CTA quoted 783 for a pair that a
// real search prices at 1,919, while the pair a week earlier was accurate to 8%. The backend
// re-prices the cheapest cell until the cheapest one is a price it fetched itself, so say
// which of the two happened rather than presenting both as equally solid.
function headlineChip(dest) {
  const drift = dest.headline_drift;
  if (dest.headline_checked === false) {
    return `<span class="drift" title="The cheapest cell here is still a price-calendar figure that we could not confirm within this search's check budget. Click it to price it live before you rely on it.">unconfirmed</span>`;
  }
  if (drift == null || Math.abs(drift) < 20) return '';
  const was = fmtMoney(dest.headline_was, state.meta.currency);
  const now = fmtMoney(dest.best ? dest.best.estimate : 0, state.meta.currency);
  const dir = drift > 0 ? 'under' : 'over';
  return `<span class="drift" title="The price calendar quoted ${was} for this card's cheapest trip; a real search returned ${now}. The headline shown is the real one. Other cells on this card come from the same calendar, so treat them as indicative until clicked.">calendar ${dir}stated by ~${Math.abs(Math.round(drift))}%</span>`;
}

/* Destinations that have already played their arrival animation. The board is rebuilt
   wholesale on every stream event (see renderBoard's replaceChildren), so without this the
   fade-up would replay on every card each time any one destination updated. Each
   destination animates once, when it first lands. Cleared by resetForSearch. */
const animatedDests = new Set();

/* Per-destination date axes, for destinations that have been widened on their own.
 *
 * The board starts with ONE set of axes for everything, which is what makes the same date
 * pair comparable across destinations. Widening a single destination necessarily breaks
 * that for that destination, and this map is where the divergence lives.
 *
 * It is keyed by IATA code and kept OUTSIDE the destination payload on purpose: every
 * stream event replaces the payload object wholesale (state.destinations.set(code, msg)),
 * so axes stored on it would be discarded seconds later. */
const destAxes = new Map();

/** The axes this destination's grid should be drawn on: its own if it has been widened,
 *  otherwise the board's. */
function axesFor(dest) {
  const own = destAxes.get(dest.destination);
  if (own) return own;
  return { departs: state.meta.depart_dates, returns: state.meta.return_dates };
}
/* Master–detail: exactly one destination's grid is on screen at a time, in the detail
 * pane. `isExpanded` is what renderCard checks to take its full-grid path, so the selected
 * destination "is expanded" and every other one is a list row. Until the user picks a row,
 * the selection tracks the cheapest destination (so the detail pane is never empty once a
 * board exists); after they pick, it is theirs. */
function isExpanded(code) {
  return code === state.selected;
}

/* Keep the selection pointed at something real. Before the user has chosen, follow the
   cheapest destination as the stream re-sorts; once chosen, only correct it if that
   destination has dropped off the board (e.g. a country filter hid it). */
let userPickedDest = false;
function syncSelection(ordered) {
  if (!ordered.length) { state.selected = null; return; }
  const stillThere = ordered.some((d) => d.destination === state.selected);
  if (userPickedDest && stillThere) return;

  const current = stillThere ? state.destinations.get(state.selected) : null;
  const streaming = !!state.source;

  // While the board is streaming, hold on to a selection that already has a grid instead
  // of re-pinning to whatever is currently top of the list.
  //
  // The two ranking bases are not comparable during a fill. A preview ranks on discovery's
  // price, which is a floor across the whole window; a filled grid ranks on its cheapest
  // cell within the requested nights, which is usually higher. So each destination that
  // finishes filling sinks BELOW the previews still above it, top-of-list flips to a card
  // with no grid, and the matrix the user is watching fill is replaced by a waiting card.
  // Measured: it swapped the open grid out mid-fill on a 6-destination board.
  if (streaming && current && current.cells.length) return;

  // Otherwise take the cheapest destination that actually has a grid to show. Falling back
  // to ordered[0] regardless would settle the finished board on a card that never filled,
  // leaving the pane empty next to a list full of priced grids. ordered[0] is only right
  // when nothing has filled at all, which is the state before the first column lands.
  const withGrid = ordered.find((d) => d.cells && d.cells.length);
  state.selected = (withGrid || ordered[0]).destination;
}

/* One row in the ranked list: the destination's essence in a line — name, country, the
   cheapest fare and the ceiling, and the cheapest date pair. Clicking it loads that grid
   into the detail pane (and, on a phone, slides the pane in over the list). */
function listRow(dest, isSel) {
  const meta = state.meta;
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'lrow';
  b.dataset.dest = dest.destination;
  if (isSel) b.classList.add('is-sel');
  b.setAttribute('aria-current', isSel ? 'true' : 'false');

  // Until the grid lands the row shows discovery's headline price, which is a real party
  // total for a real trip - just not yet pinned to a date pair, so the dates read as
  // pending rather than being guessed.
  const isPreview = dest.preview && !dest.shownBest;
  const best = dest.shownBest ? cellValue(dest.shownBest)
    : isPreview ? previewValue(dest) : null;
  const priced = (dest.allowed || []).map(cellValue).filter((v) => v != null);
  const hi = priced.length ? Math.max(...priced) : null;
  const range = !isPreview && best != null && hi != null && hi > best
    ? `<span class="lrow-range">&ndash;&#8202;${fmtMoney(hi, meta.currency)}</span>` : '';
  const bc = dest.shownBest;
  const when = bc
    ? `${weekday(bc.depart)} ${shortDate(bc.depart)} &rarr; ${weekday(bc.ret)} ${shortDate(bc.ret)}` +
      `, ${bc.nights}n`
    : isPreview ? 'Finding dates&hellip;'
    : 'no fare yet';

  b.innerHTML =
    `<span class="lrow-city">${dest.city}` +
      `${dest.country_name ? `<span class="lrow-country">${dest.country_name}</span>` : ''}</span>` +
    `<span class="lrow-price">${best != null ? fmtMoney(best, meta.currency) : '&mdash;'}${range}</span>` +
    `<span class="lrow-when">${when}</span>`;

  b.addEventListener('click', () => {
    userPickedDest = true;
    state.selected = dest.destination;
    document.body.classList.add('detail-open');
    render();
  });
  return b;
}

/* The detail pane for a destination whose grid has not arrived yet.
 *
 * This state only exists because the board previews every destination after one discovery
 * call, so on a cold board a card can sit here for a while. It must carry the same head
 * and the same "‹ All" control as a filled card: on a phone the pane is a fixed full-screen
 * layer that hides the list, so a bare sentence with no control is a dead end - you could
 * open Sofia and have no way back until its grid landed, which on a cold board is minutes.
 * The head also keeps the pane from reading as a rendering failure on a wide desktop. */
function renderWaiting(dest) {
  const card = document.createElement('section');
  card.className = 'card is-waiting';
  card.dataset.dest = dest.destination;

  const head = document.createElement('div');
  head.className = 'card-head';

  const back = document.createElement('button');
  back.className = 'fillbtn detail-back';
  back.type = 'button';
  back.textContent = '‹ All';
  back.title = 'Back to the destination list';
  back.setAttribute('aria-label', 'Back to the destination list');
  back.onclick = () => { document.body.classList.remove('detail-open'); render(); };
  head.appendChild(back);

  const city = document.createElement('h2');
  city.className = 'card-city';
  city.textContent = dest.city || dest.destination;
  head.appendChild(city);
  card.appendChild(head);

  const wait = document.createElement('p');
  wait.className = 'detail-waiting';
  // aria-live so a screen reader hears the grid arrive rather than sitting in silence.
  wait.setAttribute('role', 'status');
  const price = previewValue(dest);
  wait.textContent = price != null
    ? `Cheapest found so far ${fmtMoney(price, dest.currency || state.meta.currency)}. `
      + 'Finding the dates behind it…'
    : 'Loading this destination’s dates…';
  card.appendChild(wait);
  return card;
}

function renderCard(dest, domain) {
  const meta = state.meta;
  const card = document.createElement('section');
  card.className = 'card';
  card.dataset.dest = dest.destination;
  if (!animatedDests.has(dest.destination)) {
    card.classList.add('is-new');
    animatedDests.add(dest.destination);
  }

  const head = document.createElement('div');
  head.className = 'card-head';
  const best = dest.shownBest ? cellValue(dest.shownBest) : null;
  const bc = dest.shownBest;
  const when = bc
    ? `${weekday(bc.depart)} ${shortDate(bc.depart)} &rarr; ${weekday(bc.ret)} ${shortDate(bc.ret)}` +
      `, ${bc.nights} night${bc.nights === 1 ? '' : 's'}`
    : '';
  // The essence of a matrix in two numbers: what the cheapest date pair costs, and the
  // ceiling across every priced pair. A deal-hunter scanning the list wants the spread
  // before deciding which grids are worth opening.
  const priced = (dest.allowed || []).map(cellValue).filter((v) => v != null);
  const hi = priced.length ? Math.max(...priced) : null;
  const range = best != null && hi != null && hi > best
    ? `<span class="card-range">–&#8202;${fmtMoney(hi, meta.currency)}</span>` : '';
  head.innerHTML =
    `<h2>${dest.city}${dest.country_name ? ` <span class="card-country">${dest.country_name}</span>` : ''}</h2>` +
    `<span class="card-when">${when}</span>` +
    headlineChip(dest) +
    `<span class="best">${best != null ? fmtMoney(best, meta.currency) : ''}${range}</span>`;

  /* This card is always the detail pane now: the one selected destination's full grid. The
     leading control is a "back" affordance — it only matters on a phone, where the grid
     covers the list; on desktop the list stays beside it and CSS hides the button. */
  card.classList.add('is-open');
  const back = document.createElement('button');
  back.className = 'fillbtn detail-back';
  back.type = 'button';
  back.textContent = '‹ All';
  back.title = 'Back to the destination list';
  back.setAttribute('aria-label', 'Back to the destination list');
  back.onclick = () => { document.body.classList.remove('detail-open'); };
  head.appendChild(back);

  // No bulk "price every date" here: the cached estimates are close enough to shortlist on,
  // and clicking any single cell fetches its real live price on demand. Stripping the button
  // keeps the grid to one job — show the shape of the calendar.
  //
  // Jump to this matrix's cheapest cell. On a wide window the winner is usually scrolled
  // out of view, and hunting for a yellow ring in a 57x57 grid is exactly the chore this
  // board exists to remove.
  const locate = document.createElement('button');
  locate.className = 'fillbtn locate';
  locate.textContent = '◎';
  locate.title = 'Jump to this destination’s cheapest date pair';
  locate.setAttribute('aria-label', `Jump to ${dest.city}'s cheapest date pair`);
  locate.onclick = () => locateBest(card, dest);
  head.appendChild(locate);

  /* Widen THIS destination's dates by a week at each end. Per destination because that is
     how the need arises: you narrow to a candidate and want more dates for it, and one
     destination costs a twentieth of the provider calls a whole board would.
     Only offered while expanded: a collapsed row is meant to be one line, and the point of
     widening is to look at the grid.
     Hidden rather than disabled at the period ceiling, since a permanently dead control
     invites clicking. */
  if (canWiden(dest)) {
    const wider = document.createElement('button');
    wider.type = 'button';
    wider.className = 'fillbtn';
    const busy = widening.has(dest.destination);
    wider.textContent = busy ? '…' : `± ${WIDEN_STEP_DAYS}d`;
    wider.disabled = busy;
    const p = periodOf(dest);
    wider.title = busy
      ? `Widening ${dest.city}…`
      : `Widen ${dest.city} by ${WIDEN_STEP_DAYS} days at each end ` +
        `(${p.start} to ${p.end} now) and re-price just this destination`;
    wider.setAttribute('aria-label', `Widen ${dest.city}'s dates by a week at each end`);
    wider.onclick = () => widenDestination(dest);
    head.appendChild(wider);
  }

  card.appendChild(head);

  const byKey = new Map(dest.cells.map((c) => [c.depart + '|' + c.ret, c]));

  // Always the departure x return matrix, in both date modes. In range mode that means a
  // thin diagonal band of priced cells inside a large grid - the empty cells are simply
  // trip lengths that were not asked for, and showing the real calendar shape is worth
  // more than compacting it.
  const table = document.createElement('table');
  table.className = 'matrix';

  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  // Keep this short: it is the widest thing in the first column and a long label pushes
  // the grid past the card, clipping the last date columns.
  headRow.innerHTML = '<th class="corner" title="rows are return dates, columns are departure dates">ret ↓ dep →</th>';
  // This destination's own axes if it has been widened by itself, else the board's.
  const { departs: axDeparts, returns: axReturns } = axesFor(dest);
  axDeparts.forEach((depart, colIndex) => {
    const th = document.createElement('th');
    th.className = 'col' + (isWeekend(depart) ? ' weekend' : '');
    th.scope = 'col';
    th.dataset.c = String(colIndex);
    th.innerHTML = `${weekday(depart)}<br>${shortDate(depart)}`;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  axReturns.forEach((ret, rowIndex) => {
    const tr = document.createElement('tr');
    const th = document.createElement('th');
    th.className = 'row' + (isWeekend(ret) ? ' weekend' : '');
    th.scope = 'row';
    th.dataset.r = String(rowIndex);
    th.innerHTML = `${weekday(ret)} ${shortDate(ret)}`;
    tr.appendChild(th);

    axDeparts.forEach((depart, colIndex) => {
      const td = document.createElement('td');
      if (ret < depart) {
        td.className = 'void';                       // return before departure
        td.textContent = '–';
        td.title = 'Return is before departure';
        tr.appendChild(td);
        return;
      }
      const cell = byKey.get(depart + '|' + ret);
      if (!cell) {
        // In range mode most blanks are simply trip lengths outside what was asked for,
        // not gaps in the data, so say which it is.
        const nights = Math.round((new Date(ret) - new Date(depart)) / 86400000);
        const outsideAsk = meta.nights_span
          && !meta.nights_span.includes(nights);
        td.className = outsideAsk ? 'notasked' : 'nodata';
        td.title = outsideAsk
          ? `${nights} nights - outside the ${meta.nights_span[0]}-${meta.nights_span[meta.nights_span.length - 1]} you asked for. Click to price it anyway.`
          : 'No cached fare for this date pair. Click to fetch it live.';
        td.dataset.depart = depart;
        td.dataset.ret = ret;
        td.dataset.dest = dest.destination;
        td.dataset.c = String(colIndex);
        td.dataset.r = String(rowIndex);
        wireCell(td, () => {
          pinCross(table, rowIndex, colIndex);
          verifyCell(dest, { depart, ret, nights });
        }, `${dest.city}, ${weekday(depart)} ${shortDate(depart)} to ${weekday(ret)} ${shortDate(ret)}. No price yet. Press Enter to fetch it live.`);
        tr.appendChild(td);
        return;
      }

      const value = cellValue(cell);
      const idx = rampIndex(value, domain);
      // Excluded cells stay visible but recede, so you can still see what you ruled out
      // and how much it would have cost. A cell we actually priced live is never dimmed,
      // even if its trip length falls outside what was asked for: the user clicked it and
      // spent a request on it, so its real number gets shown plainly.
      td.className =
        'priced ' + (idx === null ? 'unscaled' : `q${idx}`) +
        (cellAllowed(cell) || cell.verified ? '' : ' excluded') +
        (cell.verified ? ' verified' : '') +
        // A constant trip length runs along a diagonal, so mark the whole-week ones
        // as a faint guide for reading trip length off the grid.
        (cell.nights > 0 && cell.nights % 7 === 0 ? ' week-diag' : '');

      const isCardBest = dest.shownBest && cell.depart === dest.shownBest.depart && cell.ret === dest.shownBest.ret;
      const isBoardBest =
        state.globalBest &&
        state.globalBest.dest === dest.destination &&
        state.globalBest.depart === cell.depart &&
        state.globalBest.ret === cell.ret;
      if (isBoardBest) td.classList.add('best-board');
      else if (isCardBest) td.classList.add('best-here');

      const wrap = document.createElement('span');
      wrap.className = 'cellwrap';
      wrap.textContent = fmtCompact(value);
      // A numeric stop count collides with the price at this cell width and reads as part
      // of the number ("5.6k1"), so mark stops with a corner wedge and keep the count in
      // the tooltip.
      if (cell.transfers != null && cell.transfers > 0) {
        const wedge = document.createElement('span');
        wedge.className = 'stopdot' + (cell.transfers > 1 ? ' many' : '');
        wrap.appendChild(wedge);
      }
      if (cell.stale) {
        const dot = document.createElement('span');
        dot.className = 'staledot';
        wrap.appendChild(dot);
      }
      td.appendChild(wrap);

      td.dataset.c = String(colIndex);
      td.dataset.r = String(rowIndex);
      td.addEventListener('mousemove', (e) => showTooltip(e, tooltipFor(dest, cell)));
      td.addEventListener('mouseleave', hideTooltip);
      wireCell(td, () => {
        pinCross(table, rowIndex, colIndex);
        verifyCell(dest, cell);
      }, cellAria(dest, cell));
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  // Cross-hair: hovering a cell lights its departure column and return row so it is
  // obvious which date is the outbound and which the return.
  table.addEventListener('mouseover', (e) => {
    const td = e.target.closest('td[data-c]');
    if (td) highlightCross(table, Number(td.dataset.r), Number(td.dataset.c), false);
  });
  table.addEventListener('mouseleave', () => restorePinned(table));

  return finishCard(card, dest, table);
}

/** Wrap a grid in its scroll viewport and restore where the user had scrolled to. */
function finishCard(card, dest, table) {
  table.setAttribute('aria-label', `${dest.city} fares by date. Arrow keys to move between cells, Enter for the live price.`);
  seedGridTabstop(table);
  const wrap = document.createElement('div');
  wrap.className = 'matrix-wrap';
  wrap.appendChild(table);
  // Scrolling to any edge asks for a wider window. Restore the scroll offset after the
  // re-render so growing the grid does not yank the view back to the corner.
  wrap.addEventListener('scroll', () => rememberScroll(dest.destination, wrap), { passive: true });
  // No wheel handler any more: its only job was to widen the date window on deliberate
  // overscroll, and that path is gone with the widen control. The grid scrolls natively.
  card.appendChild(wrap);

  const saved = scrollOffsets.get(dest.destination);
  if (saved) {
    requestAnimationFrame(() => {
      wrap.scrollLeft = saved.x;
      wrap.scrollTop = saved.y;
    });
  } else {
    // First time this destination's grid is shown: jump to its cheapest cell and flash it,
    // exactly like pressing locate. locateBest calls rememberScroll, so from here on the
    // `saved` branch above restores wherever the user last left this grid. No flash while
    // the search is still streaming and the selection keeps flipping to the new cheapest.
    requestAnimationFrame(() => locateBest(card, dest, { quiet: true, flash: !state.source }));
  }
  return card;
}

/** The accessible relief for the light end of the ramp: every priced cell as text,
    sortable by any column. */
const tableSort = { key: 'total', dir: 1 };   // price, ascending

/* Leave table view. On a phone the table is a fixed full-screen layer, so it covers the
   Table/Matrix toggle that opened it; without a control of its own the only way out was
   the browser's back button. Mirrors .detail-back, and CSS hides it on desktop where the
   toolbar toggle is never covered. */
function tableBack() {
  const back = document.createElement('button');
  back.className = 'fillbtn detail-back table-back';
  back.type = 'button';
  back.textContent = '‹ Board';
  back.title = 'Back to the fare grid';
  back.setAttribute('aria-label', 'Back to the fare grid');
  back.onclick = () => {
    document.body.classList.remove('show-table');
    $('tabletoggle').textContent = 'Table';
    $('tabletoggle').setAttribute('aria-pressed', 'false');
  };
  return back;
}

function renderTable(ordered) {
  renderTable._list = ordered;
  const host = $('tableview');
  if (!ordered || !ordered.length) {
    host.replaceChildren();
    return;
  }
  const cur = state.meta.currency;
  // In the master–detail UI the table is the current destination's grid as text, so its
  // own name is not a column. It only earns one when several destinations are listed.
  const single = ordered.length === 1;
  const cols = [
    ...(single ? [] : [{ key: 'dest', label: 'Destination', cell: (r) => `${r.dest.city} (${r.dest.destination})`,
      cmp: (a, b) => a.dest.city.localeCompare(b.dest.city) }]),
    { key: 'depart', label: 'Depart', cell: (r) => `${weekday(r.cell.depart)} ${shortDate(r.cell.depart)}`,
      cmp: (a, b) => a.cell.depart.localeCompare(b.cell.depart) },
    { key: 'return', label: 'Return', cell: (r) => `${weekday(r.cell.ret)} ${shortDate(r.cell.ret)}`,
      cmp: (a, b) => a.cell.ret.localeCompare(b.cell.ret) },
    { key: 'nights', label: 'Nights', num: true, cell: (r) => r.cell.nights,
      cmp: (a, b) => a.cell.nights - b.cell.nights },
    { key: 'total', label: 'Total', num: true, cell: (r) => fmtMoney(r.value, cur),
      cmp: (a, b) => a.value - b.value },
    { key: 'source', label: 'Source',
      cell: (r) => `<span class="tag${r.cell.verified ? ' live' : ''}">${r.cell.verified ? 'Live' : 'Est'}</span>`,
      cmp: (a, b) => (a.cell.verified ? 1 : 0) - (b.cell.verified ? 1 : 0) },
    { key: 'stops', label: 'Stops', cell: (r) => fmtStops(r.cell.transfers),
      cmp: (a, b) => (a.cell.transfers == null ? 9 : a.cell.transfers) - (b.cell.transfers == null ? 9 : b.cell.transfers) },
  ];

  const rows = [];
  for (const dest of ordered) {
    for (const cell of dest.cells) {
      const value = cellValue(cell);
      if (value == null) continue;   // an unpriced date pair is a blank row, not a fare
      rows.push({ dest, cell, value });
    }
  }
  const active = cols.find((c) => c.key === tableSort.key)
    || cols.find((c) => c.key === 'total');
  rows.sort((a, b) => active.cmp(a, b) * tableSort.dir || a.value - b.value);

  const head = cols.map((c) => {
    const on = c.key === tableSort.key;
    const aria = on ? ` aria-sort="${tableSort.dir === 1 ? 'ascending' : 'descending'}"` : '';
    return `<th data-sort="${c.key}"${c.num ? ' class="num"' : ''}${aria}>${c.label}</th>`;
  }).join('');
  const body = rows.slice(0, 800)
    .map((r) => '<tr>' + cols.map((c) => `<td${c.num ? ' class="num"' : ''}>${c.cell(r)}</td>`).join('') + '</tr>')
    .join('');

  host.innerHTML =
    `<table><caption class="sr-only">Every priced date pair, ${rows.length} rows${rows.length > 800 ? ' (showing 800)' : ''}. Click a column heading to sort.</caption>` +
    `<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  host.prepend(tableBack());
}

/* Click a heading to sort; same column again flips direction. */
$('tableview').addEventListener('click', (e) => {
  const th = e.target.closest('th[data-sort]');
  if (!th || !renderTable._list) return;
  const key = th.dataset.sort;
  tableSort.dir = tableSort.key === key ? -tableSort.dir : 1;
  tableSort.key = key;
  renderTable(renderTable._list);
});

/* ------------------------------------------------------------------- verify */

/** Render the flight-times block from the board source, appended to whatever is showing. */
function renderTimes(details) {
  if (!details || details.error) {
    if (details && details.error) console.debug('flight times unavailable:', details.error);
    return details && details.error
      ? "<p class=\"muted\">Flight times aren't available for this one.</p>"
      : '';
  }
  // 'Sat 31 Jul 19:25' -> {day: 'Sat 31 Jul', time: '19:25'} so legs can show bare times
  // and only repeat a date when the leg actually crosses into another day.
  const split = (s) => {
    const m = /^(.*)\s(\d{2}:\d{2})$/.exec(s || '');
    return m ? { day: m[1], time: m[2] } : { day: '', time: s || '' };
  };

  const way = (label, s) => {
    if (!s) return '';
    const startDay = split(s.departs).day;
    const legs = s.legs.map((l, i) => {
      const d = split(l.departs);
      const a = split(l.arrives);
      // Only spell out a date when the leg leaves or lands on a different day.
      const dep = d.day && d.day !== startDay ? `${d.day} ${d.time}` : d.time;
      const arr = a.day && a.day !== d.day ? `${a.day} ${a.time}` : a.time;
      const num = s.legs.length > 1 ? `<span class="legno">${i + 1}</span>` : '';
      return `<div class="leg">${num}<span class="route">${l.from || '?'} → ${l.to || '?'}</span>` +
        `<span class="muted">${dep}${arr ? ' → ' + arr : ''}` +
        `${l.carrier ? ', ' + l.carrier : ''}${l.code ? ' ' + l.code : ''}</span></div>`;
    }).join('');
    return `<div class="segments"><b>${label}</b>` +
      // One middle dot per line: duration and stop count used to take one each, which made
      // the summary read as a dot-separated list rather than a sentence.
      `<div class="sector-summary">${s.departs || ''} → ${split(s.arrives).time || ''}` +
      `<span class="muted">${s.duration ? ', ' + s.duration : ''}` +
      `${s.duration ? ', ' : ', '}${fmtStops(s.stops || 0)}</span></div>` +
      legs + '</div>';
  };
  // Name the source and its price: the cross-check's cheapest is often a DIFFERENT
  // itinerary from the board's, so two unlabelled "departs" times read as a contradiction.
  const head = `<div class="segments-head">Flight times, ${details.price != null
    ? fmtMoney(details.price, state.meta.currency) + ' via Kiwi' : 'Kiwi'}</div>`;
  return head + way('Outbound', details.outbound) + way('Return', details.inbound);
}

/** Times come from the board source, so they work at any horizon. */
function fetchTimes(dest, cell) {
  const meta = state.meta;
  return fetch('/api/details', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: meta.origin, destination: dest.destination,
      depart_date: cell.depart, return_date: cell.ret,
      adults: meta.adults, children: meta.children,
      currency: meta.currency, nonstop_only: meta.nonstop_only,
    }),
  }).then((r) => r.json()).catch((e) => ({ error: String(e) }));
}

async function verifyCell(dest, cell) {
  hideTooltip();
  const meta = state.meta;
  // Kick the times request off immediately and in parallel: it comes from the board source
  // and succeeds even where the Google cross-check has no data at all.
  const timesPromise = fetchTimes(dest, cell);
  let timesHtml = '';
  timesPromise.then((details) => {
    timesHtml = renderTimes(details);
    const slot = document.getElementById('paneltimes');
    if (slot) slot.innerHTML = timesHtml;
  });
  // Whichever request finishes second must not wipe out the other's output, so every
  // panel render re-injects whatever the times request has produced so far.
  const restoreTimes = () => {
    const slot = document.getElementById('paneltimes');
    if (slot && timesHtml) slot.innerHTML = timesHtml;
  };
  openPanel(
    `<h3>${dest.city} (${dest.destination})</h3>` +
      `<div class="muted">${weekday(cell.depart)} ${shortDate(cell.depart)} &rarr; ${weekday(cell.ret)} ${shortDate(cell.ret)}</div>` +
      `<p>Checking Google Flights for ${meta.adults} adults${meta.children ? ' + ' + meta.children + ' children' : ''}…</p><div id="paneltimes"></div>`
  );

  let data;
  try {
    const res = await fetch('/api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        origin: meta.origin,
        destination: dest.destination,
        depart_date: cell.depart,
        return_date: cell.ret,
        adults: meta.adults,
        children: meta.children,
        currency: meta.currency,
        nonstop_only: meta.nonstop_only,
      }),
    });
    data = await res.json();
  } catch (err) {
    console.debug('cross-check request failed:', err);
    openPanel(
      `<h3>${dest.city} (${dest.destination})</h3>` +
        `<p class="err">Couldn't reach the live cross-check. Check your connection and try again.</p>`
    );
    return;
  }

  const cur = meta.currency;
  const who = `${meta.adults} adults` + (meta.children ? ` + ${meta.children} children` : '');
  const estimate = cell.estimate != null ? fmtMoney(cell.estimate, cur) : 'n/a';
  if (data.error || data.total == null) {
    // The live cross-check didn't return a price. The raw reason (route absent from
    // Google, rate limit, missing dependency) is dev detail: log it, never show it.
    // The board still priced this cell, so lead with that and keep the booking links live.
    if (data.error) console.debug('cross-check unavailable:', data.error);
    const boardPrice = cell.estimate != null
      ? `<div class="big">${fmtMoney(cell.estimate, cur)}</div>` +
        `<div class="muted">${cell.is_total ? `total for ${who}` : 'estimated'}, from ${sourceName(cell.source)}</div>`
      : '';
    const links = [];
    if (cell.link) {
      links.push(`<a href="${cell.link}" target="_blank" rel="noopener">Book on ${sourceName(cell.source)}</a>`);
    }
    if (data.link) {
      links.push(`<a href="${data.link}" target="_blank" rel="noopener">Open on Google Flights</a>`);
    }
    const explain = cell.estimate != null
      ? `Couldn't verify this fare live. Not every route is in Google Flights. The price above is the board's ${cell.is_total ? 'total' : 'estimate'}; the booking links below are live.`
      : `Couldn't verify this fare live, and the board has no price for this date pair. Try a nearby cell.`;
    openPanel(
      `<h3>${dest.city} (${dest.destination})</h3>` +
        `<div class="muted">${weekday(cell.depart)} ${shortDate(cell.depart)} &rarr; ${weekday(cell.ret)} ${shortDate(cell.ret)}</div>` +
        boardPrice +
        `<p class="muted">${explain}</p>` +
        '<div id="paneltimes"></div>' +
      (links.length ? `<p>${links.join('<br>')}</p>` : '')
    );
    restoreTimes();
    return;
  }

  const delta = cell.estimate ? ((data.total - cell.estimate) / cell.estimate) * 100 : null;
  openPanel(
    `<h3>${dest.city} (${dest.destination})</h3>` +
      `<div class="muted">${weekday(cell.depart)} ${shortDate(cell.depart)} &rarr; ${weekday(cell.ret)} ${shortDate(cell.ret)}, ${cell.nights || ''} nights</div>` +
      `<div class="big">${fmtMoney(data.total, cur)}</div>` +
      `<div class="muted">live total for ${meta.adults} adults${meta.children ? ' + ' + meta.children + ' children' : ''}</div>` +
      '<dl>' +
      `<dt>Estimate was</dt><dd>${estimate}${delta != null ? ` (${delta >= 0 ? '+' : ''}${delta.toFixed(0)}%)` : ''}</dd>` +
      (data.departs ? `<dt>Outbound departs</dt><dd>${data.departs}</dd>` : '') +
      (data.arrives ? `<dt>Outbound arrives</dt><dd>${data.arrives}</dd>` : '') +
      (data.airline ? `<dt>Airline</dt><dd>${data.airline}</dd>` : '') +
      (data.duration ? `<dt>Duration</dt><dd>${data.duration}</dd>` : '') +
      (data.stops_out != null ? `<dt>Stops</dt><dd>${fmtStops(data.stops_out)}</dd>` : '') +
      (data.cached ? '<dt>Source</dt><dd>previously verified</dd>' : '') +
      '</dl>' +
      // Filled in by the parallel times request from the board source, which covers both
      // legs and works at horizons the Google cross-check cannot reach.
      '<div id="paneltimes"></div>' +
      (cell.link ? `<p><a href="${cell.link}" target="_blank" rel="noopener">Book on ${sourceName(cell.source)}</a></p>` : '') +
      (data.link ? `<p><a href="${data.link}" target="_blank" rel="noopener">Open on Google Flights</a></p>` : '')
  );
  restoreTimes();

  // Fold the verified total back into the board so the colour scale reflects reality.
  const stored = state.destinations.get(dest.destination);
  if (stored) {
    let target = stored.cells.find((c) => c.depart === cell.depart && c.ret === cell.ret);
    if (!target) {
      target = { depart: cell.depart, ret: cell.ret, nights: cell.nights || 0, estimate: null, unit_price: null, currency: cur };
      stored.cells.push(target);
    }
    target.total = data.total;
    target.verified = true;
    target.airline = data.airline;
    if (data.stops_out != null) target.transfers = data.stops_out;
    // `best` arrives as its own object, not a reference into `cells`, so recompute it
    // from scratch. A verified price is often WORSE than the estimate it replaces, so
    // this must be able to move `best` up as well as down.
    stored.best = stored.cells.reduce(
      (acc, c) => (acc === null || cellValue(c) < cellValue(acc) ? c : acc),
      null
    );
    render();
  }
}

function addDays(iso, n) {
  const d = new Date(iso + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return isoLocal(d);
}

/* ---------------------------------------------------------------- cross-hair */

const pinned = new WeakMap(); // table -> {r, c}

/** Light the departure column and return row that a cell sits on. */
function highlightCross(table, r, c, pin) {
  clearCross(table);
  if (Number.isNaN(r) || Number.isNaN(c)) return;
  for (const el of table.querySelectorAll(`[data-c="${c}"]`)) el.classList.add('cross-col');
  for (const el of table.querySelectorAll(`[data-r="${r}"]`)) el.classList.add('cross-row');
  const cell = table.querySelector(`td[data-r="${r}"][data-c="${c}"]`);
  if (cell) cell.classList.add('cross-at');
  if (pin) pinned.set(table, { r, c });
}

function clearCross(table) {
  for (const el of table.querySelectorAll('.cross-col, .cross-row, .cross-at')) {
    el.classList.remove('cross-col', 'cross-row', 'cross-at');
  }
}

/** Clicking a cell pins its cross-hair, so it survives the mouse leaving the grid. */
function pinCross(table, r, c) {
  highlightCross(table, r, c, true);
}

/** On mouse-out fall back to the pinned cell, if any. */
function restorePinned(table) {
  const p = pinned.get(table);
  if (p) highlightCross(table, p.r, p.c, true);
  else clearCross(table);
}

/* --------------------------------------------------------------- locate best */

/** Scroll a card's grid so its cheapest cell is centred, and flash it. `quiet` is the
 *  auto-locate on first opening a destination: same move and flash, but no status line and
 *  no smooth animation (there is no gesture to follow). */
function locateBest(card, dest, { quiet = false, flash = true } = {}) {
  const wrap = card.querySelector('.matrix-wrap');
  const target = card.querySelector('td.best-board') || card.querySelector('td.best-here');
  if (!wrap || !target) return;

  // Centre it manually rather than scrollIntoView, which would also scroll the page and
  // move every other card out from under the pointer.
  wrap.scrollTo({
    left: Math.max(0, target.offsetLeft - wrap.clientWidth / 2 + target.offsetWidth / 2),
    top: Math.max(0, target.offsetTop - wrap.clientHeight / 2 + target.offsetHeight / 2),
    behavior: quiet || REDUCE_MOTION.matches ? 'auto' : 'smooth',
  });
  rememberScroll(dest.destination, wrap);

  if (flash) {
    target.classList.remove('flash');
    void target.offsetWidth;        // restart the animation if it is already running
    target.classList.add('flash');
    setTimeout(() => target.classList.remove('flash'), 1600);
  }

  if (quiet) return;

  // Keyboard path: the locate BUTTON hands focus to the cheapest cell, so the next Enter
  // prices it. Not on the auto-locate: the user may still be in the search bar or the list.
  if (target.getAttribute('role') === 'button') {
    target.tabIndex = 0;
    target.focus({ preventScroll: true });
  }

  const best = dest.best;
  if (best) {
    $('growing').hidden = false;
    $('growing').textContent =
      `${dest.city}: cheapest is ${fmtMoney(cellValue(best), state.meta.currency)} on ` +
      `${weekday(best.depart)} ${shortDate(best.depart)} → ${weekday(best.ret)} ${shortDate(best.ret)} (${best.nights}n)`;
    clearTimeout(locateBest._timer);
    locateBest._timer = setTimeout(() => { $('growing').hidden = true; }, 6000);
  }
}

/* ----------------------------------------------------- widen ONE destination */

/* Widen a single destination's travel period by a week at each end and re-price just it.
 *
 * Per destination rather than per board, because that is how the need actually arises: you
 * narrow to a candidate or two and want more dates for THOSE, and widening one costs one
 * destination's worth of provider calls instead of twenty.
 *
 * The cost is real and worth stating: a widened destination no longer shares its axes with
 * the rest of the board, so the same grid position stops meaning the same date pair across
 * destinations. Comparing by headline price still works, which is what the cheapest-first
 * ordering and the headline band are for.
 *
 * /api/extend already takes a destinations list, so asking for exactly one needs no backend
 * change. Its axes reply is stored per destination in destAxes rather than on meta, so the
 * rest of the board keeps the axes it was searched on.
 */
const WIDEN_STEP_DAYS = 7;
const MAX_PERIOD_DAYS = 60;      // a 60-day period is already ~55x55 cells for one grid
const widening = new Set();      // IATA codes currently being re-priced

function periodOf(dest) {
  const ax = axesFor(dest);
  if (!ax.departs.length || !ax.returns.length) return null;
  const start = ax.departs[0];
  const end = ax.returns[ax.returns.length - 1];
  const days = Math.round(
    (new Date(end + 'T00:00:00') - new Date(start + 'T00:00:00')) / 86400000
  );
  return { start, end, days };
}

function canWiden(dest) {
  const p = periodOf(dest);
  return !!p && p.days + 2 * WIDEN_STEP_DAYS <= MAX_PERIOD_DAYS;
}

function widenDestination(dest) {
  const code = dest.destination;
  const p = periodOf(dest);
  if (widening.has(code) || !p || !canWiden(dest)) return;

  const start = addDays(p.start, -WIDEN_STEP_DAYS);
  const end = addDays(p.end, WIDEN_STEP_DAYS);
  widening.add(code);
  render();

  fetch('/api/extend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: state.meta.origin,
      depart_date: start,
      return_date: end,
      destinations: [code],
      // Carried deliberately: without these the backend falls back to its 5-9 default and
      // rebuilds the axes for a trip length nobody asked for.
      nights_min: state.constraints.min,
      nights_max: state.constraints.max,
      adults: state.meta.adults,
      children: state.meta.children,
      currency: state.meta.currency,
      nonstop_only: state.meta.nonstop_only,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (!data.extend_id) throw new Error('extend failed');
      const source = new EventSource(`/api/extend/${data.extend_id}/stream`);
      source.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'axes') {
          // Per destination, NOT on meta: the rest of the board keeps its own axes.
          destAxes.set(code, { departs: msg.depart_dates, returns: msg.return_dates });
          render();
        } else if (msg.type === 'destination') {
          state.destinations.set(msg.destination, msg);
          recomputeBest(msg.destination);
          render();
        }
      };
      const finish = () => {
        source.close();
        widening.delete(code);
        render();
      };
      source.addEventListener('end', finish);
      source.onerror = finish;
    })
    .catch(() => {
      widening.delete(code);
      render();
    });
}
/* ------------------------------------------------------- matrix scroll memory */

const scrollOffsets = new Map(); // IATA -> {x, y}

/** Keep the last scroll position so a re-render does not jump back to the corner. */
function rememberScroll(dest, wrap) {
  scrollOffsets.set(dest, { x: wrap.scrollLeft, y: wrap.scrollTop });
}

/* ------------------------------------------------ apply a live-priced cell */

/** Fold one Google-Flights-priced cell into the board model. */
function applyCell(dest, msg) {
  const stored = state.destinations.get(dest.destination);
  if (!stored) return;
  let cell = stored.cells.find((c) => c.depart === msg.depart_date && c.ret === msg.return_date);
  if (!cell) {
    const nights = Math.round(
      (new Date(msg.return_date) - new Date(msg.depart_date)) / 86400000
    );
    cell = {
      depart: msg.depart_date, ret: msg.return_date, nights,
      estimate: null, unit_price: null, currency: state.meta.currency,
    };
    stored.cells.push(cell);
  }
  cell.total = msg.total;
  cell.verified = true;
  if (msg.airline) cell.airline = msg.airline;
  if (msg.stops != null) cell.transfers = msg.stops;
}

/* ------------------------------------------------- auto-upgrade Kiwi -> Google */

const AUTO_VERIFY_CELLS = 40;      // total cells to upgrade automatically
const AUTO_VERIFY_PER_DEST = 6;    // per destination, so no single city eats the budget
let autoSource = null;

/** After the fast Kiwi board lands, quietly re-price its cheapest cells on Google Flights.
 *  Cheapest-first because that is where a booking decision actually turns, and where a
 *  headline fare is least likely to survive contact with five passengers. */
function startAutoVerify() {
  if (!$('autoverify').checked || !state.meta || autoSource) return;

  // Take each destination's own cheapest cells and interleave them, rather than a flat
  // cheapest-N across the board. A single cheap destination would otherwise monopolise the
  // whole budget - measured: all 40 slots went to one city, which then turned out to be a
  // route Google cannot price at all, so nothing got cross-checked.
  const perDest = [];
  for (const dest of state.destinations.values()) {
    const own = dest.cells
      .filter((c) => !c.verified && cellValue(c) != null)
      .sort((a, b) => cellValue(a) - cellValue(b))
      .slice(0, AUTO_VERIFY_PER_DEST)
      .map((c) => ({ destination: dest.destination, depart_date: c.depart, return_date: c.ret }));
    if (own.length) perDest.push(own);
  }
  if (!perDest.length) return;

  const cells = [];
  for (let rank = 0; cells.length < AUTO_VERIFY_CELLS; rank += 1) {
    let added = false;
    for (const list of perDest) {
      if (rank < list.length && cells.length < AUTO_VERIFY_CELLS) {
        cells.push(list[rank]);
        added = true;
      }
    }
    if (!added) break;
  }

  const meta = state.meta;
  fetch('/api/autoverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: meta.origin, adults: meta.adults, children: meta.children,
      currency: meta.currency, nonstop_only: meta.nonstop_only, cells,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (!data.fill_id) return;
      const source = new EventSource(`/api/fill/${data.fill_id}/stream`);
      autoSource = source;
      let since = 0;
      source.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'fill_cell') {
          if (msg.ok) {
            const dest = state.destinations.get(msg.destination);
            if (dest) {
              applyCell(dest, msg);
              recomputeBest(msg.destination);
            }
          }
          $('growing').hidden = false;
          $('growing').textContent =
            `cross-checking cheapest fares on Google Flights… ${msg.progress}/${msg.total_cells}`;
          if (++since >= 6) { since = 0; render(); }
        } else if (msg.type === 'fill_done') {
          $('growing').hidden = true;
        }
      };
      const finish = () => {
        source.close();
        autoSource = null;
        $('growing').hidden = true;
        render();
      };
      source.addEventListener('end', finish);
      source.onerror = finish;
    })
    .catch(() => { autoSource = null; });
}

function stopAutoVerify() {
  if (autoSource) {
    autoSource.close();
    autoSource = null;
  }
  $('growing').hidden = true;
}

/* ------------------------------------------- live-price the OPEN destination's grid

   With one destination on screen at a time, pricing its whole trip-length band on Google
   Flights is cheap: one grid is ~40-120 cells, seconds of work, versus the thousands a
   whole-board fill would be. Kicked off when a destination becomes the selected one, once
   per destination per search, gated on the same "Auto-refresh" toggle. Moving to another
   destination cancels the one in flight. */
const OPEN_FILL_CAP = 120;
const openFilled = new Set();     // destinations whose band fill has been started this search
let openFillSource = null;
let openFillId = null;
let openFillFor = null;           // destination the active/last fill belongs to

/** Every (departure, return) pair in this destination's asked trip-length band that is not
 *  already a live price, priced-estimate cells first (cheapest first) then blanks. */
function bandCells(dest) {
  const meta = state.meta;
  const { departs, returns } = axesFor(dest);
  const span = meta.nights_span && meta.nights_span.length ? new Set(meta.nights_span) : null;
  const byKey = new Map(dest.cells.map((c) => [c.depart + '|' + c.ret, c]));
  const out = [];
  for (const depart of departs) {
    for (const ret of returns) {
      if (ret < depart) continue;
      const nights = Math.round((new Date(ret) - new Date(depart)) / 86400000);
      if (span && !span.has(nights)) continue;
      const c = byKey.get(depart + '|' + ret);
      if (c && c.verified) continue;
      out.push({ depart, ret, sort: c && cellValue(c) != null ? cellValue(c) : Infinity });
    }
  }
  out.sort((a, b) => a.sort - b.sort);
  return out.slice(0, OPEN_FILL_CAP).map((c) => ({
    destination: dest.destination, depart_date: c.depart, return_date: c.ret,
  }));
}

function stopOpenFill() {
  if (openFillId) fetch(`/api/fill/${openFillId}/cancel`, { method: 'POST' }).catch(() => {});
  if (openFillSource) openFillSource.close();
  openFillSource = null;
  openFillId = null;
}

function fillOpenDestination(dest) {
  if (!dest || !state.meta || !$('autoverify').checked) return;
  const code = dest.destination;
  if (openFillFor === code) return;      // already handled this selection
  stopOpenFill();
  openFillFor = code;
  if (openFilled.has(code)) return;      // already done once this search
  openFilled.add(code);

  const cells = bandCells(dest);
  if (!cells.length) return;

  const meta = state.meta;
  const city = dest.city;
  fetch('/api/autoverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: meta.origin, adults: meta.adults, children: meta.children,
      currency: meta.currency, nonstop_only: meta.nonstop_only, cells,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (!data.fill_id || openFillFor !== code) return;
      openFillId = data.fill_id;
      const source = new EventSource(`/api/fill/${data.fill_id}/stream`);
      openFillSource = source;
      let since = 0;
      source.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'fill_cell') {
          const d = state.destinations.get(msg.destination);
          if (msg.ok && d) { applyCell(d, msg); recomputeBest(msg.destination); }
          $('growing').hidden = false;
          $('growing').textContent =
            `pricing ${city} on Google Flights… ${msg.progress}/${msg.total_cells}`;
          if (++since >= 5) { since = 0; if (state.selected === code) render(); }
        } else if (msg.type === 'fill_done') {
          $('growing').hidden = true;
        }
      };
      const finish = () => {
        source.close();
        if (openFillSource === source) stopOpenFill();
        $('growing').hidden = true;
        if (state.selected === code) render();
      };
      source.addEventListener('end', finish);
      source.onerror = finish;
    })
    .catch(() => { openFillSource = null; openFillId = null; });
}

function recomputeBest(code) {
  const stored = state.destinations.get(code);
  if (!stored || !stored.cells.length) return;
  stored.best = stored.cells.reduce(
    (acc, c) => (acc === null || cellValue(c) < cellValue(acc) ? c : acc),
    null
  );
  stored.coverage.populated = stored.cells.length;
}

/* -------------------------------------------------------------------- panel */

function openPanel(html) {
  $('panelbody').innerHTML = html;
  $('panel').classList.add('open');
}

$('panelclose').addEventListener('click', () => $('panel').classList.remove('open'));

/* ------------------------------------------------------------------- search */

function startSearch() {
  if (state.source) state.source.close();
  // On a phone the search bar and filter panel fill the screen, so fold both away on
  // search — the results need the room. On desktop they wrap, so leave them.
  if (window.matchMedia('(max-width: 720px)').matches) {
    document.body.classList.remove('opts-open', 'search-open');
    $('optsbtn').setAttribute('aria-expanded', 'false');
    $('editsearch').setAttribute('aria-expanded', 'false');
  }
  renderEditSummary();
  state.destinations.clear();
  state.meta = null;
  $('dlist').replaceChildren();
  $('ddetail').replaceChildren();
  document.body.classList.remove('detail-open', 'has-board', 'show-table');
  $('tabletoggle').textContent = 'Table';
  $('tabletoggle').setAttribute('aria-pressed', 'false');
  $('tableview').replaceChildren();
  $('errors').textContent = '';
  // Until the first destination lands the board area would be blank; hold a placeholder
  // there so the wait reads as work in progress, not a broken page.
  $('empty').hidden = false;
  $('empty').classList.add('is-searching');
  $('empty').textContent = 'Finding cheap destinations…';
  $('boardtools').hidden = true;   // no results yet
  // Orientation is a first-run thing; once you've searched, you know. The date hint is
  // part of that same orientation (the field labels and the first-run lede already say
  // it), and it was costing a permanent line in the status strip above every board.
  $('firstrun').hidden = true;
  $('datehint').hidden = true;
  stopAutoVerify();             // a new search invalidates any in-flight cross-check
  stopOpenFill();
  openFilled.clear();
  openFillFor = null;
  $('growing').hidden = true;   // clear any stale rate-limit / widening notice
  $('note').hidden = true;
  scrollOffsets.clear();
  animatedDests.clear();        // a new board: let every destination animate in again
  state.selected = null;        // and let the new cheapest be the one that opens
  userPickedDest = false;
  destAxes.clear();             // every destination back on the board's own axes
  widening.clear();
  state.searchSignature = searchSignature();
  // Deliberately NOT disabled: a long search used to leave the button dead while it also
  // looked amber/clickable, so changing a setting mid-search trapped you. Pressing Search
  // again simply abandons the running stream and starts over (startSearch closes it above).
  $('go').classList.remove('stale');
  $('go').classList.add('running');
  $('go').textContent = 'Searching…';
  $('stop').hidden = false;
  $('stalenote').hidden = true;
  $('progress').textContent = 'Finding destinations…';

  const body = {
    origin: $('origin').value.trim().toUpperCase(),
    depart_date: $('depart').value,
    return_date: $('ret').value,
    adults: Number($('adults').value),
    children: Number($('children').value),
    currency: $('currency').value,
    max_destinations: Number($('dests').value),
    nonstop_only: $('nonstop').checked,
    max_price: $('maxprice').value ? Number($('maxprice').value) : null,
    // Search scope: the Destinations tree. Empty = everywhere. The budget is spent inside
    // the selection at discovery, not on the cheapest destinations anywhere.
    country_codes: [...state.regions],
    // In range mode the two dates bound a period and the nights box says what to look for
    // inside it, so the nights constraint drives the search instead of filtering it after.
    nights_min: $('nmin').value === '' ? null : Number($('nmin').value),
    nights_max: $('nmax').value === '' ? null : Number($('nmax').value),
    depart_hour_from: $('dephfrom').value === '' ? null : Number($('dephfrom').value),
    depart_hour_to: $('dephto').value === '' ? null : Number($('dephto').value),
    return_hour_from: $('rethfrom').value === '' ? null : Number($('rethfrom').value),
    return_hour_to: $('rethto').value === '' ? null : Number($('rethto').value),
  };

  boardToUrl();   // this board is now bookmarkable / shareable

  fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
    .then((r) => r.json())
    .then((data) => {
      if (!data.search_id) throw new Error(data.detail || 'search failed');
      state.searchId = data.search_id;
      consume(data.search_id);
    })
    .catch((err) => {
      console.debug('search failed:', err);
      $('go').classList.remove('running');
      $('go').textContent = 'Search';
      $('stop').hidden = true;
      $('errors').textContent = /failed to fetch|networkerror/i.test(String(err))
        ? "Couldn't reach the server. Check your connection and try again."
        : "The search couldn't start. Try again in a moment.";
      $('progress').textContent = '';
    });
}

/* Stop a running search. Closes the stream immediately and tells the backend to stop
   at the next destination boundary; whatever already rendered stays on screen. */
function stopSearch() {
  if (state.searchId) {
    fetch(`/api/search/${state.searchId}/cancel`, { method: 'POST' }).catch(() => {});
  }
  if (state.source) { state.source.close(); state.source = null; }
  $('go').classList.remove('running');
  $('go').textContent = 'Search';
  $('stop').hidden = true;
  $('growing').hidden = true;
  $('progress').textContent = state.destinations.size
    ? `Stopped. ${state.destinations.size} destination${state.destinations.size > 1 ? 's' : ''} loaded`
    : 'Search stopped';
  markSearchStale();
}

/* Live grid fill ------------------------------------------------------------------
 *
 * The backend streams one `cells` event per calendar column, so a grid paints as it
 * fills instead of appearing whole. Two things keep that from being expensive:
 *
 *  - Only the OPEN grid is on screen. Columns for the other nineteen destinations are
 *    merged into state and never trigger a paint; their card renders once, complete,
 *    when its `destination` event lands.
 *  - Bursts coalesce. Four workers finishing at once would otherwise be four renders of
 *    the same table, so a paint is scheduled on the next frame and repeated requests
 *    collapse into it.
 *
 * The colour ramp is recomputed as cells arrive, so a half-filled grid is ranked against
 * what is known so far and the colours settle as the rest lands. That is honest to the
 * per-matrix scale rule: green means cheapest *here*, and "here" grows.
 */
let paintQueued = false;

function schedulePaint() {
  if (paintQueued) return;
  paintQueued = true;
  requestAnimationFrame(() => {
    paintQueued = false;
    render();
  });
}

function mergeCells(code, cells) {
  const dest = state.destinations.get(code);
  if (!dest || !cells || !cells.length) return;
  // Key by the date pair: a column can legitimately be re-sent (a re-fill at a wider
  // window), and the later value is the fresher one.
  const byPair = new Map((dest.cells || []).map((c) => [`${c.depart}|${c.ret}`, c]));
  for (const cell of cells) byPair.set(`${cell.depart}|${cell.ret}`, cell);
  dest.cells = [...byPair.values()].sort(
    (a, b) => (a.depart === b.depart ? a.ret.localeCompare(b.ret) : a.depart.localeCompare(b.depart)));
  dest.filling = true;
  // Painting is only worth it for the grid the user is actually looking at.
  if (state.selected === code) schedulePaint();
}

function consume(searchId) {
  const source = new EventSource(`/api/search/${searchId}/stream`);
  state.source = source;
  let expected = 0;
  let seen = 0;

  source.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'meta') {
      state.meta = msg;
      state.displayCurrency = msg.currency;   // board priced in this; dropdown starts here
      $('currency').value = msg.currency;
      syncDateMode();
      $('progress').textContent = `Searching from ${msg.origin_city} (${msg.origin})…`;
    } else if (msg.type === 'candidates') {
      expected = msg.count;
      $('progress').textContent = `${expected} destinations found, filling grids…`;
    } else if (msg.type === 'destination') {
      // Previews arrive first and are replaced in place by the filled card, so only the
      // filled one counts towards progress - otherwise a 20-destination board reports 40.
      state.destinations.set(msg.destination, msg);
      if (msg.preview) {
        $('progress').textContent = `${state.destinations.size} destinations, filling grids…`;
      } else {
        seen += 1;
        $('progress').textContent = `${seen} of ${expected} grids…`;
      }
      $('empty').hidden = true;
      $('empty').classList.remove('is-searching');
      render();
    } else if (msg.type === 'cells') {
      mergeCells(msg.destination, msg.cells);
    } else if (msg.type === 'destination_empty') {
      // Discovery priced this city, but nothing is bookable at the trip lengths asked for,
      // so the backend leaves it off the board. Drop its preview card too, or it sits in
      // the list saying "Finding dates..." for the rest of the session, for dates that do
      // not exist.
      state.destinations.delete(msg.destination);
      seen += 1;
      render();
    } else if (msg.type === 'destination_error') {
      $('errors').textContent = `${msg.destination}: ${msg.message}`;
      seen += 1;
    } else if (msg.type === 'filter_applied') {
      $('note').hidden = false;
      $('note').textContent = msg.matched
        ? `Searching only destinations matching "${msg.filter}": ${msg.matched} of ${msg.considered} reachable destinations matched.`
        : `Nothing reachable from here matches "${msg.filter}". Clear the filter and search again.`;
    } else if (msg.type === 'provider_status') {
      // Rate-limit waits stream in while they happen, so a pause never reads as a hang.
      $('growing').hidden = false;
      $('growing').textContent = msg.message;
    } else if (msg.type === 'provider_fallback') {
      // Live source unavailable (usually a rate limit). Say so plainly, because the
      // prices on screen now mean something different.
      $('note').textContent = msg.message;
      $('note').hidden = false;
    } else if (msg.type === 'error') {
      $('errors').textContent = msg.message;
    } else if (msg.type === 'done') {
      $('growing').hidden = true;
      $('empty').classList.remove('is-searching');
      if (msg.destinations) {
        $('progress').textContent = `${msg.destinations} destinations, cheapest first`;
      } else {
        $('progress').textContent = '';
        $('empty').hidden = false;
        $('empty').textContent = msg.note || 'Nothing came back for this window.';
      }
      // The backend's sparse-cache warning is deliberately not surfaced: every estimate is
      // clickable for a live price, so a "many cells are blank" banner just adds anxiety.
      $('note').hidden = true;
      // Board is up; now upgrade its cheapest cells to live Google prices in the background.
      if (msg.destinations) startAutoVerify();
    }
  };

  const finish = () => {
    source.close();
    state.source = null;
    $('go').classList.remove('running');
    $('go').textContent = 'Search';
    $('stop').hidden = true;
    markSearchStale();   // settings may have been changed while the search ran
    if (state.meta) render();   // paint the settled board and kick off the open-grid fill
  };
  source.addEventListener('end', finish);
  source.onerror = finish;
}

/* --------------------------------------------------------------------- init */

$('go').addEventListener('click', startSearch);
$('stop').addEventListener('click', stopSearch);
$('perperson').addEventListener('change', (e) => {
  state.perPerson = e.target.checked;
  if (state.meta) render();
});
/* Filtering is purely a view over the board already loaded - it never refetches, so it
   stays instant and costs no API calls. */
buildDowPicker('dowdep', 'dep');
buildDowPicker('dowret', 'ret');

/* Hour pickers. Unlike the day and night constraints these are SEARCH parameters: the
   price calendar returns no departure time, so there is nothing to filter client-side.
   Changing them therefore needs a new Search, and the button says so. */
function buildHourPicker(id, isEnd) {
  const sel = $(id);
  const any = document.createElement('option');
  any.value = '';
  any.textContent = 'any';
  sel.appendChild(any);
  for (let h = 0; h < 24; h += 1) {
    const o = document.createElement('option');
    o.value = String(h);
    o.textContent = `${String(h).padStart(2, '0')}:00`;
    sel.appendChild(o);
  }
}
['dephfrom', 'dephto', 'rethfrom', 'rethto'].forEach((id, i) => buildHourPicker(id, i % 2 === 1));

/* Which controls change what is FETCHED, so require a new Search. Everything else (the
   weekday pickers, the destination box after a search) is a view over loaded cells and
   applies instantly. Changing a date used to silently leave the old board on screen with
   no hint that it was stale. */
const SEARCH_INPUTS = [
  'origin', 'depart', 'ret', 'nmin', 'nmax', 'adults', 'children', 'dests', 'maxprice',
  'nonstop', 'dephfrom', 'dephto', 'rethfrom', 'rethto',
];
// 'currency' is deliberately NOT a search input: once a board is loaded, changing it
// just re-labels the numbers via FX conversion. A fresh search still fetches in
// whatever the dropdown shows.

function searchSignature() {
  const parts = SEARCH_INPUTS.map((id) => {
    const el = $(id);
    return el.type === 'checkbox' ? String(el.checked) : el.value;
  });
  parts.push('r:' + [...state.regions].sort().join(','));
  return parts.join('|');
}

/** Highlight Search when the form no longer matches the board on screen. */
function markSearchStale() {
  const stale = !!state.meta && searchSignature() !== state.searchSignature;
  $('go').classList.toggle('stale', stale);
  $('go').title = stale ? 'Settings changed. Press Search to update the board' : '';
  $('stalenote').hidden = !stale;
  $('stalenote').textContent = stale
    ? 'showing the previous search, press Search to apply your changes'
    : '';
}

for (const id of SEARCH_INPUTS.concat(['nmin', 'nmax'])) {
  const el = $(id);
  el.addEventListener('change', markSearchStale);
  el.addEventListener('input', markSearchStale);
}

/* ---------------------------------------------------------------- region tree */
/* Collapsible continent -> subregion -> country. Checking a node checks everything
   under it; the selected country codes become the search's `country_codes` filter,
   spent inside the selection at discovery (composes with "Only destinations"). */

function buildRegionTree() {
  fetch('/api/regions')
    .then((r) => r.json())
    .then((data) => renderRegionTree(data.tree || []))
    .catch(() => {
      $('regiontree').innerHTML = '<span class="region-loading">regions unavailable</span>';
    });
}

// For the tag summary: highest-level groups first, so "all of Southern Europe" reads as
// one tag rather than ten country tags.
const regionMeta = { groups: [], name: {} };  // groups: [{label, codes, rank}], name: code->name

function renderRegionTree(tree) {
  const root = $('regiontree');
  root.replaceChildren();
  regionMeta.groups = [];
  regionMeta.name = {};
  for (const cont of tree) {
    const contCodes = cont.subregions.flatMap((s) => s.countries.map((c) => c.code));
    regionMeta.groups.push({ label: cont.continent, codes: contCodes, rank: 0 });
    const subs = cont.subregions.map((sub) => {
      const codes = sub.countries.map((c) => c.code);
      regionMeta.groups.push({ label: sub.name, codes, rank: 1 });
      for (const c of sub.countries) regionMeta.name[c.code] = c.name;
      return regionBranch(sub.name, codes, sub.countries.map((c) => regionLeaf(c.code, c.name)));
    });
    root.appendChild(regionBranch(cont.continent, contCodes, subs));
  }
  root.addEventListener('change', onRegionChange);
  $('regionclear').addEventListener('click', () => { state.regions.clear(); afterRegionChange(); });
  wireDestCombo();
  afterRegionChange();
  refreshRegionCounts();
}

function regionBranch(label, codes, children) {
  const wrap = document.createElement('div');
  wrap.className = 'rnode';
  const head = document.createElement('div');
  head.className = 'rhead';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'rtoggle';
  toggle.setAttribute('aria-expanded', 'false');
  toggle.textContent = '›';
  const lab = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.dataset.codes = codes.join(',');
  lab.append(cb, ' ', label, spanCount());
  head.append(toggle, lab);
  const kids = document.createElement('div');
  kids.className = 'rchildren';
  kids.hidden = true;
  kids.append(...children);
  toggle.addEventListener('click', () => {
    kids.hidden = !kids.hidden;
    toggle.setAttribute('aria-expanded', String(!kids.hidden));
    toggle.textContent = kids.hidden ? '›' : '˅';
  });
  wrap.append(head, kids);
  return wrap;
}

function regionLeaf(code, name) {
  const lab = document.createElement('label');
  lab.className = 'rleaf';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.value = code;
  cb.dataset.codes = code;
  lab.append(cb, ' ', name, spanCount(code));
  return lab;
}

function spanCount(code) {
  const s = document.createElement('span');
  s.className = 'rcount';
  if (code) s.dataset.code = code;
  return s;
}

function onRegionChange(e) {
  const cb = e.target;
  if (cb.type !== 'checkbox') return;
  for (const c of (cb.dataset.codes || '').split(',').filter(Boolean)) {
    cb.checked ? state.regions.add(c) : state.regions.delete(c);
  }
  afterRegionChange();
}

/** Re-sync every checkbox to `state.regions`, then tags, clear button, counts, stale mark. */
function afterRegionChange() {
  for (const cb of $('regiontree').querySelectorAll('input[type=checkbox]')) {
    const codes = (cb.dataset.codes || '').split(',').filter(Boolean);
    const on = codes.filter((c) => state.regions.has(c)).length;
    cb.checked = on > 0 && on === codes.length;
    cb.indeterminate = on > 0 && on < codes.length;
  }
  $('regionclear').hidden = state.regions.size === 0;
  renderDestTags();
  refreshRegionCounts();
  markSearchStale();
}

/* -------------------------------------------------- Destinations combobox (tags + popover) */

function wireDestCombo() {
  const control = $('destcontrol');
  const input = $('regionsearch');
  control.addEventListener('mousedown', (e) => {
    if (e.target.closest('.dest-tag-x')) return;   // let the × handler run
    if (e.target !== input) e.preventDefault();     // don't steal focus from a click on chrome
    openDestPop();
    input.focus();
  });
  input.addEventListener('focus', openDestPop);
  input.addEventListener('input', (e) => { openDestPop(); filterRegionTree(e.target.value.trim().toLowerCase()); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeDestPop(); input.blur(); }
    // Backspace on an empty input removes the last tag.
    if (e.key === 'Backspace' && input.value === '' && state.regions.size) {
      const last = [...destTagList()].pop();
      if (last) { for (const c of last.codes) state.regions.delete(c); afterRegionChange(); }
    }
  });
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('#destcombo')) closeDestPop();
  });
}

function openDestPop() {
  $('destpop').hidden = false;
  $('destcombo').classList.add('open');
  $('regionsearch').setAttribute('aria-expanded', 'true');
}
function closeDestPop() {
  $('destpop').hidden = true;
  $('destcombo').classList.remove('open');
  $('regionsearch').setAttribute('aria-expanded', 'false');
  const input = $('regionsearch');
  if (input.value) { input.value = ''; filterRegionTree(''); }
}

/** Collapse the selection to the fewest tags: a fully-selected continent or subregion
    becomes one tag; leftover countries get their own. */
function destTagList() {
  const sel = state.regions;
  if (!sel.size) return [];
  const covered = new Set();
  const tags = [];
  for (const g of regionMeta.groups) {            // rank 0 (continents) come first
    if (g.codes.length && g.codes.every((c) => sel.has(c)) && !g.codes.some((c) => covered.has(c))) {
      tags.push({ label: g.label, codes: g.codes });
      for (const c of g.codes) covered.add(c);
    }
  }
  for (const c of sel) {
    if (!covered.has(c)) tags.push({ label: regionMeta.name[c] || c, codes: [c] });
  }
  return tags;
}

function renderDestTags() {
  const host = $('desttags');
  const tags = destTagList();
  host.replaceChildren(...tags.map((t) => {
    const el = document.createElement('span');
    el.className = 'dest-tag';
    el.append(t.label);
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'dest-tag-x';
    x.setAttribute('aria-label', `Remove ${t.label}`);
    x.textContent = '×';
    x.addEventListener('click', () => {
      for (const c of t.codes) state.regions.delete(c);
      afterRegionChange();
    });
    el.append(x);
    return el;
  }));
  $('destcombo').classList.toggle('has-tags', tags.length > 0);
  $('regionsearch').placeholder = tags.length ? '' : 'Everywhere';
}

/** Post-search: how many loaded destinations sit under each node. */
function refreshRegionCounts() {
  const tree = $('regiontree');
  if (!tree || !tree.querySelector('.rnode')) return;
  const byCode = {};
  for (const d of state.destinations.values()) {
    const c = (d.country || '').toUpperCase();
    if (c) byCode[c] = (byCode[c] || 0) + 1;
  }
  const has = state.destinations.size > 0;
  for (const s of tree.querySelectorAll('.rcount')) {
    const codes = s.dataset.code
      ? [s.dataset.code]
      : (s.closest('.rhead').querySelector('input').dataset.codes || '').split(',').filter(Boolean);
    const n = codes.reduce((a, c) => a + (byCode[c] || 0), 0);
    s.textContent = has && n ? String(n) : '';
  }
}

/* The two dates bound a PERIOD; Nights is the trip length to look for inside it.
   (Kept as a named function because several places call it after the axes change.) */
function syncDateMode() {
  $('departlabel').textContent = 'Travel from';
  $('retlabel').textContent = 'Travel until';
  $('datehint').textContent =
    'the two dates bound a period; Nights is the trip length to look for inside it';
  if ($('nmin').value === '' && $('nmax').value === '') {
    $('nmin').value = '5';
    $('nmax').value = '9';
  }
  readNights();
}

function readNights() {
  const parse = (id) => ($(id).value === '' ? null : Number($(id).value));
  state.constraints.min = parse('nmin');
  state.constraints.max = parse('nmax');
  if (state.meta) render();
}
$('nmin').addEventListener('input', readNights);
$('nmax').addEventListener('input', readNights);

$('clearconstraints').addEventListener('click', () => {
  state.constraints.dep.clear();
  state.constraints.ret.clear();
  state.constraints.min = state.constraints.max = null;
  $('nmin').value = '';
  $('nmax').value = '';
  for (const id of ['dephfrom','dephto','rethfrom','rethto']) $(id).value = '';
  markSearchStale();
  for (const b of document.querySelectorAll('.dow button.on')) b.classList.remove('on');
  if (state.meta) render();
});

/* Typeahead over the Destinations tree: type a country / region / continent name and
   the tree collapses to the matches, auto-expanding the branches that contain them.
   Wired from wireDestCombo(); this is just the filter itself. */
function filterRegionTree(q) {
  const tree = $('regiontree');
  for (const node of tree.querySelectorAll('.rnode')) {
    const head = node.querySelector(':scope > .rhead');
    const kids = node.querySelector(':scope > .rchildren');
    const label = head.querySelector('label').textContent.toLowerCase();
    const selfMatch = !q || label.includes(q);
    const kidMatch = kids && [...kids.querySelectorAll('.rleaf, .rhead > label')]
      .some((el) => el.textContent.toLowerCase().includes(q));
    node.hidden = !(selfMatch || kidMatch);
    if (kids) {
      const open = !!q && kidMatch;
      kids.hidden = q ? !open : true;
      const tog = head.querySelector('.rtoggle');
      if (tog) {
        tog.setAttribute('aria-expanded', String(!kids.hidden));
        tog.textContent = kids.hidden ? '›' : '˅';
      }
    }
  }
  for (const leaf of tree.querySelectorAll('.rleaf')) {
    leaf.hidden = q ? !leaf.textContent.toLowerCase().includes(q) : false;
  }
}

/* Currency: with a board loaded, just convert the displayed numbers, no re-search.
   With no board yet, it's simply the currency the next search will fetch in. */
$('currency').addEventListener('change', (e) => {
  if (!state.meta) return;
  state.displayCurrency = e.target.value;
  $('panel').classList.remove('open');   // its numbers are now stale
  render();
});

$('autoverify').addEventListener('change', (e) => {
  if (e.target.checked) startAutoVerify();
  else stopAutoVerify();
});
/* One pane, two ways to read it: the colour grid or a sortable table of the same fares.
   The button names the view you'd switch TO. */
$('tabletoggle').addEventListener('click', () => {
  const table = document.body.classList.toggle('show-table');
  $('tabletoggle').textContent = table ? 'Matrix' : 'Table';
  $('tabletoggle').setAttribute('aria-pressed', String(table));
});

/* Desktop: fold the ranked list away and let the grid have the whole width. No effect on a
   phone, where the list and the grid already occupy the screen one at a time. */
$('listtoggle').addEventListener('click', () => {
  const collapsed = document.body.classList.toggle('list-collapsed');
  $('listtoggle').setAttribute('aria-pressed', String(collapsed));
  $('listtoggle').textContent = collapsed ? 'Show list' : 'Hide list';
});

/* Mobile: the options bar is collapsed by default behind this toggle, so it stops
   filling the screen. No effect on desktop, where the whole row just wraps. */
$('optsbtn').addEventListener('click', () => {
  const open = document.body.classList.toggle('opts-open');
  $('optsbtn').setAttribute('aria-expanded', open ? 'true' : 'false');
});

/* Mobile only (CSS hides #editsearch elsewhere): once a board exists the full search bar
   is folded to a one-line summary. This toggles it back open, and running a search folds
   it again (startSearch). */
function renderEditSummary() {
  const dests = state.regions && state.regions.size
    ? (state.regions.size === 1
        ? (regionMeta.name[[...state.regions][0]] || '1 place')
        : `${state.regions.size} places`)
    : 'Anywhere';
  // Terse on purpose — this has to fit one line on a narrow phone. Origin, where to, and
  // roughly when; the rest is a tap away.
  const w = $('whenselect');
  const label = w.options[w.selectedIndex]?.text || '';
  const when = w.value === 'flex'
    ? 'anytime'
    : label.replace(/^(\w{3})\w*/, '$1');   // "October 2026" -> "Oct 2026"
  $('editsearchtext').textContent =
    `${($('origin').value || '').toUpperCase()} → ${dests} · ${when}`;
  $('editsearch').querySelector('.edit-search-cue').textContent =
    document.body.classList.contains('search-open') ? 'Hide ▴' : 'Edit ▾';
}

$('editsearch').addEventListener('click', () => {
  const open = document.body.classList.toggle('search-open');
  $('editsearch').setAttribute('aria-expanded', open ? 'true' : 'false');
  if (!open) document.body.classList.remove('opts-open');
  renderEditSummary();
});
$('themetoggle').addEventListener('click', () => {
  const root = document.documentElement;
  /* Until data-theme is set the page is following the OS preference, so that preference
     is what the first click has to flip. Defaulting to 'dark' here instead made the first
     click a no-op for anyone whose OS is already dark: it set data-theme="dark" on an
     already-dark page, and only the second click did anything. */
  const current = root.getAttribute('data-theme')
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  root.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
  if (state.meta) render();
});

/* Keep the return date at or after the departure date. Picking a later departure than the
   current return would otherwise produce a window with no valid cells at all. */
function syncReturnDate() {
  const depart = $('depart').value;
  if (!depart) return;
  $('ret').min = depart;
  if ($('ret').value && $('ret').value < depart) $('ret').value = depart;
}

$('depart').addEventListener('change', syncReturnDate);
$('depart').addEventListener('input', syncReturnDate);

loadFx();
buildRegionTree();

/* "When" is a plain month picker plus an "anytime" span. It just writes the two exact
   date fields (which still drive everything); Options exposes those directly for anyone
   who wants a precise window. */
function buildWhenOptions() {
  const sel = $('whenselect');
  const now = new Date();
  const opts = [new Option('Anytime (next 3 months)', 'flex')];
  // Airlines load schedules ~11-12 months out; past that the board comes back empty.
  for (let i = 0; i < 13; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    opts.push(new Option(d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }), key));
  }
  sel.replaceChildren(...opts);
}

/** Reflect a preset's day-of-week choice in the picker and the constraint state. */
function setDow(key, days) {
  const set = state.constraints[key];
  set.clear();
  for (const d of days) set.add(d);
  const host = $(key === 'dep' ? 'dowdep' : 'dowret');
  [...host.children].forEach((btn, i) => btn.classList.toggle('on', set.has(i)));
}

function applyWhen() {
  const v = $('whenselect').value;
  if (v === 'flex') {
    $('depart').value = isoToday(21);
    $('ret').value = isoToday(21 + 90);
  } else {
    const [y, m] = v.split('-').map(Number);
    const first = new Date(y, m - 1, 1);
    const last = new Date(y, m, 0);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    $('depart').value = isoLocal(first < today ? today : first);
    $('ret').value = isoLocal(last);
  }
  syncReturnDate();
}

function applyTrip() {
  const [lo, hi] = $('tripselect').value.split(',');
  $('nmin').value = lo;
  $('nmax').value = hi;
  // A "weekend" means leaving Wed/Thu and back Sun/Mon; the longer presets have no
  // natural shape, so they clear the day filter.
  const weekendish = $('tripselect').value === '2,3' || $('tripselect').value === '3,4';
  setDow('dep', weekendish ? [3, 4] : []);       // Wed, Thu
  setDow('ret', weekendish ? [0, 1] : []);       // Sun, Mon
}

buildWhenOptions();
$('whenselect').addEventListener('change', () => { applyWhen(); markSearchStale(); });
$('tripselect').addEventListener('change', () => {
  applyTrip();
  markSearchStale();
  if (state.meta) render();   // the day-of-week part is a view filter
});

applyWhen();
applyTrip();

// A shared/bookmarked board carries its search in the query string; it wins over the
// defaults and prefills the form.
const urlBoard = boardFromUrl(new URLSearchParams(location.search));
syncDateMode();
syncReturnDate();

/* A URL that carries a search PREFILLS the form and stops there. It deliberately does not
   run the search itself.

   It used to auto-run, which is defensible (the link then always means "current fares")
   but turned every page refresh into a fresh 60-destination search: half a minute of
   waiting and a chunk of provider quota, just to redraw a board that was already on
   screen. Reloading during a session is far more common than wanting fresh prices, and
   pressing Search is one click, so the cheap default wins.

   The first-run panel and the date hint stay visible on purpose: the board really is
   empty, and a shared link may well be opened by somebody who has never seen this tool,
   for whom that panel is the only explanation of what the colours mean. */
if (urlBoard.size) {
  $('progress').textContent =
    'Your saved search is loaded. Press Search to price these dates.';
}

/* A shared link normally prefills and waits (a reload is not a request for fresh, expensive
   prices). `&run=1` opts a link into running on load — the form the "share this exact
   board, priced now" case wants. */
if (urlBoard.size && new URLSearchParams(location.search).get('run') === '1') {
  requestAnimationFrame(() => $('go').click());
}

/* Health only supplies defaults for fields the URL left unset. It is raced against a
   timeout because fetch has none of its own: a hanging request never settles, and when
   the auto-search was chained onto this promise's .finally() that silently made a
   bookmarked board unopenable. Nothing is chained onto it now, but the timeout still
   earns its keep by not leaving the form half-populated forever. If health loses the
   race we keep the markup's own defaults, which match the server's. */
const HEALTH_TIMEOUT_MS = 4000;

Promise.race([
  fetch('/api/health').then((r) => r.json()).catch(() => null),
  new Promise((resolve) => setTimeout(() => resolve(null), HEALTH_TIMEOUT_MS)),
])
  .then((h) => {
    if (!h || !h.defaults) return;   // lost the race, or unreachable: keep markup defaults
    if (!h.token_configured) {
      $('errors').textContent =
        'No Travelpayouts token configured. Add TRAVELPAYOUTS_TOKEN=... to the .env file in the project root, then restart.';
    }
    if (!urlBoard.has('from')) $('origin').value = h.defaults.origin;
    if (!urlBoard.has('currency')) $('currency').value = h.defaults.currency;
    if (!urlBoard.has('adults')) $('adults').value = h.defaults.adults;
    if (!urlBoard.has('children')) $('children').value = h.defaults.children;
    if (!urlBoard.has('places')) $('dests').value = h.defaults.max_destinations;
  })
  .catch(() => {});
