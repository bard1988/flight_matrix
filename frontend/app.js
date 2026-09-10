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
  places: new Set(),       // IATA codes picked from the typeahead (a city or airport)
  placeName: {},            // IATA -> display label, for the chip
  // `${dest}|${depart}|${ret}` keys for cells with a live price fetch in flight, so the
  // grid can show them mid-load. Survives the wholesale repaint: buildMatrix reads it.
  pendingCells: new Set(),
  // Multi view: one combined grid, several destinations stacked in every cell. Until the
  // user adds / removes / hides one (`touched`), `dests` tracks the three cheapest as the
  // board settles; after that it is frozen to their picks (dead codes still pruned).
  // `hidden` is temporarily-off; `axes` overrides meta's window after a Multi widen;
  // `density` sticks once the user picks Stacked/Strip (null = follow the screen).
  multi: { on: false, dests: [], hidden: new Set(), touched: false, axes: null, density: null },
};

const MULTI_CAP = 6;

const cellKey = (dest, depart, ret) => `${dest}|${depart}|${ret}`;

// Rough offline fallback, only used if the FX fetch fails. Does not need to be exact.
const FX_FALLBACK = { eur: 1, usd: 1.16, gbp: 0.86, ils: 3.5 };

const $ = (id) => document.getElementById(id);

/* Board data comes from an aggregator, or for its own routes direct from an airline. */
const AIRLINE_SOURCES = { wizz: 'Wizz Air', ryanair: 'Ryanair' };
const sourceName = (s) =>
  s === 'kiwi' ? 'Kiwi.com'
    : s === 'travelpayouts' ? 'Aviasales'
    : AIRLINE_SOURCES[s] || s || 'the fare cache';

/* A firm party price, or an extrapolation? Kiwi returns a real party total; an LCC's
   per-person fare scales linearly, so fare x party is firm too (ancillaries aside, like
   any headline fare). Only Travelpayouts single-ticket fares are the estimate. */
const isAirlineFare = (cell) => cell.source in AIRLINE_SOURCES;
const isFirmPrice = (cell) => cell.is_total || isAirlineFare(cell);
const fareNote = (cell) => (isAirlineFare(cell) ? ` — ${AIRLINE_SOURCES[cell.source]} fare, carry-on only` : '');
/* Sort order for the table's Source column: verified, then an airline's own fare, then estimate. */
const srcRank = (cell) => (cell.verified ? 2 : isAirlineFare(cell) ? 1 : 0);

/* One phrasing for stop counts everywhere: tooltip, table, panel. */
const fmtStops = (n) =>
  n == null ? '' : n === 0 ? 'nonstop' : `${n} stop${n > 1 ? 's' : ''}`;

/* "just now" / "12 min ago" / "3 h ago" / "2 days ago" from a minute count. */
const fmtAge = (min) => {
  if (min == null) return '';
  if (min < 2) return 'just now';
  if (min < 90) return `${Math.round(min)} min ago`;
  const h = min / 60;
  if (h < 36) return `${Math.round(h)} h ago`;
  return `${Math.round(h / 24)} days ago`;
};

const REDUCE_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)');

/* Cycling dots for the "still working" lines ("Finding dates", "Finding cheap
   destinations"). One shared counter, advanced by a rAF loop (dotLoop, below). Every
   ellipsis reads the CURRENT frame when it is built, so the list rebuilding many times a
   second while grids stream in re-applies that frame instead of resetting the cycle.

   NOT gated on prefers-reduced-motion: a text loading indicator is not vestibular motion,
   and this runs where a CSS keyframe animation would be damped to nothing by the global
   reduced-motion rule anyway. rAF (not setInterval) because mobile browsers throttle
   background timers hard; rAF just pauses with the tab, which is what we want. */
const DOT_FRAMES = ['.', '..', '...'];
let dotFrame = 0;
const dots = () => DOT_FRAMES[dotFrame % DOT_FRAMES.length];

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
  if ($('autoverify').checked) p.set('verify', '1');   // off by default, opt in explicitly
  if (state.regions.size) p.set('r', [...state.regions].join(','));
  if (state.places.size) p.set('p', [...state.places].join(','));
  if (state.multi.on) {
    p.set('view', 'multi');
    if (state.multi.dests.length) p.set('multi', state.multi.dests.join(','));
  }
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
  if (params.has('verify')) { $('autoverify').checked = params.get('verify') === '1'; seen.add('verify'); }
  if (params.has('r')) {
    for (const c of params.get('r').split(',').filter(Boolean)) state.regions.add(c.toUpperCase());
    seen.add('r');
  }
  if (params.has('p')) {
    for (const c of params.get('p').split(',').filter(Boolean)) {
      const code = c.toUpperCase();
      state.places.add(code);
      state.placeName[code] = code;   // real label hydrated async below
    }
    seen.add('p');
    hydratePlaceNames();
  }
  if (params.get('view') === 'multi') {
    state.multi.on = true;
    seen.add('view');
    if (params.has('multi')) {
      state.multi.dests = params.get('multi').split(',').map((c) => c.trim().toUpperCase()).filter(Boolean);
      state.multi.touched = true;   // an explicit list is the user's, not the default top-3
      seen.add('multi');
    }
  }
  // Mirror the shared controls onto their Options-panel twins and into state.
  $('currencyopt').value = $('currency').value;
  state.perPerson = $('perperson').checked;
  $('perpersonopt').checked = $('perperson').checked;
  return seen;
}

/** After a shared URL loads, swap the bare IATA codes on the place chips for city names. */
function hydratePlaceNames() {
  for (const code of state.places) {
    fetch(`/api/airport/${code}`).then((r) => r.json()).then((d) => {
      if (d && d.city && state.places.has(code)) { state.placeName[code] = d.city; renderDestTags(); }
    }).catch(() => {});
  }
}

/* -------------------------------------------------- keyboard-operable matrix cells */

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

/* The fare cells are large now (a headline price over a trip-length line), so they carry
   the currency symbol and the whole grouped number rather than the "1.2k" compaction the
   dense grid needed. Falls back to the compact form only past five figures, where the
   digits would wrap. */
function fmtCell(value) {
  if (value == null) return '';
  const n = Math.round(convert(value, state.meta && state.meta.currency));
  const to = state.displayCurrency || (state.meta && state.meta.currency);
  const symbol = { ils: '₪', eur: '€', usd: '$', gbp: '£' }[to] || '';
  return symbol + (n >= 100000 ? fmtCompact(value) : n.toLocaleString());
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
  } else if (isFirmPrice(cell)) {
    // Kiwi returns a real party total; a Wizz LCC fare scales linearly. Neither is an
    // extrapolation, so neither is labelled as one.
    rows.push(`<b>${fmtMoney(cell.estimate, cur)}</b> total for ${who} <span class="muted">via ${sourceName(cell.source)}${fareNote(cell)}</span>`);
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

  // Multi view takes over the whole board area: one combined grid instead of the ranked
  // list + focus layer. Everything above here (allowed cells, globalBest, the country
  // filter, the constraint note) is shared; the list / detail / table build below is not.
  document.body.classList.toggle('show-multi', state.multi.on);
  if (state.multi.on) {
    multiDests(ordered);   // seed / prune synchronously so boardToUrl sees the real list
    $('boardtools').hidden = state.destinations.size === 0;
    $('footnote').hidden = ordered.length === 0;
    document.body.classList.toggle('has-board', ordered.length > 0);
    $('legend').hidden = true;
    state.lastOrdered = ordered;
    scheduleMulti();
    return;
  }

  syncSelection(ordered);
  const selDest = ordered.find((d) => d.destination === state.selected) || null;

  // In the list -> focus-grid flow the detail pane is a full-window layer that is only
  // shown once a card is opened. Building its matrix (a wide date window is thousands of
  // <td>s with listeners) on every streamed destination while it is display:none is what
  // made the board feel stuck right after Search. Only build it when it is actually up.
  const detailOpen = document.body.classList.contains('detail-open');

  // A destination you have opened gets live-priced straight away -- even while the rest of
  // the board is still streaming in. Opening a grid IS the signal to favour it, and the
  // board stream fills the OTHER grids; there is no reason to make the one you are looking
  // at wait for them. (This gate used to require the whole board to finish first, which is
  // why a long-haul search that seeds slowly never filled its open grid.)
  if (selDest && detailOpen) fillOpenDestination(selDest);

  // A keyboard user navigating the grid loses focus when the detail pane is rebuilt (every
  // streamed destination, every verify fold-back). Remember which cell had it and put it
  // back on the equivalent cell afterwards.
  const af = document.activeElement;
  const keep = af && af.matches && af.matches('td[role="button"]')
    ? { dest: af.closest('.card') && af.closest('.card').dataset.dest, r: af.dataset.r, c: af.dataset.c }
    : null;

  // The ranked list. Only rebuilt while it is actually on screen -- during a fill the
  // focus layer covers it, and rebuilding 20 cards per streamed result is wasted work
  // that competes with the click you just made.
  if (!detailOpen) {
    $('dlist').replaceChildren(...ordered.map((dest) => listRow(dest, dest === selDest)));
  }
  const detail = $('ddetail');
  if (!detailOpen) {
    // List is showing; the layer is hidden. Leave whatever is in it — it is rebuilt from
    // scratch the moment a card is opened (selectDestination -> render with detailOpen).
  } else if (selDest && selDest.cells.length) {
    const domain = scaleDomain(selDest.allowed);
    const cur = detail.querySelector('.card.is-open');
    const sameGrid = cur && cur.dataset.dest === selDest.destination
      && cur.dataset.sig === detailSig(selDest);
    if (sameGrid && matrixScrolling) {
      pendingRepaint = true;                       // flush when the scroll settles
    } else if (sameGrid) {
      refreshOpenCard(cur, selDest, domain);       // keep the scroll container
    } else {
      detail.replaceChildren(renderCard(selDest, domain));
    }
  } else if (selDest) {
    detail.replaceChildren(renderWaiting(selDest));
  } else {
    detail.replaceChildren();
  }
  const gridOnScreen = !!(detailOpen && selDest && selDest.cells.length);
  document.body.classList.toggle('has-board', ordered.length > 0);

  if (keep && keep.dest) {
    const cell = detail.querySelector(
      `.card[data-dest="${keep.dest}"] td[data-r="${keep.r}"][data-c="${keep.c}"][role="button"]`
    );
    if (cell) { cell.tabIndex = 0; cell.focus({ preventScroll: true }); ensureVisible(cell); }
  }

  state.lastOrdered = ordered;
  // The table view is the selected destination's grid as text -- only build it when it is
  // the thing on screen (focus layer open AND in table mode).
  if (detailOpen && document.body.classList.contains('show-table')) {
    renderTable(selDest ? [selDest] : ordered);
  }
  if (!detailOpen) refreshRegionCounts();
  $('boardtools').hidden = state.destinations.size === 0;
  $('footnote').hidden = ordered.length === 0;
  // The colour key describes the grid in the detail pane. That pane no longer always has
  // one: previews land first, so between discovery and the fill the key would be
  // explaining a ramp with nothing on screen using it.
  $('legend').hidden = !gridOnScreen;
}

/* ============================================================== Multi view ===

   One combined departure x return grid instead of a card per destination. Every cell
   stacks the chosen destinations' prices; each destination is shaded against ITS OWN
   cheapest->dearest (`scaleDomain` per destination, exactly like a Single card), so a
   row that is dear in absolute money still shows which weeks it dips. The numbers side
   by side are the cross-destination comparison; the colour is the timing. */

const FM_PLANE =
  '<svg viewBox="12 8 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" ' +
  'd="M 35.30 8.70 C 35.90 9.62 34.69 11.74 33.32 13.42 L 29.82 17.22 L 33.17 28.47 ' +
  'Q 33.32 29.84 31.80 29.53 L 25.26 22.39 L 20.09 26.95 L 20.25 31.36 Q 20.25 32.27 ' +
  '19.03 31.66 L 15.53 28.47 L 12.34 24.97 Q 11.73 23.75 12.64 23.75 L 17.05 23.91 ' +
  'L 21.61 18.74 L 14.47 12.20 Q 14.16 10.68 15.53 10.83 L 26.78 14.18 L 30.58 10.68 ' +
  'C 32.26 9.31 34.38 8.10 35.30 8.70 Z"/></svg>';

let multiWidening = false;

function multiAxes() {
  return state.multi.axes || { departs: state.meta.depart_dates, returns: state.meta.return_dates };
}

/** The destinations in the combined grid. Until the user touches the set it tracks the
 *  three cheapest (so it fills in as the board streams). Once touched it is their list,
 *  minus any code no longer on the board -- and if that leaves nothing (a shared link
 *  whose destinations this board does not have), it reverts to tracking the top three. */
function multiDests(ordered) {
  const live = new Set(ordered.map((d) => d.destination));
  if (state.multi.touched) {
    const kept = state.multi.dests.filter((c) => live.has(c));
    if (kept.length) state.multi.dests = kept;
    else state.multi.touched = false;
  }
  if (!state.multi.touched) {
    state.multi.dests = ordered.slice(0, 3).map((d) => d.destination);
  }
  for (const c of [...state.multi.hidden]) if (!state.multi.dests.includes(c)) state.multi.hidden.delete(c);
  return state.multi.dests;
}

/* The combined grid is ~1000 elements to build; a streaming search fires render() many
   times a second, so coalesce the rebuilds -- a burst of stream events within one window
   collapses to a single build, and it flushes as soon as the stream pauses. setTimeout,
   not rAF: rAF is throttled to zero in a backgrounded / occluded tab and the grid would
   never appear. */
let multiTimer = 0;
function scheduleMulti() {
  clearTimeout(multiTimer);
  multiTimer = setTimeout(() => { if (state.multi.on) renderMulti(state.lastOrdered || []); }, 50);
}

function renderMulti(ordered) {
  const dests = multiDests(ordered);
  const byCode = new Map(ordered.map((d) => [d.destination, d]));
  const shown = dests.filter((c) => !state.multi.hidden.has(c)).map((c) => byCode.get(c)).filter(Boolean);

  renderMultiChips(ordered, dests, shown.length);

  const grid = $('multigrid');
  if (!shown.length || !state.meta) { grid.replaceChildren(); return; }

  const domains = new Map(shown.map((d) => [d.destination, scaleDomain(d.allowed)]));
  const maps = new Map(shown.map((d) => [d.destination, new Map(d.cells.map((c) => [c.depart + '|' + c.ret, c]))]));
  const { departs, returns } = multiAxes();
  const nightsSpan = state.meta.nights_span || null;

  let html = '<thead><tr><th class="corner" title="rows are return dates, columns are departure dates">ret ↓ dep →</th>';
  for (let c = 0; c < departs.length; c += 1) {
    const d = departs[c];
    html += `<th class="col${isWeekend(d) ? ' weekend' : ''}" scope="col">${weekday(d)}<span class="ax-date">${shortDate(d)}</span></th>`;
  }
  html += '</tr></thead><tbody>';

  for (let r = 0; r < returns.length; r += 1) {
    const ret = returns[r];
    html += `<tr><th class="row${isWeekend(ret) ? ' weekend' : ''}" scope="row">${weekday(ret)}<span class="ax-date">${shortDate(ret)}</span></th>`;
    for (let c = 0; c < departs.length; c += 1) {
      const dep = departs[c];
      if (ret < dep) { html += '<td class="void"></td>'; continue; }
      const nights = Math.round((new Date(ret) - new Date(dep)) / 86400000);
      let cheapCode = null, cheapVal = Infinity;
      for (const d of shown) {
        const cell = maps.get(d.destination).get(dep + '|' + ret);
        const v = cell ? cellValue(cell) : null;
        if (v != null && v < cheapVal) { cheapVal = v; cheapCode = d.destination; }
      }
      let subs = '';
      for (const d of shown) {
        const code = d.destination;
        const cell = maps.get(code).get(dep + '|' + ret);
        const loading = state.pendingCells.has(cellKey(code, dep, ret)) ? ' loading' : '';
        const attrs = ` data-dest="${code}" data-dep="${dep}" data-ret="${ret}" data-nights="${nights}" role="button" tabindex="-1"`;
        if (!cell) {
          const outside = nightsSpan && !nightsSpan.includes(nights);
          subs += `<span class="msub ${outside ? 'mnotasked' : 'mnodata'}${loading}"${attrs}><span class="mc">${code}</span><span class="mp">–</span></span>`;
          continue;
        }
        const value = cellValue(cell);
        const idx = rampIndex(value, domains.get(code));
        const cls = ['msub', idx === null ? 'unscaled' : 'q' + idx];
        if (!(cellAllowed(cell) || cell.verified)) cls.push('mexcluded');
        if (cell.verified) cls.push('mverified');
        if (loading) cls.push('loading');
        if (d.shownBest && cell.depart === d.shownBest.depart && cell.ret === d.shownBest.ret) cls.push('mbest');
        else if (code === cheapCode && shown.length > 1) cls.push('mwin');
        const wedge = cell.transfers > 0 ? `<span class="stopdot${cell.transfers > 1 ? ' many' : ''}"></span>` : '';
        const stale = cell.stale ? '<span class="staledot"></span>' : '';
        subs += `<span class="${cls.join(' ')}"${attrs}><span class="mc">${code}</span><span class="mp">${fmtCell(value)}</span>${wedge}${stale}</span>`;
      }
      html += `<td class="mcell"><span class="mstack">${subs}</span></td>`;
    }
    html += '</tr>';
  }
  // Rebuilding innerHTML drops the scroll offset, and the table width often changes with
  // it (add/remove a destination, widen), so the browser lands somewhere arbitrary. Pin
  // the wrapper's scroll across the swap.
  const wrap = $('multiwrap');
  const sx = wrap.scrollLeft, sy = wrap.scrollTop;
  grid.innerHTML = html + '</tbody>';
  wrap.scrollLeft = sx;
  wrap.scrollTop = sy;
  wireMultiGrid();
}

function wireMultiGrid() {
  const grid = $('multigrid');
  grid.onclick = (e) => {
    const sub = e.target.closest('.msub');
    if (!sub) return;
    const dest = state.destinations.get(sub.dataset.dest);
    if (!dest) return;
    const dep = sub.dataset.dep, ret = sub.dataset.ret;
    const cell = (dest.cells || []).find((x) => x.depart === dep && x.ret === ret)
      || { depart: dep, ret, nights: Number(sub.dataset.nights) || 0 };
    verifyCell(dest, cell);
  };
  const subs = [...grid.querySelectorAll('.msub')];
  let dimmedFor = null;
  const undim = () => { if (dimmedFor !== null) { subs.forEach((s) => s.classList.remove('dim')); dimmedFor = null; } };
  grid.onmousemove = (e) => {
    const sub = e.target.closest('.msub');
    if (!sub) { undim(); hideTooltip(); return; }
    const code = sub.dataset.dest;
    if (code !== dimmedFor) {
      for (const s of subs) s.classList.toggle('dim', s.dataset.dest !== code);
      dimmedFor = code;
    }
    const dest = state.destinations.get(code) || {};
    const cell = (dest.cells || []).find((x) => x.depart === sub.dataset.dep && x.ret === sub.dataset.ret);
    const when = `${weekday(sub.dataset.dep)} ${shortDate(sub.dataset.dep)} → ${weekday(sub.dataset.ret)} ${shortDate(sub.dataset.ret)}, ${sub.dataset.nights}n`;
    showTooltip(e, `<b>${dest.city || code} (${code})</b><br>${when}` +
      (cell ? `<br>${fmtCell(cellValue(cell))}${cell.transfers > 0 ? ' · ' + fmtStops(cell.transfers) : ' · nonstop'}` : '<br>tap to price live'));
  };
  grid.onmouseleave = () => { undim(); hideTooltip(); };
}

function renderMultiChips(ordered, dests, shownCount) {
  const host = $('multichips');
  const chip = (code) => {
    const d = state.destinations.get(code) || {};
    const hid = state.multi.hidden.has(code);
    return `<span class="mchip${hid ? ' hid' : ''}">` +
      `<button class="mchip-loc" data-c="${code}" title="Jump to ${d.city || code}'s cheapest fare"${hid ? ' disabled' : ''}>${FM_PLANE}</button>` +
      `<button class="mchip-vis" data-c="${code}" aria-pressed="${!hid}" title="${hid ? 'Show' : 'Hide'} ${d.city || code} on the grid">` +
      `${d.city || code} <span class="mchip-code">${code}</span></button>` +
      `<button class="mchip-x" data-c="${code}" aria-label="Remove ${d.city || code}">×</button></span>`;
  };
  const canWidenMulti = (() => {
    const ax = multiAxes();
    if (!ax.departs.length || !ax.returns.length) return false;
    const span = Math.round((new Date(ax.returns[ax.returns.length - 1]) - new Date(ax.departs[0])) / 86400000);
    return span + 2 * WIDEN_STEP_DAYS <= MAX_PERIOD_DAYS;
  })();
  const pool = ordered.filter((d) => !dests.includes(d.destination));
  host.innerHTML =
    dests.map(chip).join('') +
    (dests.length < MULTI_CAP && pool.length
      ? `<span class="mchip-add-wrap"><button class="mchip-add" id="mchipadd">+ add</button>` +
        `<span class="mchip-pool" id="mchippool" hidden>` +
        pool.slice(0, 24).map((d) => `<button data-c="${d.destination}">${d.city || d.destination} <span class="mchip-code">${d.destination}</span></button>`).join('') +
        `</span></span>`
      : '') +
    `<span class="mchip-spacer"></span>` +
    (canWidenMulti || multiWidening
      ? `<button class="mchip-widen" id="mchipwiden"${multiWidening ? ' disabled' : ''}>${multiWidening ? '…' : '± ' + WIDEN_STEP_DAYS + 'd'}</button>`
      : '') +
    `<span class="mdensity" role="group" aria-label="Cell density">` +
    `<button data-d="stack"${multiDensity() === 'stack' ? ' aria-pressed="true"' : ''}>Stacked</button>` +
    `<button data-d="strip"${multiDensity() === 'strip' ? ' aria-pressed="true"' : ''}>Strip</button></span>`;

  host.querySelectorAll('.mchip-x').forEach((b) => b.onclick = () => {
    state.multi.touched = true;
    state.multi.dests = state.multi.dests.filter((c) => c !== b.dataset.c);
    state.multi.hidden.delete(b.dataset.c);
    boardToUrl(); render();
  });
  host.querySelectorAll('.mchip-vis').forEach((b) => b.onclick = () => {
    const c = b.dataset.c;
    state.multi.touched = true;
    if (state.multi.hidden.has(c)) state.multi.hidden.delete(c);
    else if (shownCount > 1) state.multi.hidden.add(c);
    render();
  });
  host.querySelectorAll('.mchip-loc:not([disabled])').forEach((b) => b.onclick = () => jumpToMultiCheapest(b.dataset.c));
  const add = $('mchipadd');
  if (add) {
    add.onclick = () => $('mchippool').hidden = !$('mchippool').hidden;
    $('mchippool').querySelectorAll('button').forEach((b) => b.onclick = () => {
      state.multi.touched = true;
      if (state.multi.dests.length < MULTI_CAP) state.multi.dests.push(b.dataset.c);
      boardToUrl(); render();
    });
  }
  if ($('mchipwiden')) $('mchipwiden').onclick = multiWiden;
  host.querySelectorAll('.mdensity button').forEach((b) => b.onclick = () => {
    state.multi.density = b.dataset.d;
    applyMultiDensity();
    render();
  });
  host.querySelector('.mchip-spacer').after(nightsStepper('multi'));
}

function jumpToMultiCheapest(code) {
  const dest = state.destinations.get(code);
  if (!dest || !dest.shownBest) return;
  const b = dest.shownBest;
  const el = $('multigrid').querySelector(`.msub[data-dest="${code}"][data-dep="${b.depart}"][data-ret="${b.ret}"]`);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
  el.classList.remove('mflash');
  void el.offsetWidth;
  el.classList.add('mflash');
}

/** Widen the whole combined window: one /api/extend for every destination in the grid,
 *  mirroring widenDestination but with a shared axes override. */
function multiWiden() {
  if (multiWidening || !state.meta) return;
  const ax = multiAxes();
  const start = addDays(ax.departs[0], -WIDEN_STEP_DAYS);
  const end = addDays(ax.returns[ax.returns.length - 1], WIDEN_STEP_DAYS);
  multiWidening = true;
  render();
  fetch('/api/extend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: state.meta.origin, depart_date: start, return_date: end,
      destinations: [...state.multi.dests],
      nights_min: state.constraints.min, nights_max: state.constraints.max,
      adults: state.meta.adults, children: state.meta.children,
      currency: state.meta.currency, nonstop_only: state.meta.nonstop_only,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (!data.extend_id) throw new Error('extend failed');
      const source = new EventSource(`/api/extend/${data.extend_id}/stream`);
      source.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'axes') {
          state.multi.axes = { departs: msg.depart_dates, returns: msg.return_dates };
          render();
        } else if (msg.type === 'destination') {
          state.destinations.set(msg.destination, msg);
          recomputeBest(msg.destination);
          render();
        }
      };
      const finish = () => { source.close(); multiWidening = false; render(); };
      source.addEventListener('end', finish);
      source.onerror = finish;
    })
    .catch(() => { multiWidening = false; render(); });
}

/* Density: Strip on a desktop (packs the window), Stacked on a phone (one price per line
   suits a narrow column). A manual pick sticks. */
const multiPhone = window.matchMedia('(max-width: 720px)');
function multiDensity() {
  return state.multi.density || (multiPhone.matches ? 'stack' : 'strip');
}
function applyMultiDensity() {
  document.body.classList.toggle('multi-stack', multiDensity() === 'stack');
  document.body.classList.toggle('multi-strip', multiDensity() === 'strip');
}
multiPhone.addEventListener('change', () => { if (!state.multi.density) { applyMultiDensity(); if (state.multi.on) render(); } });

function setView(multi) {
  state.multi.on = multi;
  $('viewsingle').setAttribute('aria-pressed', String(!multi));
  $('viewmulti').setAttribute('aria-pressed', String(multi));
  // Close the focus layer without history.back() -- that would land on a pre-Multi URL
  // entry and boardToUrl below would write to the wrong one. A stale overlay entry just
  // costs one dead Back press.
  if (multi) {
    document.body.classList.remove('detail-open');
    if (document.body.classList.contains('show-table')) setTableView(false);
    $('panel').classList.remove('open');
  }
  applyMultiDensity();
  render();        // seeds state.multi.dests when switching on
  boardToUrl();
}
$('viewsingle').addEventListener('click', () => setView(false));
$('viewmulti').addEventListener('click', () => setView(true));

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
    : isPreview ? `Finding dates<span class="ellipsis" aria-hidden="true">${dots()}</span>`
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
    pushOverlay('detail');
    render();
  });
  return b;
}

/* The detail pane for a destination whose grid has not arrived yet.
 *
 * This state only exists because the board previews every destination after one discovery
 * call, so on a cold board a card can sit here for a while. It must carry the same head
 * and the same "‹ Back" control as a filled card: on a phone the pane is a fixed full-screen
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
  back.textContent = '‹ All destinations';
  back.title = 'Back to the destination list';
  back.setAttribute('aria-label', 'Back to the destination list');
  back.onclick = () => leaveOverlay();
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
  const stem = price != null
    ? `Cheapest so far ${fmtMoney(price, dest.currency || state.meta.currency)}. Finding the dates`
    : 'Finding this destination’s dates';
  // The trailing dots cycle (the tickDots ticker); aria-hidden so a screen reader just
  // hears the stem.
  wait.append(stem, Object.assign(document.createElement('span'),
    { className: 'ellipsis', ariaHidden: 'true', textContent: dots() }));
  card.appendChild(wait);
  return card;
}

/* Signature of the grid's SHAPE, not its contents: the axes. Two renders with the same
   signature can reuse the same scroll container and just repaint the cells; a different
   one (a widen) has to rebuild. */
function detailSig(dest) {
  const ax = axesFor(dest);
  return ax.departs.join(',') + '|' + ax.returns.join(',');
}

function renderCard(dest, domain) {
  const card = document.createElement('section');
  card.className = 'card is-open';
  card.dataset.dest = dest.destination;
  card.dataset.sig = detailSig(dest);
  if (!animatedDests.has(dest.destination)) {
    card.classList.add('is-new');
    animatedDests.add(dest.destination);
  }
  card.appendChild(buildCardHead(dest, domain, card));
  return finishCard(card, dest, buildMatrix(dest, domain));
}

/* Repaint the OPEN card without touching its scroll container. A stream update (auto-verify,
   the open-destination fill) fires render() several times a second; rebuilding the whole
   card each time threw away the .matrix-wrap the user was scrolling, so the grid kept
   snapping back — badly on a phone mid-fling. Here the wrap element (and its scroll
   position and scroll listener) survive: only the head and the table inside it are rebuilt,
   and the scroll offset is re-asserted synchronously so there is no visible jump. */
function refreshOpenCard(card, dest, domain) {
  const wrap = card.querySelector('.matrix-wrap');
  if (!wrap) return renderCard(dest, domain);
  const sx = wrap.scrollLeft;
  const sy = wrap.scrollTop;
  card.dataset.sig = detailSig(dest);
  card.replaceChild(buildCardHead(dest, domain, card), card.querySelector('.card-head'));
  wrap.replaceChildren(buildMatrix(dest, domain));
  wrap.scrollLeft = sx;
  wrap.scrollTop = sy;
  return card;
}

function buildCardHead(dest, domain, card) {
  const meta = state.meta;
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

  /* The leading control is a "back" affordance — it only matters on a phone, where the grid
     covers the list; on desktop the list stays beside it and CSS hides the button. */
  const back = document.createElement('button');
  back.className = 'fillbtn detail-back';
  back.type = 'button';
  back.textContent = '‹ All destinations';
  back.title = 'Back to the destination list';
  back.setAttribute('aria-label', 'Back to the destination list');
  back.onclick = () => leaveOverlay();
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
  // The little plane from the FlightMatrix mark — "take me to the cheapest fare".
  locate.innerHTML =
    '<svg viewBox="12 8 24 24" aria-hidden="true" focusable="false">' +
    '<path fill="currentColor" d="M 35.30 8.70 C 35.90 9.62 34.69 11.74 33.32 13.42 ' +
    'L 29.82 17.22 L 33.17 28.47 Q 33.32 29.84 31.80 29.53 L 25.26 22.39 L 20.09 26.95 ' +
    'L 20.25 31.36 Q 20.25 32.27 19.03 31.66 L 15.53 28.47 L 12.34 24.97 Q 11.73 23.75 ' +
    '12.64 23.75 L 17.05 23.91 L 21.61 18.74 L 14.47 12.20 Q 14.16 10.68 15.53 10.83 ' +
    'L 26.78 14.18 L 30.58 10.68 C 32.26 9.31 34.38 8.10 35.30 8.70 Z"/></svg>';
  locate.title = 'Jump to this destination’s cheapest fare';
  locate.setAttribute('aria-label', `Jump to ${dest.city}'s cheapest fare`);
  locate.onclick = () => locateBest(card, dest);
  head.appendChild(locate);

  /* Phone only (CSS hides it on desktop, where the toolbar carries the toggle): read this
     destination as a sortable table instead of the grid. It lives in the open-destination
     head on purpose — on a phone the toggle should only change how the OPEN destination is
     drawn, never reach back and open something from the list. The way back is the table
     layer's own "‹ Board". */
  const astable = document.createElement('button');
  astable.type = 'button';
  astable.className = 'fillbtn detail-astable';
  astable.textContent = 'Table';
  astable.title = 'Show this destination as a sortable table';
  astable.setAttribute('aria-label', 'Show this destination as a sortable table');
  astable.onclick = () => setTableView(true);
  head.appendChild(astable);

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

  head.appendChild(nightsStepper('card'));

  return head;
}

/* The departure x return grid. Rebuilt wholesale on every repaint. Built as one innerHTML
   string with delegated listeners (not per-cell nodes + per-cell handlers): a wide window
   is a few thousand cells, and createElement + addEventListener per cell is what locked
   the tab for seconds every time a grid opened. */
function buildMatrix(dest, domain) {
  const meta = state.meta;
  const nightsSpan = meta.nights_span || null;
  const byKey = new Map(dest.cells.map((c) => [c.depart + '|' + c.ret, c]));
  const gBest = state.globalBest;
  const cBest = dest.shownBest;
  const pendPrefix = dest.destination + '|';

  const { departs: axDeparts, returns: axReturns } = axesFor(dest);

  let html = '<thead><tr><th class="corner" title="rows are return dates, columns are departure dates">ret ↓ dep →</th>';
  for (let c = 0; c < axDeparts.length; c += 1) {
    const d = axDeparts[c];
    html += `<th class="col${isWeekend(d) ? ' weekend' : ''}" scope="col" data-c="${c}">${weekday(d)}<span class="ax-date">${shortDate(d)}</span></th>`;
  }
  html += '</tr></thead><tbody>';

  for (let r = 0; r < axReturns.length; r += 1) {
    const ret = axReturns[r];
    html += `<tr><th class="row${isWeekend(ret) ? ' weekend' : ''}" scope="row" data-r="${r}">${weekday(ret)}<span class="ax-date">${shortDate(ret)}</span></th>`;
    for (let c = 0; c < axDeparts.length; c += 1) {
      const dep = axDeparts[c];
      if (ret < dep) { html += '<td class="void">–</td>'; continue; }
      const key = dep + '|' + ret;
      const loading = state.pendingCells.has(pendPrefix + key) ? ' loading' : '';
      const attrs = ` data-c="${c}" data-r="${r}" data-dep="${dep}" data-ret="${ret}" role="button" tabindex="-1"`;
      const cell = byKey.get(key);
      if (!cell) {
        const nights = Math.round((new Date(ret) - new Date(dep)) / 86400000);
        const outside = nightsSpan && !nightsSpan.includes(nights);
        html += `<td class="${outside ? 'notasked' : 'nodata'}${loading}"${attrs} data-nights="${nights}"></td>`;
        continue;
      }
      const value = cellValue(cell);
      const idx = rampIndex(value, domain);
      let cls = 'priced ' + (idx === null ? 'unscaled' : `q${idx}`);
      if (!(cellAllowed(cell) || cell.verified)) cls += ' excluded';
      if (cell.verified) cls += ' verified';
      cls += loading;
      if (cell.nights > 0 && cell.nights % 7 === 0) cls += ' week-diag';
      if (gBest && gBest.dest === dest.destination && gBest.depart === cell.depart && gBest.ret === cell.ret) cls += ' best-board';
      else if (cBest && cell.depart === cBest.depart && cell.ret === cBest.ret) cls += ' best-here';
      const sub = cell.nights > 0 ? `<span class="cellsub">${cell.nights} night${cell.nights === 1 ? '' : 's'}</span>` : '';
      const wedge = cell.transfers > 0 ? `<span class="stopdot${cell.transfers > 1 ? ' many' : ''}"></span>` : '';
      const stale = cell.stale ? '<span class="staledot"></span>' : '';
      html += `<td class="${cls}"${attrs}><span class="cellwrap"><span class="cellprice">${fmtCell(value)}</span>${sub}${wedge}${stale}</span></td>`;
    }
    html += '</tr>';
  }
  html += '</tbody>';

  const table = document.createElement('table');
  table.className = 'matrix';
  table.innerHTML = html;
  table.setAttribute('aria-label', `${dest.city} fares by date. Arrow keys to move between cells, Enter for the live price.`);

  // The live cell for a td: look it up fresh (the board fills in as you watch), fall back
  // to a synthetic cell for an empty square so it can still be priced.
  const cellFor = (td) => {
    const stored = state.destinations.get(dest.destination) || dest;
    return stored.cells.find((x) => x.depart === td.dataset.dep && x.ret === td.dataset.ret)
      || { depart: td.dataset.dep, ret: td.dataset.ret, nights: Number(td.dataset.nights) || 0 };
  };

  // --- one set of delegated listeners for the whole grid ---
  table.addEventListener('click', (e) => {
    const td = e.target.closest('td[data-c]');
    if (!td || td.classList.contains('void')) return;
    pinCross(table, Number(td.dataset.r), Number(td.dataset.c));
    verifyCell(dest, cellFor(td));
  });
  table.addEventListener('keydown', (e) => {
    const td = e.target.closest('td[data-c]');
    if (!td) return;
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      if (!td.classList.contains('void')) { pinCross(table, Number(td.dataset.r), Number(td.dataset.c)); verifyCell(dest, cellFor(td)); }
      return;
    }
    const step = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[e.key];
    if (!step) return;
    e.preventDefault();
    const nr = Number(td.dataset.r) + step[0];
    const nc = Number(td.dataset.c) + step[1];
    const next = table.querySelector(`td[data-r="${nr}"][data-c="${nc}"][role="button"]`);
    if (!next) return;
    td.tabIndex = -1;
    next.tabIndex = 0;
    next.focus({ preventScroll: true });
    ensureVisible(next);
  });
  table.addEventListener('mousemove', (e) => {
    const td = e.target.closest('td[data-c]');
    if (!td || td.classList.contains('void')) { hideTooltip(); return; }
    highlightCross(table, Number(td.dataset.r), Number(td.dataset.c), false);
    const cell = byKey.get(td.dataset.dep + '|' + td.dataset.ret);
    if (cell) showTooltip(e, tooltipFor(dest, cell));
    else if (td.classList.contains('loading')) showTooltip(e, 'Pricing this date pair live…');
    else hideTooltip();
  });
  table.addEventListener('mouseleave', () => { hideTooltip(); restorePinned(table); });

  seedGridTabstop(table);
  return table;
}

/** Update ONE cell in the open grid in place, without rebuilding the table. Used while a
 *  fill is streaming so a click or a scroll is never queued behind a full repaint. The
 *  markup must match buildMatrix's priced-cell branch. Returns false if the grid moved on. */
function patchGridCell(dest, cell) {
  if (state.selected !== dest.destination) return false;
  const td = document.querySelector(
    `#ddetail table.matrix td[data-dep="${cell.depart}"][data-ret="${cell.ret}"]`);
  if (!td) return false;
  const stored = state.destinations.get(dest.destination) || dest;
  const value = cellValue(cell);
  td.classList.remove('loading');
  if (value == null) return true;
  const idx = rampIndex(value, scaleDomain(stored.allowed));
  let cls = 'priced ' + (idx === null ? 'unscaled' : `q${idx}`);
  if (!(cellAllowed(cell) || cell.verified)) cls += ' excluded';
  if (cell.verified) cls += ' verified';
  if (cell.nights > 0 && cell.nights % 7 === 0) cls += ' week-diag';
  if (td.classList.contains('best-board')) cls += ' best-board';
  else if (td.classList.contains('best-here')) cls += ' best-here';
  td.className = cls;
  td.setAttribute('role', 'button');
  const sub = cell.nights > 0 ? `<span class="cellsub">${cell.nights} night${cell.nights === 1 ? '' : 's'}</span>` : '';
  const wedge = cell.transfers > 0 ? `<span class="stopdot${cell.transfers > 1 ? ' many' : ''}"></span>` : '';
  td.innerHTML = `<span class="cellwrap"><span class="cellprice">${fmtCell(value)}</span>${sub}${wedge}</span>`;
  return true;
}

/** Wrap the grid in its scroll viewport and restore where the user had scrolled to. */
function finishCard(card, dest, table) {
  const wrap = document.createElement('div');
  wrap.className = 'matrix-wrap';
  wrap.appendChild(table);
  // Every scroll remembers the position AND holds off the next repaint: rebuilding the
  // grid under an actively-scrolling finger is what made it snap back. When the scroll
  // settles, any repaint that came in meanwhile is flushed once.
  wrap.addEventListener('scroll', () => {
    rememberScroll(dest.destination, wrap);
    matrixScrolling = true;
    clearTimeout(matrixScrollTimer);
    matrixScrollTimer = setTimeout(() => {
      matrixScrolling = false;
      if (pendingRepaint) { pendingRepaint = false; render(); }
    }, 180);
  }, { passive: true });
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

/* One pane, two ways to read it: the colour grid or a sortable table of the same fares.
   Every entry point (the desktop toolbar button, the phone card-head button, the table's
   own "‹ Board") routes through here so the class and the toolbar button's label stay in
   step. #tabletoggle is hidden on a phone but harmless to keep updated. */
function setTableView(on) {
  document.body.classList.toggle('show-table', on);
  const tt = $('tabletoggle');
  tt.textContent = on ? 'Matrix' : 'Table';
  tt.setAttribute('aria-pressed', String(on));
  // render() is what fills #tableview (or rebuilds the grid on the way back); nothing else
  // repaints until the next fill event, so the switched-to view would come up blank.
  render();
}

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
  back.onclick = () => setTableView(false);
  return back;
}

/* --- Browser Back steps out of an overlay, it doesn't leave the board -----------------
   Opening a destination's focus layer (or the cell sheet over it) pushes a history entry,
   so the phone/desktop Back gesture pops it and collapses that one layer -- the same
   thing the "‹ All destinations" / sheet-close controls do. Without this the board is a
   single history entry, so Back left the page entirely, which read as the app breaking.
   The date fields, filters and the ranked list are all one entry (the board); only the
   two full-window overlays get their own. */
function pushOverlay(kind) {                 // 'detail' | 'panel'
  if (history.state && history.state.fmOverlay === kind) return;
  history.pushState({ fmOverlay: kind }, '');
}
function leaveOverlay() {
  // Pop the entry and let popstate do the collapse; fall back to a direct close if there
  // is no entry to pop (e.g. the layer was opened before this code ran).
  if (history.state && history.state.fmOverlay) history.back();
  else applyOverlayState('board');
}
function applyOverlayState(kind) {           // 'board' | 'detail' | 'panel'
  const wantDetail = kind === 'detail' || kind === 'panel';
  if (kind !== 'panel') $('panel').classList.remove('open');
  const hasDetail = document.body.classList.contains('detail-open');
  if (wantDetail && !hasDetail && state.selected) {
    document.body.classList.add('detail-open');
    render();
  } else if (!wantDetail && hasDetail) {
    document.body.classList.remove('detail-open');
    if (document.body.classList.contains('show-table')) setTableView(false);  // calls render()
    else render();
  }
}
window.addEventListener('popstate', (e) => {
  applyOverlayState((e.state && e.state.fmOverlay) || 'board');
});

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
      cell: (r) => r.cell.verified ? '<span class="tag live">Live</span>'
        : isAirlineFare(r.cell) ? `<span class="tag live">${AIRLINE_SOURCES[r.cell.source]}</span>`
        : '<span class="tag">Est</span>',
      cmp: (a, b) => srcRank(a.cell) - srcRank(b.cell) },
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
  const shown = rows.slice(0, 800);
  renderTable._rows = shown;   // click handler maps a <tr> back to its {dest, cell}
  const body = shown
    .map((r, i) => `<tr data-i="${i}" tabindex="0">`
      + cols.map((c) => `<td${c.num ? ' class="num"' : ''}>${c.cell(r)}</td>`).join('') + '</tr>')
    .join('');

  host.innerHTML =
    '<div class="table-bar"></div>' +
    '<div class="table-scroll">' +
    `<table><caption class="sr-only">Every priced date pair, ${rows.length} rows${rows.length > 800 ? ' (showing 800)' : ''}. Click a column heading to sort, or a row for its flight details.</caption>` +
    `<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  host.querySelector('.table-bar').appendChild(tableBack());
}

/** Open the detail panel for the row the event landed on, if any. */
function tableRowDetail(e) {
  const tr = e.target.closest('tbody tr[data-i]');
  if (!tr) return false;
  const r = (renderTable._rows || [])[Number(tr.dataset.i)];
  if (r) verifyCell(r.dest, r.cell);   // same panel a matrix cell opens
  return true;
}

$('tableview').addEventListener('click', (e) => {
  // A heading sorts; same column again flips direction.
  const th = e.target.closest('th[data-sort]');
  if (th && renderTable._list) {
    const key = th.dataset.sort;
    tableSort.dir = tableSort.key === key ? -tableSort.dir : 1;
    tableSort.key = key;
    renderTable(renderTable._list);
    return;
  }
  tableRowDetail(e);
});
$('tableview').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
    if (tableRowDetail(e)) e.preventDefault();
  }
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
      // The city the airport serves, with the code kept as a dimmed suffix so a
      // connection through an unfamiliar code is still identifiable. Falls back to the
      // bare code when the backend could not resolve a distinct city name.
      const place = (code, city) => (city
        ? `${city}<span class="iata">${code || ''}</span>`
        : (code || '?'));
      return `<div class="leg">${num}<span class="route">${place(l.from, l.from_city)} → ${place(l.to, l.to_city)}</span>` +
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

/* POST JSON with a timeout and a couple of silent retries. A transient failure -- the
   single worker on the box busy with a board fill, a phone dropping a packet -- should
   heal itself rather than dead-end the user. Resolves with the parsed body, or throws
   after the last attempt. */
async function postJSON(url, payload, { tries = 3, timeoutMs = 15000 } = {}) {
  let lastErr;
  for (let i = 0; i < tries; i++) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: ctl.signal,
      });
      clearTimeout(timer);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      clearTimeout(timer);
      lastErr = err;
      if (i < tries - 1) await new Promise((r) => setTimeout(r, 600 * (i + 1)));
    }
  }
  throw lastErr;
}

/** Times come from the board source, so they work at any horizon. */
function fetchTimes(dest, cell) {
  const meta = state.meta;
  return postJSON('/api/details', {
    origin: meta.origin, destination: dest.destination,
    depart_date: cell.depart, return_date: cell.ret,
    adults: meta.adults, children: meta.children,
    currency: meta.currency, nonstop_only: meta.nonstop_only,
  }).catch((e) => ({ error: String(e) }));
}

async function verifyCell(dest, cell) {
  hideTooltip();
  const meta = state.meta;
  // Pulse this cell while both lookups are out.
  const pk = cellKey(dest.destination, cell.depart, cell.ret);
  state.pendingCells.add(pk);
  const donePending = () => { state.pendingCells.delete(pk); if (state.selected === dest.destination) render(); };
  // Kick the times request off immediately and in parallel: it comes from the board source
  // and succeeds even where the Google cross-check has no data at all.
  const timesPromise = fetchTimes(dest, cell);
  let timesHtml = '';
  timesPromise.then((details) => {
    timesHtml = renderTimes(details);
    const slot = document.getElementById('paneltimes');
    if (slot) slot.innerHTML = timesHtml;
    // The times request comes from the booking source and returns a real party total for
    // this exact date pair, at any horizon -- so an empty cell you clicked can be filled
    // from it even when the Google cross-check below has no data. It is the board source's
    // own number (not a Google-verified "truth"), so it lands as a normal priced cell,
    // never with the verified border.
    if (details && details.price != null) {
      const stored = state.destinations.get(dest.destination);
      if (stored) {
        let target = stored.cells.find((c) => c.depart === cell.depart && c.ret === cell.ret);
        if (!target) {
          target = { depart: cell.depart, ret: cell.ret, nights: cell.nights || 0,
                     estimate: null, unit_price: null, currency: state.meta.currency };
          stored.cells.push(target);
        }
        if (target.total == null && !target.verified) {
          target.estimate = details.price;
          target.is_total = true;
          target.source = details.source || 'kiwi';
          if (details.airline && !target.airline) target.airline = details.airline;
          stored.best = stored.cells.reduce(
            (acc, c) => (acc === null || cellValue(c) < cellValue(acc) ? c : acc), null);
          if (state.selected === dest.destination) render();
        }
      }
    }
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
    data = await postJSON('/api/verify', {
      origin: meta.origin,
      destination: dest.destination,
      depart_date: cell.depart,
      return_date: cell.ret,
      adults: meta.adults,
      children: meta.children,
      currency: meta.currency,
      nonstop_only: meta.nonstop_only,
    });
  } catch (err) {
    // Retries are spent. Don't dead-end: fall through the "no live price" branch below,
    // which keeps the board's own number and the booking link on screen.
    console.debug('cross-check request failed after retries:', err);
    data = { error: 'unreachable', total: null, link: null };
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
        `<div class="muted">${isFirmPrice(cell) ? `total for ${who}` : 'estimated'}, from ${sourceName(cell.source)}${fareNote(cell)}</div>`
      : '';
    const links = [];
    if (cell.link) {
      links.push(`<a href="${cell.link}" target="_blank" rel="noopener">Book on ${sourceName(cell.source)}</a>`);
    }
    if (data.link) {
      links.push(`<a href="${data.link}" target="_blank" rel="noopener">Open on Google Flights</a>`);
    }
    const explain = data.error === 'unreachable'
      ? `The live check didn't respond just now${cell.estimate != null ? ` — the price above is the board${isFirmPrice(cell) ? ' total' : ' estimate'}` : ''}. The booking links below are live; tap the cell again in a moment to re-check.`
      : isAirlineFare(cell)
      ? `${AIRLINE_SOURCES[cell.source]} fares don't always show on Google Flights. The price above is ${AIRLINE_SOURCES[cell.source]}'s own fare for these exact dates (lowest fare, one carry-on, per traveller × your party); book it on the link below.`
      : cell.estimate != null
        ? `Couldn't verify this fare live. Not every route is in Google Flights. The price above is the board's ${isFirmPrice(cell) ? 'total' : 'estimate'}; the booking links below are live.`
        : `Google Flights has no fare for this exact date pair. If the booking source found one it is shown below and the cell is now filled with it; otherwise try a nearby cell.`;
    openPanel(
      `<h3>${dest.city} (${dest.destination})</h3>` +
        `<div class="muted">${weekday(cell.depart)} ${shortDate(cell.depart)} &rarr; ${weekday(cell.ret)} ${shortDate(cell.ret)}</div>` +
        boardPrice +
        `<p class="muted">${explain}</p>` +
        '<div id="paneltimes"></div>' +
      (links.length ? `<p>${links.join('<br>')}</p>` : '')
    );
    restoreTimes();
    donePending();
    return;
  }

  // `data.cached` means the live check failed and we fell back to the last stored
  // verification. Don't show the "Estimate was … (+0%)" line then: for a fallback the
  // estimate is often derived from this very number, so the delta is a circular 0.
  const delta = (!data.cached && cell.estimate) ? ((data.total - cell.estimate) / cell.estimate) * 100 : null;
  const age = data.cache_age_minutes != null ? fmtAge(data.cache_age_minutes) : null;
  const headNote = data.cached
    ? `last verified ${age || 'earlier'}${data.stale ? ' — may be out of date' : ''}`
    : `live total for ${meta.adults} adults${meta.children ? ' + ' + meta.children + ' children' : ''}`;
  openPanel(
    `<h3>${dest.city} (${dest.destination})</h3>` +
      `<div class="muted">${weekday(cell.depart)} ${shortDate(cell.depart)} &rarr; ${weekday(cell.ret)} ${shortDate(cell.ret)}, ${cell.nights || ''} nights</div>` +
      `<div class="big">${fmtMoney(data.total, cur)}</div>` +
      `<div class="muted">${headNote}</div>` +
      (data.cached ? `<p class="muted">The live re-check didn't respond; showing the last one. Tap the cell again to retry.</p>` : '') +
      '<dl>' +
      (delta != null ? `<dt>Estimate was</dt><dd>${estimate} (${delta >= 0 ? '+' : ''}${delta.toFixed(0)}%)</dd>` : '') +
      (data.departs ? `<dt>Outbound departs</dt><dd>${data.departs}</dd>` : '') +
      (data.arrives ? `<dt>Outbound arrives</dt><dd>${data.arrives}</dd>` : '') +
      (data.airline ? `<dt>Airline</dt><dd>${data.airline}</dd>` : '') +
      (data.duration ? `<dt>Duration</dt><dd>${data.duration}</dd>` : '') +
      (data.stops_out != null ? `<dt>Stops</dt><dd>${fmtStops(data.stops_out)}</dd>` : '') +
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
    target.stale = !!data.stale;   // a fallback to an aged verification stays marked aged
    target.airline = data.airline;
    if (data.stops_out != null) target.transfers = data.stops_out;
    // `best` arrives as its own object, not a reference into `cells`, so recompute it
    // from scratch. A verified price is often WORSE than the estimate it replaces, so
    // this must be able to move `best` up as well as down.
    stored.best = stored.cells.reduce(
      (acc, c) => (acc === null || cellValue(c) < cellValue(acc) ? c : acc),
      null
    );
  }
  donePending();   // also repaints, folding in the verified total
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
// The grid scrolls and only the nights-band diagonal is populated, so a wide window is
// cheap to show; this bound is really about provider calls on a re-fetch. Raised from 60
// so the default ~3-month window can still be widened a few times.
const MAX_PERIOD_DAYS = 120;
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

/* While the open grid is being scrolled, defer repaints (see finishCard's scroll handler
   and render's use of refreshOpenCard). Cleared 180ms after the last scroll event, which
   also flushes any repaint that was held back. */
let matrixScrolling = false;
let matrixScrollTimer = null;
let pendingRepaint = false;

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
// When you open a destination the board favours THAT grid: it live-prices its EMPTY cells
// first (so the striped no-data gaps fill in and the grid ends up complete), then the
// cheapest estimate cells for verification. Runs independent of the board-wide
// "Cross-check live" toggle -- opening a grid is the signal to fill it. The cap is a
// rate-limit sanity bound, not a design choice; a normal band sits well under it.
const OPEN_FILL_CAP = 160;
const openFilled = new Set();     // destinations whose band fill has been started this search
let openFillSource = null;
let openFillId = null;
let openFillFor = null;           // destination the active/last fill belongs to

/** Every valid (departure, return) pair in this destination's rendered grid that is not
 *  already a live price. The user wants a complete grid, so this covers the WHOLE window,
 *  not just the asked trip-length band. Order: empty cells first (fill the gaps), then
 *  cheapest estimates for verification; within that, in-range trip lengths before the
 *  out-of-range ones so the fares that matter land first. */
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
      const c = byKey.get(depart + '|' + ret);
      if (c && c.verified) continue;
      const value = c ? cellValue(c) : null;
      const inRange = !span || span.has(nights);
      out.push({
        depart, ret,
        // sort key: [empty-first] [in-range-first] [cheapest-first]
        rank: (value == null ? 0 : 2) + (inRange ? 0 : 1),
        sort: value == null ? 0 : value,
      });
    }
  }
  out.sort((a, b) => a.rank - b.rank || a.sort - b.sort);
  // Empties and in-range cells come first (the rank), so a big window still fills the part
  // that matters; the cap is a rate-limit bound on the long tail of out-of-range squares.
  const cap = out.length > 1400 ? 120 : OPEN_FILL_CAP;
  return out.slice(0, cap).map((c) => ({
    destination: dest.destination, depart_date: c.depart, return_date: c.ret,
  }));
}

function stopOpenFill() {
  if (openFillId) fetch(`/api/fill/${openFillId}/cancel`, { method: 'POST' }).catch(() => {});
  if (openFillSource) openFillSource.close();
  openFillSource = null;
  openFillId = null;
  // Drop any still-blinking cells from the fill we just abandoned.
  if (openFillFor) {
    const pfx = openFillFor + '|';
    for (const k of state.pendingCells) if (k.startsWith(pfx)) state.pendingCells.delete(k);
  }
}

function fillOpenDestination(dest) {
  // Runs whenever a grid is open (a deliberate focus action) -- not gated on the
  // board-wide "Cross-check live" toggle. Opening a destination IS the signal to favour it.
  if (!dest || !state.meta) return;
  const code = dest.destination;
  if (openFillFor === code) return;      // already handled this selection
  stopOpenFill();
  stopAutoVerify();     // the open grid gets priority over the board-wide cross-check
  openFillFor = code;
  if (openFilled.has(code)) return;      // already done once this search
  openFilled.add(code);

  const cells = bandCells(dest);
  if (!cells.length) return;

  // Mark every cell we are about to price as loading, so the grid pulses them while the
  // fetch is out. Cleared per cell as each result lands, and wholesale when the run ends.
  for (const c of cells) state.pendingCells.add(cellKey(code, c.depart_date, c.return_date));
  if (state.selected === code) render();

  const meta = state.meta;
  const city = dest.city;
  const clearPending = () => {
    for (const c of cells) state.pendingCells.delete(cellKey(code, c.depart_date, c.return_date));
  };
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
      if (!data.fill_id || openFillFor !== code) { clearPending(); if (state.selected === code) render(); return; }
      openFillId = data.fill_id;
      const source = new EventSource(`/api/fill/${data.fill_id}/stream`);
      openFillSource = source;
      let lastFull = 0;
      source.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'fill_cell') {
          const d = state.destinations.get(msg.destination);
          let patched = false;
          if (msg.ok && d) {
            applyCell(d, msg);
            recomputeBest(msg.destination);
            // Patch just this cell in place -- no full repaint, so a click or a locate
            // during the fill is handled immediately.
            const c = d.cells.find((x) => x.depart === msg.depart_date && x.ret === msg.return_date);
            if (c) patched = patchGridCell(d, c);
          } else {
            const td = document.querySelector(
              `#ddetail table.matrix td[data-dep="${msg.depart_date}"][data-ret="${msg.return_date}"]`);
            if (td) td.classList.remove('loading');
          }
          state.pendingCells.delete(cellKey(msg.destination, msg.depart_date, msg.return_date));
          $('growing').hidden = false;
          $('growing').textContent =
            `pricing ${city} on Google Flights… ${msg.progress}/${msg.total_cells}`;
          // A full repaint only every couple of seconds, to re-rank the colour scale as
          // fares land; the per-cell patch above keeps the grid current between them.
          const now = performance.now();
          if (state.selected === code && (!patched || now - lastFull > 2500)) {
            lastFull = now; render();
          }
        } else if (msg.type === 'fill_done') {
          $('growing').hidden = true;
          if (state.selected === code) render();
        }
      };
      const finish = () => {
        source.close();
        if (openFillSource === source) stopOpenFill();
        clearPending();
        $('growing').hidden = true;
        if (state.selected === code) render();
      };
      source.addEventListener('end', finish);
      source.onerror = finish;
    })
    .catch(() => { openFillSource = null; openFillId = null; clearPending(); if (state.selected === code) render(); });
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
  pushOverlay('panel');   // so Back closes the sheet before the focus layer
}

$('panelclose').addEventListener('click', () => leaveOverlay());

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
  state.nightsBand = null;   // the new board is priced for its own nights range
  $('dlist').replaceChildren();
  $('ddetail').replaceChildren();
  document.body.classList.remove('detail-open', 'has-board', 'show-table');
  $('tabletoggle').textContent = 'Table';
  $('tabletoggle').setAttribute('aria-pressed', 'false');
  $('tableview').replaceChildren();
  // A new board changes the window and (usually) the destinations: drop the widen and the
  // hidden set. `dests` / `touched` are left alone -- multiDests() prunes any code that is
  // not on the new board, so a user's own picks that still exist carry over and an
  // otherwise-fresh board falls back to its three cheapest.
  state.multi.hidden.clear();
  state.multi.axes = null;
  $('multigrid').replaceChildren();
  $('errors').textContent = '';
  // Until the first destination lands the board area would be blank; hold a placeholder
  // there so the wait reads as work in progress, not a broken page.
  $('empty').hidden = false;
  $('empty').classList.add('is-searching');
  $('empty').replaceChildren('Finding cheap destinations',
    Object.assign(document.createElement('span'),
      { className: 'ellipsis', ariaHidden: 'true', textContent: dots() }));
  $('boardtools').hidden = true;   // no results yet
  // Orientation is a first-run thing; once you've searched, you know.
  $('firstrun').hidden = true;
  stopAutoVerify();             // a new search invalidates any in-flight cross-check
  stopOpenFill();
  openFilled.clear();
  openFillFor = null;
  $('growing').hidden = true;   // clear any stale rate-limit / widening notice
  $('note').hidden = true;
  scrollOffsets.clear();
  matrixScrolling = false;
  pendingRepaint = false;
  clearTimeout(matrixScrollTimer);
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
    destination_codes: [...state.places],
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
      $('currencyopt').value = msg.currency;
      syncCurrencyMarks();
      syncDateMode();
      $('progress').textContent = `Searching from ${msg.origin_city} (${msg.origin})…`;
    } else if (msg.type === 'region_seeding') {
      // The region filter left the board thin, so the backend is probing a shortlist of
      // that region's airports for live fares. Can take a few seconds — say so.
      $('progress').textContent = 'Checking which airports fly from here…';
    } else if (msg.type === 'region_seeded') {
      if (msg.added) $('progress').textContent = `Found ${msg.matched} destinations in this region…`;
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
      // A destination the user named explicitly must not just vanish -- say why.
      if (msg.picked) {
        $('errors').textContent =
          `No ${$('origin').value.toUpperCase()} → ${msg.city} flights are on sale for these dates yet. ` +
          `Airlines load schedules for smaller routes 3–6 months ahead; try a nearer date or a larger nearby airport.`;
      }
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
/* Per person lives in two places -- the board toolbar (after a search) and the Options
   panel (available before one). Whichever the user touches, mirror it to the other and
   re-label the board. */
function applyPerPerson(on) {
  state.perPerson = on;
  $('perperson').checked = on;
  $('perpersonopt').checked = on;
  if (state.meta) render();
}
$('perperson').addEventListener('change', (e) => applyPerPerson(e.target.checked));
$('perpersonopt').addEventListener('change', (e) => applyPerPerson(e.target.checked));
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
  'origin', 'depart', 'ret', 'adults', 'children', 'dests', 'maxprice',
  'nonstop', 'dephfrom', 'dephto', 'rethfrom', 'rethto',
];
// 'currency' is NOT a search input (a loaded board just re-labels via FX). 'nmin'/'nmax'
// are NOT either any more: the on-grid steppers apply a nights change live -- narrowing
// re-filters instantly, widening auto-fetches the new band. A fresh search still reads
// the fields directly.

function searchSignature() {
  const parts = SEARCH_INPUTS.map((id) => {
    const el = $(id);
    return el.type === 'checkbox' ? String(el.checked) : el.value;
  });
  parts.push('r:' + [...state.regions].sort().join(','));
  parts.push('p:' + [...state.places].sort().join(','));
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

for (const id of SEARCH_INPUTS) {
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
  $('regionclear').addEventListener('click', () => {
    state.regions.clear(); state.places.clear(); state.placeName = {}; afterRegionChange();
  });
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
  const name = document.createElement('span');
  name.className = 'rname';
  name.textContent = label;
  lab.append(cb, name, spanCount());
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
  const label = document.createElement('span');
  label.className = 'rname';
  label.textContent = name;
  lab.append(cb, label, spanCount(code));
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
  $('regionclear').hidden = state.regions.size === 0 && state.places.size === 0;
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
  input.addEventListener('input', (e) => {
    openDestPop();
    const q = e.target.value.trim();
    filterRegionTree(q.toLowerCase());
    queryPlaces(q);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeDestPop(); input.blur(); }
    if (e.key === 'Enter') {
      const first = $('destresults').querySelector('.dest-result');
      if (first) { e.preventDefault(); first.click(); }
    }
    // Backspace on an empty input removes the last tag (place chips first, then regions).
    if (e.key === 'Backspace' && input.value === '') {
      if (state.places.size) {
        const last = [...state.places].pop();
        state.places.delete(last); delete state.placeName[last]; afterPlacesChange();
      } else if (state.regions.size) {
        const last = [...destTagList()].pop();
        if (last) { for (const c of last.codes) state.regions.delete(c); afterRegionChange(); }
      }
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
  clearPlaceResults();
}

/* -------------------------------------------------- Typeahead: country / city / airport */

let placeQueryTimer = null;
let placeQuerySeq = 0;

function clearPlaceResults() {
  const box = $('destresults');
  box.replaceChildren();
  box.hidden = true;
}

function queryPlaces(q) {
  clearTimeout(placeQueryTimer);
  if (q.length < 2) { clearPlaceResults(); return; }
  const seq = ++placeQuerySeq;
  placeQueryTimer = setTimeout(() => {
    fetch(`/api/places?q=${encodeURIComponent(q)}`)
      .then((r) => r.json())
      .then((data) => { if (seq === placeQuerySeq) renderPlaceResults(data.results || []); })
      .catch(() => {});
  }, 140);
}

function renderPlaceResults(results) {
  const box = $('destresults');
  const rows = results
    .filter((r) => !(r.kind === 'country' ? state.regions.has(r.code) : state.places.has(r.code)))
    .map((r) => {
      const li = document.createElement('li');
      li.className = 'dest-result';
      li.setAttribute('role', 'option');
      li.dataset.kind = r.kind;
      li.dataset.code = r.code;
      li.innerHTML =
        `<span class="dr-kind">${r.kind === 'country' ? 'Country' : r.kind === 'city' ? 'City' : 'Airport'}</span>` +
        `<span class="dr-label">${r.label}${r.kind !== 'country' ? ` <span class="dr-code">${r.code}</span>` : ''}</span>` +
        (r.sub ? `<span class="dr-sub">${r.sub}</span>` : '');
      li.addEventListener('mousedown', (e) => e.preventDefault());   // keep input focus
      li.addEventListener('click', () => pickPlace(r));
      return li;
    });
  box.replaceChildren(...rows);
  box.hidden = rows.length === 0;
}

function pickPlace(r) {
  if (r.kind === 'country') {
    state.regions.add(r.code);
    afterRegionChange();
  } else {
    state.places.add(r.code);
    state.placeName[r.code] = r.label;
    afterPlacesChange();
  }
  const input = $('regionsearch');
  input.value = '';
  filterRegionTree('');
  clearPlaceResults();
  input.focus();
}

function afterPlacesChange() {
  renderDestTags();
  markSearchStale();
}

/* -------------------------------------------------- Origin ("From") typeahead */
/* Single value, no chips. Type a city or airport, pick one, `#origin` holds the IATA
   code the search needs; a bare 2-4 letter code still works typed straight in. */
let originQueryTimer = null;
let originQuerySeq = 0;
let originLastCode = ($('origin').value || '').trim().toUpperCase();

function closeOriginResults() {
  $('originresults').replaceChildren();
  $('originresults').hidden = true;
  $('origin').setAttribute('aria-expanded', 'false');
}

function wireOriginCombo() {
  const input = $('origin');
  input.addEventListener('input', () => {
    const q = input.value.trim();
    clearTimeout(originQueryTimer);
    if (q.length < 2) { closeOriginResults(); return; }
    const seq = ++originQuerySeq;
    originQueryTimer = setTimeout(() => {
      fetch(`/api/places?q=${encodeURIComponent(q)}`)
        .then((r) => r.json())
        .then((data) => {
          if (seq !== originQuerySeq) return;
          // Countries are allowed too -- picking one resolves to its busiest hub. Drop only
          // a country row we can't resolve to an airport.
          const results = (data.results || []).filter((r) => r.kind !== 'country' || r.hub);
          renderOriginResults(results);
        })
        .catch(() => {});
    }, 140);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeOriginResults(); }
    if (e.key === 'Enter') {
      const first = $('originresults').querySelector('.dest-result');
      if (first) { e.preventDefault(); pickOrigin(first.dataset.code, first.dataset.label); }
    }
  });
  input.addEventListener('blur', () => {
    // Snap back to the last confirmed code if the field was left mid-search.
    setTimeout(() => {
      if (!/^[A-Za-z]{2,4}$/.test(input.value.trim())) {
        input.value = originLastCode;
      } else {
        input.value = input.value.trim().toUpperCase();
        originLastCode = input.value;
      }
      closeOriginResults();
      markSearchStale();
    }, 150);
  });
}

function renderOriginResults(results) {
  const box = $('originresults');
  box.replaceChildren(...results.map((r) => {
    const isCountry = r.kind === 'country';
    const code = isCountry ? r.hub : r.code;               // depart from the country's hub
    const label = r.label;
    const li = document.createElement('li');
    li.className = 'dest-result';
    li.setAttribute('role', 'option');
    li.dataset.code = code;
    li.dataset.label = label;
    li.innerHTML =
      `<span class="dr-kind">${isCountry ? 'Country' : 'Airport'}</span>` +
      `<span class="dr-label">${r.label} <span class="dr-code">${code}</span></span>` +
      (r.sub ? `<span class="dr-sub">${r.sub}</span>` : '');
    li.addEventListener('mousedown', (e) => e.preventDefault());
    li.addEventListener('click', () => pickOrigin(code, label));
    return li;
  }));
  box.hidden = results.length === 0;
  $('origin').setAttribute('aria-expanded', String(!box.hidden));
}

function pickOrigin(code, label) {
  const input = $('origin');
  input.value = code;
  originLastCode = code;
  input.title = label ? `${label} (${code})` : code;
  closeOriginResults();
  input.dispatchEvent(new Event('change', { bubbles: true }));   // change, not input: don't re-open
  markSearchStale();
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
  const mk = (label, onRemove, isPlace) => {
    const el = document.createElement('span');
    el.className = 'dest-tag' + (isPlace ? ' is-place' : '');
    el.append(label);
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'dest-tag-x';
    x.setAttribute('aria-label', `Remove ${label}`);
    x.textContent = '×';
    x.addEventListener('click', onRemove);
    el.append(x);
    return el;
  };
  const regionTags = destTagList();
  const placeChips = [...state.places].map((code) =>
    mk(state.placeName[code] || code, () => {
      state.places.delete(code); delete state.placeName[code]; afterPlacesChange();
    }, true));
  const regionChips = regionTags.map((t) =>
    mk(t.label, () => { for (const c of t.codes) state.regions.delete(c); afterRegionChange(); }, false));
  host.replaceChildren(...placeChips, ...regionChips);
  const any = placeChips.length + regionChips.length > 0;
  $('destcombo').classList.toggle('has-tags', any);
  $('regionsearch').placeholder = any ? '' : 'Anywhere';
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
   The field labels and the first-run lede already say this, so there is no standing hint
   line -- it only ever sat above the board as redundant chrome. */
function syncDateMode() {
  $('departlabel').textContent = 'Travel from';
  $('retlabel').textContent = 'Travel until';
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
$('nmin').addEventListener('input', commitNights);
$('nmax').addEventListener('input', commitNights);

/* ---------------------------------------------------------- nights, live on the grid

   Nights min/max is mostly a view filter: `state.constraints` re-colours, re-ranks and
   re-orders the board with no refetch. The on-grid steppers (Single card head + Multi
   chips) drive it directly; only widening PAST the trip lengths already priced needs
   data, and that is fetched automatically for whatever grid is on screen. */

let nightsExtending = false;
let nightsExtendTimer = 0;

/** Current fetched trip-length band, expanded as widening fetches fill it in. */
function fetchedNights() {
  const span = state.meta && state.meta.nights_span;
  if (state.nightsBand) return state.nightsBand;
  if (span && span.length) return { lo: Math.min(...span), hi: Math.max(...span) };
  return null;
}

/** A compact `Nights  − 6 +   − 9 +` control, values read live from the hidden fields. */
function nightsStepper(where) {
  const wrap = document.createElement('span');
  wrap.className = 'nights-stepper' + (where ? ' ns-' + where : '');
  const cur = (id, d) => ($(id).value === '' ? d : Number($(id).value));
  const group = (which, val) => {
    const g = document.createElement('span');
    g.className = 'ns-group';
    const dec = document.createElement('button');
    dec.type = 'button'; dec.textContent = '−';
    dec.setAttribute('aria-label', `One fewer ${which} night`);
    dec.onclick = () => stepNights(which, -1);
    const n = document.createElement('span');
    n.className = 'ns-val'; n.textContent = String(val);
    const inc = document.createElement('button');
    inc.type = 'button'; inc.textContent = '+';
    inc.setAttribute('aria-label', `One more ${which} night`);
    inc.onclick = () => stepNights(which, 1);
    g.append(dec, n, inc);
    return g;
  };
  const lab = document.createElement('span');
  lab.className = 'ns-label'; lab.textContent = 'Nights';
  const dash = document.createElement('span');
  dash.className = 'ns-dash'; dash.textContent = '–';
  wrap.append(lab, group('min', cur('nmin', 5)), dash, group('max', cur('nmax', 9)));
  return wrap;
}

function stepNights(which, delta) {
  const el = which === 'min' ? $('nmin') : $('nmax');
  const other = which === 'min' ? $('nmax') : $('nmin');
  const otherV = other.value === '' ? null : Number(other.value);
  let v = (el.value === '' ? (which === 'min' ? 5 : 9) : Number(el.value)) + delta;
  v = Math.max(0, Math.min(60, v));
  if (which === 'min' && otherV != null) v = Math.min(v, otherV);
  if (which === 'max' && otherV != null) v = Math.max(v, otherV);
  el.value = String(v);
  commitNights();
}

/** Apply a nights change everywhere: constraints + repaint (readNights), the preset
 *  label, and -- if the band grew -- an auto-fetch for the visible grid. */
function commitNights() {
  readNights();
  syncTripPreset();
  markSearchStale();          // nights is not a search input any more, so this clears the marker
  updateNightsBand();
}

function syncTripPreset() {
  const val = `${$('nmin').value},${$('nmax').value}`;
  const sel = $('tripselect');
  const match = [...sel.options].some((o) => o.value === val);
  sel.value = match ? val : 'custom';
}

function nightsRange() {
  const b = fetchedNights();
  const lo = state.constraints.min != null ? state.constraints.min : (b ? b.lo : 5);
  const hi = state.constraints.max != null ? state.constraints.max : (b ? b.hi : 9);
  return { lo: Math.min(lo, hi), hi: Math.max(lo, hi) };
}

function updateNightsBand() {
  if (!state.meta) return;
  const want = nightsRange();
  const band = fetchedNights();
  if (!band || (want.lo >= band.lo && want.hi <= band.hi)) return;   // within the priced band

  // Widen the band so the grid treats the new lengths as in-range straight away; the
  // cells fill from the fetch below.
  state.nightsBand = { lo: Math.min(band.lo, want.lo), hi: Math.max(band.hi, want.hi) };
  state.meta.nights_span = [];
  for (let n = state.nightsBand.lo; n <= state.nightsBand.hi; n += 1) state.meta.nights_span.push(n);

  clearTimeout(nightsExtendTimer);
  nightsExtendTimer = setTimeout(nightsExtend, 350);
  render();
}

/** Re-price the visible grid over the same date window with the wider nights range.
 *  Multi: every destination on the grid, one shared axes. Single: the open card. */
function nightsExtend() {
  if (nightsExtending || !state.meta) return;
  const codes = state.multi.on
    ? [...state.multi.dests]
    : (document.body.classList.contains('detail-open') && state.selected ? [state.selected] : []);
  if (!codes.length) { openFilled.clear(); return; }   // list view: cards refill on open

  nightsExtending = true;
  render();
  fetch('/api/extend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: state.meta.origin,
      depart_date: $('depart').value, return_date: $('ret').value,   // the window is unchanged
      destinations: codes,
      nights_min: state.constraints.min, nights_max: state.constraints.max,
      adults: state.meta.adults, children: state.meta.children,
      currency: state.meta.currency, nonstop_only: state.meta.nonstop_only,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (!data.extend_id) throw new Error('extend failed');
      const source = new EventSource(`/api/extend/${data.extend_id}/stream`);
      source.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'axes') {
          const ax = { departs: msg.depart_dates, returns: msg.return_dates };
          if (state.multi.on) state.multi.axes = ax;
          else codes.forEach((c) => destAxes.set(c, ax));
          render();
        } else if (msg.type === 'destination') {
          state.destinations.set(msg.destination, msg);
          recomputeBest(msg.destination);
          render();
        }
      };
      const finish = () => { source.close(); nightsExtending = false; render(); };
      source.addEventListener('end', finish);
      source.onerror = finish;
    })
    .catch(() => { nightsExtending = false; render(); });
}

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
const CURRENCY_SYMBOL = { ils: '₪', eur: '€', usd: '$', gbp: '£' };

/** Keep the currency marks on money fields (Options -> Max total) in sync with the picker. */
function syncCurrencyMarks() {
  const sym = CURRENCY_SYMBOL[$('currency').value] || '';
  $('maxpricecur').textContent = sym;
}

/* Currency, like Per person, sits both in the board toolbar and in Options. #currency is
   the canonical control (URL, search body, board-load default all read it); #currencyopt
   mirrors it so the value -- and the Max total money mark -- can be set before a search. */
function applyCurrency(val) {
  if ($('currency').value !== val) $('currency').value = val;
  if ($('currencyopt').value !== val) $('currencyopt').value = val;
  syncCurrencyMarks();
  if (!state.meta) return;   // no board yet: this is just what the next search fetches in
  state.displayCurrency = val;
  $('panel').classList.remove('open');   // its numbers are now stale
  render();
}
$('currency').addEventListener('change', (e) => applyCurrency(e.target.value));
$('currencyopt').addEventListener('change', (e) => applyCurrency(e.target.value));
syncCurrencyMarks();

$('autoverify').addEventListener('change', (e) => {
  if (e.target.checked) startAutoVerify();
  else stopAutoVerify();
});

/* Fare heatmap: the pale tint scale ships by default; this opts in to the green-to-red
   ramp that stays distinct under red-green colour vision deficiency and in greyscale.
   Pure CSS switch (data-fareramp on <html> re-points --qN), persisted, so no re-render is
   needed -- the legend swatches follow the same tokens. */
(function initFareRamp() {
  let pref = null;
  try { pref = localStorage.getItem('flightmatrix.fareramp'); } catch (e) { /* ignore */ }
  if (pref === 'cvd') {
    document.documentElement.setAttribute('data-fareramp', 'cvd');
    $('cvdramp').checked = true;
  }
})();
$('cvdramp').addEventListener('change', (e) => {
  const on = e.target.checked;
  if (on) document.documentElement.setAttribute('data-fareramp', 'cvd');
  else document.documentElement.removeAttribute('data-fareramp');
  try {
    localStorage.setItem('flightmatrix.fareramp', on ? 'cvd' : 'pale');
  } catch (err) { /* ignore */ }
});
/* The desktop toolbar toggle; the button names the view you'd switch TO. */
$('tabletoggle').addEventListener('click', () => {
  setTableView(!document.body.classList.contains('show-table'));
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
  // the travel window; the rest is a tap away.
  const fmt = (iso) => {
    if (!iso) return '';
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  };
  const from = fmt($('depart').value);
  const to = fmt($('ret').value);
  const when = from && to ? `${from} – ${to}` : (from || to || 'anytime');
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
wireOriginCombo();

/* Advance the shared dot frame every 300ms and write it into every ellipsis on the page.
   New spans built between ticks already carry the current frame (see `dots()`); this nudges
   the mounted ones. A plain foreground interval — no guards, no reduced-motion gate — is
   the most reliable thing across phone browsers. */
setInterval(() => {
  dotFrame += 1;
  const s = DOT_FRAMES[dotFrame % DOT_FRAMES.length];
  const els = document.getElementsByClassName('ellipsis');
  for (let i = 0; i < els.length; i += 1) els[i].textContent = s;
}, 300);

/* The window is the two date fields, in the bar. Default to a ~3-month span starting
   three weeks out (close enough to be well-covered, far enough to leave planning room);
   a shared/bookmarked URL overrides this. `min` keeps the picker off past dates. */
function setDefaultDates() {
  const today = isoLocal(new Date());
  $('depart').min = today;
  $('ret').min = today;
  if (!$('depart').value) $('depart').value = isoToday(21);
  if (!$('ret').value) $('ret').value = isoToday(21 + 90);
}

/** Reflect a preset's day-of-week choice in the picker and the constraint state. */
function setDow(key, days) {
  const set = state.constraints[key];
  set.clear();
  for (const d of days) set.add(d);
  const host = $(key === 'dep' ? 'dowdep' : 'dowret');
  [...host.children].forEach((btn, i) => btn.classList.toggle('on', set.has(i)));
}

function applyTrip() {
  if ($('tripselect').value === 'custom') return;   // "Custom" is a label, not a preset
  const [lo, hi] = $('tripselect').value.split(',');
  $('nmin').value = lo;
  $('nmax').value = hi;
  // A "weekend" means leaving Wed/Thu and back Sun/Mon; the longer presets have no
  // natural shape, so they clear the day filter.
  const weekendish = $('tripselect').value === '2,3' || $('tripselect').value === '3,4';
  setDow('dep', weekendish ? [3, 4] : []);       // Wed, Thu
  setDow('ret', weekendish ? [0, 1] : []);       // Sun, Mon
}

setDefaultDates();
for (const id of ['depart', 'ret']) {
  $(id).addEventListener('change', () => { syncReturnDate(); markSearchStale(); renderEditSummary(); });
}
$('tripselect').addEventListener('change', () => {
  applyTrip();
  commitNights();   // preset -> fields -> live apply (+ fetch if it widened the band)
});

applyTrip();

// A shared/bookmarked board carries its search in the query string; it wins over the
// defaults and prefills the form.
const urlBoard = boardFromUrl(new URLSearchParams(location.search));
setDefaultDates();        // fill only what the URL left blank
syncDateMode();
syncReturnDate();
if (state.regions.size || state.places.size) renderDestTags();
syncTripPreset();
$('viewsingle').setAttribute('aria-pressed', String(!state.multi.on));
$('viewmulti').setAttribute('aria-pressed', String(state.multi.on));
applyMultiDensity();

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
    if (!urlBoard.has('currency')) {
      $('currency').value = h.defaults.currency;
      $('currencyopt').value = h.defaults.currency;
      syncCurrencyMarks();
    }
    if (!urlBoard.has('adults')) $('adults').value = h.defaults.adults;
    if (!urlBoard.has('children')) $('children').value = h.defaults.children;
    if (!urlBoard.has('places')) $('dests').value = h.defaults.max_destinations;
  })
  .catch(() => {});
