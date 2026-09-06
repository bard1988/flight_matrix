// Run the real renderTimes() from app.js against a live /api/details payload, so the
// indented numbered legs are verified as rendered output rather than as source that looks right.
import { readFileSync } from 'node:fs';

const src = readFileSync('frontend/app.js', 'utf8');
const start = src.indexOf('function renderTimes(');
const end = src.indexOf('\n}\n', start) + 3;
const fnSrc = src.slice(start, end);

const state = { meta: { currency: 'ils' } };
const fmtMoney = (v, c) => `${Math.round(v).toLocaleString()} ${String(c).toUpperCase()}`;
const renderTimes = new Function('state', 'fmtMoney', `${fnSrc}; return renderTimes;`)(state, fmtMoney);

const [dest, depart, ret] = process.argv.slice(2);
const res = await fetch('http://127.0.0.1:8712/api/details', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    origin: 'TLV', destination: dest, depart_date: depart, return_date: ret,
    adults: 2, children: 3, currency: 'ils',
  }),
});
const details = await res.json();
const html = renderTimes(details);

// Print it as indented text so the nesting is visible in a terminal.
const text = html
  .replace(/<div class="segments">/g, '\n')
  .replace(/<div class="sector-summary">/g, '\n    ')
  .replace(/<div class="leg">/g, '\n       ')
  .replace(/<span class="legno">(\d+)<\/span>/g, '$1. ')
  .replace(/<[^>]+>/g, '')
  .replace(/&rarr;/g, '->');
console.log(text.trim());
console.log('\n--- raw leg markup ---');
for (const m of html.matchAll(/<div class="leg">.*?<\/div>/g)) console.log(m[0]);
