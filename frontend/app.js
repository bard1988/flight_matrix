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
  filter: '',              // destination filter, applied to the already-loaded board
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
  places: 'dests', currency: 'currency', only: 'destfilter',
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

function isoToday(offsetDays) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
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
  rows.push(`${weekday(cell.depart)} ${shortDate(cell.depart)} &rarr; ${weekday(cell.ret)} ${shortDate(cell.ret)} &middot; ${cell.nights} nights`);
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

/** Does this destination match the filter box? Matches city, IATA code or country. */
function matchesFilter(dest) {
  const q = state.filter;
  if (!q) return true;
  // Codes match exactly, names by substring - mirrors the server. Substring-matching a
  // 2-letter code against country names over-matches ("IT" is inside Lithuania).
  const code = (dest.destination || '').toLowerCase();
  const country = (dest.country || '').toLowerCase();
  if ((q.length === 2 || q.length === 3) && (q === code || q === country)) return true;
  return [dest.city, dest.country_name]
    .filter(Boolean)
    .some((field) => String(field).toLowerCase().includes(q));
}

function render() {
  const board = $('board');

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

  const ordered = visible.sort((a, b) => {
    const av = a.shownBest ? cellValue(a.shownBest) : Infinity;
    const bv = b.shownBest ? cellValue(b.shownBest) : Infinity;
    return av - bv;
  });

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
        text += ` · this window only contains ${lo}-${hi} night trips. ` +
                `Your dates are ${Math.round((new Date(state.meta.return_dates[Math.floor(state.meta.return_dates.length / 2)]) - new Date(state.meta.depart_dates[Math.floor(state.meta.depart_dates.length / 2)])) / 86400000)} days apart. ` +
                `Move "Return around" closer to "Depart around" to look for short trips.`;
      } else {
        text += ' · nothing matches; try fewer days or a wider nights range.';
      }
    }
    $('constraintnote').textContent = text;
    $('constraintnote').classList.toggle('warn', !kept && all > 0);
  } else {
    $('constraintnote').hidden = true;
    $('constraintnote').textContent = '';
    $('constraintnote').classList.remove('warn');
  }

  const total = state.destinations.size;
  $('filtercount').hidden = !state.filter;
  $('filtercount').textContent = state.filter
    ? `showing ${ordered.length} of ${total}${ordered.length ? '' : ', nothing matches'}`
    : '';

  // A keyboard user navigating the grid loses focus when the board is rebuilt (every
  // streamed destination, every verify fold-back). Remember which cell had it and put it
  // back on the equivalent cell afterwards.
  const af = document.activeElement;
  const keep = af && af.matches && af.matches('td[role="button"]')
    ? { dest: af.closest('.card') && af.closest('.card').dataset.dest, r: af.dataset.r, c: af.dataset.c }
    : null;

  seedExpanded(ordered);

  // Each card gets its own colour scale, computed from just its own cells.
  board.replaceChildren(...ordered.map((dest) => renderCard(dest, scaleDomain(dest.allowed))));

  if (keep && keep.dest) {
    const cell = board.querySelector(
      `.card[data-dest="${keep.dest}"] td[data-r="${keep.r}"][data-c="${keep.c}"][role="button"]`
    );
    if (cell) { cell.tabIndex = 0; cell.focus({ preventScroll: true }); ensureVisible(cell); }
  }

  state.lastOrdered = ordered;
  syncExpandAll(ordered);
  renderHeadline(ordered);
  renderTable(ordered);
  refreshRegionCounts();
  $('footnote').hidden = ordered.length === 0;
  $('legend').hidden = ordered.length === 0;
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
function renderHeadline(ordered) {
  const host = $('headline');
  const top = ordered.filter((d) => d.shownBest).slice(0, 3);
  host.hidden = top.length === 0;
  if (!top.length) {
    host.replaceChildren();
    return;
  }

  const cur = state.meta.currency;
  const trip = (cell) =>
    `${weekday(cell.depart)} ${shortDate(cell.depart)} to ${weekday(cell.ret)} ` +
    `${shortDate(cell.ret)}, ${cell.nights} night${cell.nights === 1 ? '' : 's'}`;

  host.replaceChildren(...top.map((dest, i) => {
    const cell = dest.shownBest;
    const b = document.createElement('button');
    b.type = 'button';
    b.className = i === 0 ? 'headline-item is-lead' : 'headline-item';
    b.innerHTML =
      `<span class="headline-city">${dest.city}</span>` +
      `<span class="headline-price">${fmtMoney(cellValue(cell), cur)}</span>` +
      `<span class="headline-when">${trip(cell)}</span>` +
      (cell.verified ? '<span class="tag live">live</span>' : '<span class="tag">est</span>');
    b.title = `Show ${dest.city} on the board`;
    // The visible spans are flex items with no whitespace between them, so the derived
    // accessible name would run together as "Larnaca352Fri Oct 9". State it properly.
    b.setAttribute('aria-label',
      `${dest.city}, ${fmtMoney(cellValue(cell), cur)}, ${trip(cell)}, ` +
      `${cell.verified ? 'live price' : 'estimate'}. Show it on the board.`);
    b.addEventListener('click', () => {
      // There is nothing to jump to while the destination is collapsed, so open it first.
      // render() is synchronous, so the rebuilt card is queryable immediately after.
      if (!isExpanded(dest.destination)) {
        expanded.add(dest.destination);
        userToggled = true;
        render();
      }
      const card = $('board').querySelector(`.card[data-dest="${dest.destination}"]`);
      if (card) locateBest(card, dest);
    });
    return b;
  }));
}

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

/* Which destinations show their full grid. Survives the wholesale board rebuild that every
   stream event triggers, exactly like animatedDests and scrollOffsets. */
const expanded = new Set();

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
let userToggled = false;

function isExpanded(code) {
  return expanded.has(code);
}

/* How many destinations open by default.
 *
 * Three, not one and not all. The task has two phases: compare destinations, which needs
 * ordered headline numbers rather than grids, then choose dates for a candidate or two,
 * which needs the grid. Opening everything serves neither, because twenty grids cannot be
 * compared, only scrolled past. Opening nothing hides the thing that makes this board
 * different from a ranked price list, which is several date grids side by side.
 *
 * Three is the number of columns the board lays out at desktop widths
 * (minmax(420px, 1fr)), so the default is exactly one row of real grids with strips below.
 * A fixed count rather than one derived from the measured column count: deriving it would
 * make the default reshuffle itself on every window resize. */
const AUTO_EXPAND_COUNT = 3;

/* Until the user touches a disclosure, the open set IS the cheapest AUTO_EXPAND_COUNT,
 * recomputed on every render. The moment they toggle anything, this stops entirely and the
 * set is theirs.
 *
 * Two simpler versions were tried and measured first, and both were wrong:
 *   - Seed once on the first render. Destinations stream in one at a time, so that render
 *     holds exactly ONE of them and slice(0, 3) could only ever open that one.
 *   - Top up across renders and latch at three. That opens whichever three ARRIVED first,
 *     which is not the cheapest three, because the ordering churns as prices land. It
 *     measured 3 open with only 1 of them in the top row.
 *
 * Recomputing does mean grids open and close while the search streams. That is acceptable
 * because the board is already reflowing hard during a search: cards are re-sorted by price
 * on every event, so they jump position anyway. The payoff is that when the stream settles,
 * the open grids are the right ones, with no stale choice to notice and undo. */
function seedExpanded(ordered) {
  if (userToggled || !ordered.length) return;
  expanded.clear();
  for (const dest of ordered.slice(0, AUTO_EXPAND_COUNT)) expanded.add(dest.destination);
}

/* One control for the whole board, because doing this per destination is twenty clicks.
   The label states what pressing it will DO rather than naming a mode, and it flips to
   "Collapse all" only when everything is already open, so the common case (some closed)
   always offers the expanding action. */
function syncExpandAll(ordered) {
  const btn = $('expandall');
  btn.hidden = ordered.length === 0;
  if (!ordered.length) return;
  const allOpen = ordered.every((d) => isExpanded(d.destination));
  btn.textContent = allOpen ? 'Collapse' : 'Expand';
  btn.title = allOpen
    ? 'Collapse every destination to a single row'
    : 'Show every destination’s full date grid';
  btn.onclick = () => {
    userToggled = true;          // the user is driving now
    if (allOpen) expanded.clear();
    else for (const d of ordered) expanded.add(d.destination);
    render();
  };
}

/* One cell per departure date, coloured by the cheapest fare available that day: the
   matrix flattened onto its departure axis. This is what makes a collapsed row useful
   rather than merely short, because "which day should I leave" is most of what the grid
   gets scanned for. Same ramp as the grid, so the two read as one system. */
function departureStrip(dest, domain) {
  const wrap = document.createElement('div');
  wrap.className = 'strip';

  const cheapestByDeparture = new Map();
  for (const cell of dest.allowed || []) {
    const v = cellValue(cell);
    if (v == null) continue;
    const cur = cheapestByDeparture.get(cell.depart);
    if (cur == null || v < cur.v) cheapestByDeparture.set(cell.depart, { v, cell });
  }

  for (const depart of axesFor(dest).departs) {
    const hit = cheapestByDeparture.get(depart);
    const i = document.createElement('i');
    if (!hit) {
      i.className = 'strip-cell strip-none';
      i.title = `${weekday(depart)} ${shortDate(depart)}: no price`;
    } else {
      const idx = rampIndex(hit.v, domain);
      i.className = 'strip-cell' + (idx === null ? ' unscaled' : ` q${idx}`);
      i.title = `${weekday(depart)} ${shortDate(depart)}: from ` +
        `${fmtMoney(hit.v, state.meta.currency)} (${hit.cell.nights} nights)`;
    }
    if (isWeekend(depart)) i.classList.add('strip-weekend');
    wrap.appendChild(i);
  }

  // No caption here on purpose. It used to print "cheapest by departure day" beside every
  // collapsed row, which on a twenty-destination board is the same sentence twenty times.
  // It is stated once in the legend instead, and every cell carries the full figure in its
  // title.
  return wrap;
}

function renderCard(dest, domain) {
  const meta = state.meta;
  const card = document.createElement('section');
  card.className = 'card';
  card.dataset.dest = dest.destination;
  if (state.globalBest && state.globalBest.dest === dest.destination) card.classList.add('is-winner');
  if (!animatedDests.has(dest.destination)) {
    card.classList.add('is-new');
    animatedDests.add(dest.destination);
  }

  const head = document.createElement('div');
  head.className = 'card-head';
  const best = dest.shownBest ? cellValue(dest.shownBest) : null;
  // Say plainly whether the headline number is a live price or still an estimate:
  // verifying a cell often makes it worse, so a card can bounce back up the board as its
  // best falls through to the next unverified estimate.
  const bestTag = dest.shownBest && dest.shownBest.verified
    ? '<span class="tag live">live</span>'
    : dest.shownBest && dest.shownBest.is_total
      ? `<span class="tag real">${(dest.shownBest.source || 'real')}</span>`
      : '<span class="tag">est</span>';
  head.innerHTML =
    `<h2>${dest.city}</h2>` +
    `<span class="code">${dest.destination}${dest.country ? ' · ' + dest.country : ''}</span>` +
    `<span class="cov" title="${dest.coverage.populated} of ${dest.coverage.valid} date pairs priced">${dest.coverage.populated}/${dest.coverage.valid}</span>` +
    headlineChip(dest) +
    `<span class="best">${best != null ? fmtMoney(best, meta.currency) : ''} ${bestTag}</span>`;

  /* Collapsed by default. Twenty full matrices, each with its own scrollbar, is a wall of
     grids: the page cannot be taken in, and it gets worse the more destinations you ask
     for. Collapsed, a destination is one line plus a strip showing WHICH departure days
     are cheap, which is the question a grid answers by being scanned. Expand the ones
     worth the detail.
     The toggle sits first among the controls because it governs everything after it. */
  const open = isExpanded(dest.destination);
  card.classList.add(open ? 'is-open' : 'is-collapsed');
  const toggle = document.createElement('button');
  toggle.className = 'fillbtn disclose';
  toggle.type = 'button';
  toggle.textContent = open ? '−' : '+';   // minus / plus
  toggle.title = open ? `Collapse ${dest.city}` : `Show ${dest.city}'s full date grid`;
  toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  toggle.setAttribute('aria-label',
    open ? `Collapse ${dest.city}` : `Show ${dest.city}'s full date grid`);
  toggle.onclick = () => {
    if (isExpanded(dest.destination)) expanded.delete(dest.destination);
    else expanded.add(dest.destination);
    // Any manual toggle ends the one-time auto-expand, so the winner changing as prices
    // stream in cannot reopen something the user just closed.
    userToggled = true;
    render();
  };
  head.appendChild(toggle);

  if (!open) {
    card.appendChild(head);
    card.appendChild(departureStrip(dest, domain));
    return card;
  }

  // Bulk live fill: ~1 minute for a whole grid, and it replaces every estimate with a
  // real price for the actual passenger mix. This is the answer to sparse cached data.
  const fillBtn = document.createElement('button');
  fillBtn.className = 'fillbtn';
  const state_ = fillState.get(dest.destination);
  if (state_ && state_.running) {
    fillBtn.textContent = `${state_.progress}/${state_.total} ✕`;
    fillBtn.title = 'Click to stop filling';
    fillBtn.onclick = () => stopFill(dest.destination);
  } else {
    fillBtn.textContent = 'Fill live';
    fillBtn.title = 'Price every cell live for your real passenger mix (about a minute)';
    fillBtn.onclick = () => startFill(dest);
  }
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

  head.appendChild(fillBtn);

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
          verifyCell(dest, { depart, ret });
        }, `${dest.city}, ${weekday(depart)} ${shortDate(depart)} to ${weekday(ret)} ${shortDate(ret)}. No price yet. Press Enter to fetch it live.`);
        tr.appendChild(td);
        return;
      }

      const value = cellValue(cell);
      const idx = rampIndex(value, domain);
      // Excluded cells stay visible but recede, so you can still see what you ruled out
      // and how much it would have cost.
      td.className =
        'priced ' + (idx === null ? 'unscaled' : `q${idx}`) +
        (cellAllowed(cell) ? '' : ' excluded') +
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
  }
  return card;
}

/** The accessible relief for the light end of the ramp: every priced cell as text,
    sortable by any column. */
const tableSort = { key: 'total', dir: 1 };   // price, ascending

function renderTable(ordered) {
  const host = $('tableview');
  if (!ordered || !ordered.length) {
    host.replaceChildren();
    return;
  }
  const cur = state.meta.currency;
  const cols = [
    { key: 'dest', label: 'Destination', cell: (r) => `${r.dest.city} (${r.dest.destination})`,
      cmp: (a, b) => a.dest.city.localeCompare(b.dest.city) },
    { key: 'depart', label: 'Depart', cell: (r) => `${weekday(r.cell.depart)} ${shortDate(r.cell.depart)}`,
      cmp: (a, b) => a.cell.depart.localeCompare(b.cell.depart) },
    { key: 'return', label: 'Return', cell: (r) => `${weekday(r.cell.ret)} ${shortDate(r.cell.ret)}`,
      cmp: (a, b) => a.cell.ret.localeCompare(b.cell.ret) },
    { key: 'nights', label: 'Nights', num: true, cell: (r) => r.cell.nights,
      cmp: (a, b) => a.cell.nights - b.cell.nights },
    { key: 'total', label: 'Total', num: true, cell: (r) => fmtMoney(r.value, cur),
      cmp: (a, b) => a.value - b.value },
    { key: 'source', label: 'Source',
      cell: (r) => `<span class="tag${r.cell.verified ? ' live' : ''}">${r.cell.verified ? 'live' : 'est'}</span>`,
      cmp: (a, b) => (a.cell.verified ? 1 : 0) - (b.cell.verified ? 1 : 0) },
    { key: 'stops', label: 'Stops', cell: (r) => fmtStops(r.cell.transfers),
      cmp: (a, b) => (a.cell.transfers == null ? 9 : a.cell.transfers) - (b.cell.transfers == null ? 9 : b.cell.transfers) },
  ];

  const rows = [];
  for (const dest of ordered) {
    for (const cell of dest.cells) rows.push({ dest, cell, value: cellValue(cell) });
  }
  const active = cols.find((c) => c.key === tableSort.key) || cols[4];
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
}

/* Click a heading to sort; same column again flips direction. */
$('tableview').addEventListener('click', (e) => {
  const th = e.target.closest('th[data-sort]');
  if (!th || !state.lastOrdered) return;
  const key = th.dataset.sort;
  tableSort.dir = tableSort.key === key ? -tableSort.dir : 1;
  tableSort.key = key;
  renderTable(state.lastOrdered);
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
        `${l.carrier ? ' · ' + l.carrier : ''}${l.code ? ' ' + l.code : ''}</span></div>`;
    }).join('');
    return `<div class="segments"><b>${label}</b>` +
      // One middle dot per line: duration and stop count used to take one each, which made
      // the summary read as a dot-separated list rather than a sentence.
      `<div class="sector-summary">${s.departs || ''} → ${split(s.arrives).time || ''}` +
      `<span class="muted">${s.duration ? ' · ' + s.duration : ''}` +
      `${s.duration ? ', ' : ' · '}${fmtStops(s.stops || 0)}</span></div>` +
      legs + '</div>';
  };
  // Name the source and its price: the cross-check's cheapest is often a DIFFERENT
  // itinerary from the board's, so two unlabelled "departs" times read as a contradiction.
  const head = `<div class="segments-head">Flight times · ${details.price != null
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
      `<div class="muted">${weekday(cell.depart)} ${shortDate(cell.depart)} &rarr; ${weekday(cell.ret)} ${shortDate(cell.ret)} &middot; ${cell.nights || ''} nights</div>` +
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
  return d.toISOString().slice(0, 10);
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

/** Scroll a card's grid so its cheapest cell is centred, and flash it. */
function locateBest(card, dest) {
  const wrap = card.querySelector('.matrix-wrap');
  const target = card.querySelector('td.best-board') || card.querySelector('td.best-here');
  if (!wrap || !target) return;

  // Centre it manually rather than scrollIntoView, which would also scroll the page and
  // move every other card out from under the pointer.
  wrap.scrollTo({
    left: Math.max(0, target.offsetLeft - wrap.clientWidth / 2 + target.offsetWidth / 2),
    top: Math.max(0, target.offsetTop - wrap.clientHeight / 2 + target.offsetHeight / 2),
    behavior: REDUCE_MOTION.matches ? 'auto' : 'smooth',
  });
  rememberScroll(dest.destination, wrap);

  target.classList.remove('flash');
  void target.offsetWidth;          // restart the animation if it is already running
  target.classList.add('flash');
  setTimeout(() => target.classList.remove('flash'), 1600);

  // Keyboard path: the locate button hands focus to the cheapest cell, so the next
  // Enter prices it.
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

/* ---------------------------------------------------------------- bulk fill */

const fillState = new Map(); // IATA -> {running, progress, total, source, id}

/** Apply one live-priced cell into the board model. */
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

function startFill(dest) {
  const meta = state.meta;
  const code = dest.destination;
  if (fillState.get(code)?.running) return;

  fetch('/api/fill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      origin: meta.origin,
      destination: code,
      depart_date: meta.depart_dates[Math.floor(meta.depart_dates.length / 2)],
      return_date: meta.return_dates[Math.floor(meta.return_dates.length / 2)],
      adults: meta.adults,
      children: meta.children,
      currency: meta.currency,
      nonstop_only: meta.nonstop_only,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      const source = new EventSource(`/api/fill/${data.fill_id}/stream`);
      fillState.set(code, { running: true, progress: 0, total: data.pending, source, id: data.fill_id });
      render();

      let sinceRender = 0;
      source.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        const st = fillState.get(code);
        if (msg.type === 'fill_start') {
          if (st) st.total = msg.total_cells;
        } else if (msg.type === 'fill_cell') {
          if (st) st.progress = msg.progress;
          if (msg.ok) applyCell(dest, msg);
          // Repaint periodically rather than per cell; a full grid is ~200 events.
          if (++sinceRender >= 12) {
            sinceRender = 0;
            recomputeBest(code);
            render();
          }
        } else if (msg.type === 'fill_done') {
          $('progress').textContent = `${dest.city}: ${msg.note}`;
        } else if (msg.type === 'error') {
          $('errors').textContent = msg.message;
        }
      };

      const finish = () => {
        source.close();
        fillState.set(code, { running: false, progress: 0, total: 0 });
        recomputeBest(code);
        render();
      };
      source.addEventListener('end', finish);
      source.onerror = finish;
    })
    .catch((err) => {
      $('errors').textContent = `Fill failed: ${err}`;
    });
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

function stopFill(code) {
  const st = fillState.get(code);
  if (!st) return;
  if (st.id) fetch(`/api/fill/${st.id}/cancel`, { method: 'POST' }).catch(() => {});
  if (st.source) st.source.close();
  fillState.set(code, { running: false, progress: 0, total: 0 });
  recomputeBest(code);
  render();
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
  // On a phone the filter panel fills the screen, so fold it away on search. On desktop
  // it sits above the board, so leave it as the user set it and filters stay easy to tune.
  if (window.matchMedia('(max-width: 720px)').matches) {
    document.body.classList.remove('opts-open');
    $('optsbtn').setAttribute('aria-expanded', 'false');
  }
  state.destinations.clear();
  state.meta = null;
  $('board').replaceChildren();
  $('tableview').replaceChildren();
  $('errors').textContent = '';
  $('empty').hidden = true;
  $('headline').hidden = true;   // no winner until something comes back
  $('expandall').hidden = true;  // nothing to expand yet either
  // Orientation is a first-run thing; once you've searched, you know. The date hint is
  // part of that same orientation (the field labels and the first-run lede already say
  // it), and it was costing a permanent line in the status strip above every board.
  $('firstrun').hidden = true;
  $('datehint').hidden = true;
  stopAutoVerify();             // a new search invalidates any in-flight cross-check
  $('growing').hidden = true;   // clear any stale rate-limit / widening notice
  $('note').hidden = true;
  scrollOffsets.clear();
  animatedDests.clear();        // a new board: let every destination animate in again
  expanded.clear();             // and let the new winner be the one that opens
  destAxes.clear();             // every destination back on the board's own axes
  widening.clear();
  userToggled = false;
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
    // Sent with the search so the destination budget is spent inside the filter, not on
    // the cheapest destinations anywhere which are then hidden.
    destination_filter: $('destfilter').value.trim(),
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
      state.destinations.set(msg.destination, msg);
      seen += 1;
      $('progress').textContent = `${seen} of ${expected} destinations…`;
      render();
    } else if (msg.type === 'destination_empty') {
      seen += 1;
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
      if (msg.destinations) {
        const cov = [...state.destinations.values()].map(
          (d) => (100 * d.coverage.populated) / d.coverage.valid
        );
        const mean = cov.reduce((a, b) => a + b, 0) / (cov.length || 1);
        $('progress').textContent =
          `${msg.destinations} destinations, cheapest first · ${mean.toFixed(0)}% of cells priced`;
      } else {
        $('progress').textContent = '';
        $('empty').hidden = false;
        $('empty').textContent = msg.note || 'Nothing came back for this window.';
      }
      // The backend warns when the window is far enough out that the cache is sparse.
      $('note').textContent = msg.note || '';
      $('note').hidden = !msg.note;
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

function renderRegionTree(tree) {
  const root = $('regiontree');
  root.replaceChildren();
  for (const cont of tree) {
    const contCodes = cont.subregions.flatMap((s) => s.countries.map((c) => c.code));
    const subs = cont.subregions.map((sub) =>
      regionBranch(sub.name, sub.countries.map((c) => c.code),
        sub.countries.map((c) => regionLeaf(c.code, c.name))));
    root.appendChild(regionBranch(cont.continent, contCodes, subs));
  }
  root.addEventListener('change', onRegionChange);
  $('regionclear').addEventListener('click', () => {
    state.regions.clear();
    afterRegionChange();
  });
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

/** Re-sync every checkbox to `state.regions`, then the clear button, counts and stale mark. */
function afterRegionChange() {
  for (const cb of $('regiontree').querySelectorAll('input[type=checkbox]')) {
    const codes = (cb.dataset.codes || '').split(',').filter(Boolean);
    const on = codes.filter((c) => state.regions.has(c)).length;
    cb.checked = on > 0 && on === codes.length;
    cb.indeterminate = on > 0 && on < codes.length;
  }
  $('regionclear').hidden = state.regions.size === 0;
  refreshRegionCounts();
  markSearchStale();
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

$('destfilter').addEventListener('input', (e) => {
  state.filter = e.target.value.trim().toLowerCase();
  if (state.meta) render();
});

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
$('tabletoggle').addEventListener('click', () => document.body.classList.toggle('show-table'));

/* Mobile: the options bar is collapsed by default behind this toggle, so it stops
   filling the screen. No effect on desktop, where the whole row just wraps. */
$('optsbtn').addEventListener('click', () => {
  const open = document.body.classList.toggle('opts-open');
  $('optsbtn').setAttribute('aria-expanded', open ? 'true' : 'false');
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

// Default period: ~3 weeks starting a month out, looking for a 5-9 night trip inside it.
$('depart').value = isoToday(30);
$('ret').value = isoToday(51);
$('nmin').value = '5';
$('nmax').value = '9';

// A shared/bookmarked board carries its search in the query string; it wins over the
// isoToday and server defaults, and auto-runs on load.
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
