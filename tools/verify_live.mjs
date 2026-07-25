/* Live integration check: console -> broker -> sidecars, the whole chain.
 *
 * verify_console.mjs proves the OFFLINE path. This proves the ONLINE one, which is
 * what will actually be on the projector. It builds each demo beat's filters exactly
 * the way the console's readFilters() does -- including population.basis, which the
 * broker's validator requires on fetal queries -- posts to :8000, and checks both the
 * ladder numbers and the Correction-1b guarantee that a suppressed node emits no
 * exact count anywhere in the payload.
 *
 * Run: node tools/verify_live.mjs      (needs the broker + sidecars up)
 */
const BROKER = 'http://localhost:8000';
const K = 10;

const BEATS = {
  '1b': {
    name: 'EF < 40%',
    expect: { BCH: 30, MGH: 53, BWH: 73 },
    filters: {
      imaging: { modality: ['MR'], body_site: ['HEART'] },
      numeric: [{ quantity: 'ejection_fraction', op: 'lt', value: 40, unit: '%' }],
      access: { min_layer: 'L1' },
    },
  },
  '2': {
    name: 'fetal atrial width > 10mm',
    expect: { BCH: 87, MGH: 78, BWH: 60 },
    filters: {
      imaging: { modality: ['MR'], body_site: ['FETAL'] },
      population: { basis: 'gestational' },
      numeric: [{ quantity: 'lateral_ventricular_atrial_width', op: 'gt', value: 10, unit: 'mm' }],
      access: { min_layer: 'L1' },
    },
  },
  '3': {
    name: 'severe > 15mm  (all suppress)',
    suppressAll: true,
    filters: {
      imaging: { modality: ['MR'], body_site: ['FETAL'] },
      population: { basis: 'gestational' },
      numeric: [{ quantity: 'lateral_ventricular_atrial_width', op: 'gt', value: 15, unit: 'mm' }],
      access: { min_layer: 'L1' },
    },
  },
};

let failures = 0;
const fail = (m) => { console.log(`        ${m}`); failures++; };

try {
  const meta = await (await fetch(`${BROKER}/nodes`)).json();
  console.log(`  broker up · ${meta.nodes.length} nodes · k=${meta.k_anon_threshold}\n`);
} catch (e) {
  console.log(`  BROKER DOWN (${e.message}) — start it, or the console falls back to fixtures.`);
  process.exit(1);
}

for (const [id, beat] of Object.entries(BEATS)) {
  const res = await fetch(`${BROKER}/search`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ filters: beat.filters, role: 'researcher', page_size: 200 }),
  });

  if (!res.ok) {
    let d = res.status;
    try { d = (await res.json()).detail; } catch (_) { /* non-JSON */ }
    console.log(`  FAIL  beat ${id}  ${beat.name}`);
    fail(`broker refused: ${d}`);
    continue;
  }

  const raw = await res.text();
  const j = JSON.parse(raw);
  const per = j.disclosure?.per_node || [];
  const got = Object.fromEntries(
    per.map((p) => [p.node, p.k_anon_ok ? p.records_returned : p.approximate_count])
  );

  if (beat.suppressAll) {
    const allSup = per.length > 0 && per.every((p) => !p.k_anon_ok);
    // The Correction-1b guarantee, checked against the WIRE not the renderer:
    // no suppressed node may carry a nonzero exact count anywhere in the payload.
    const leak = per.filter((p) => !p.k_anon_ok && p.records_returned > 0);
    const ok = allSup && leak.length === 0 && (j.results || []).length === 0;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  beat ${id}  ${beat.name.padEnd(30)} ` +
                `${JSON.stringify(got)}`);
    if (!allSup) fail('expected every node to suppress');
    if (leak.length) fail(`LEAK: exact count on ${leak.map((p) => p.node).join(',')}`);
    if ((j.results || []).length) fail(`LEAK: ${j.results.length} records returned`);
  } else {
    const ok = Object.entries(beat.expect).every(([n, v]) => got[n] === v);
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  beat ${id}  ${beat.name.padEnd(30)} ` +
                `${JSON.stringify(got)}`);
    if (!ok) fail(`expected ${JSON.stringify(beat.expect)}`);
  }

  // Every rendered row must carry a why-string; the UI prints it verbatim and an
  // empty one reads as an unexplained match, which is the opposite of the pitch.
  const missing = (j.results || []).filter((r) => !r.why?.reason_text).length;
  if (missing) fail(`${missing} result(s) missing why.reason_text`);
}

/* The differencing exploit, live. Both probes permitted; the guard should notice. */
const probe = async (mmGt, weeksMax) => {
  const filters = {
    imaging: { modality: ['MR'], body_site: ['FETAL'] },
    population: { basis: 'gestational', ...(weeksMax ? { gestational_age_max_weeks: weeksMax } : {}) },
    numeric: [{ quantity: 'lateral_ventricular_atrial_width', op: 'gt', value: mmGt, unit: 'mm' }],
    access: { min_layer: 'L1' },
  };
  const r = await fetch(`${BROKER}/search`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ filters, role: 'researcher', page_size: 200 }),
  });
  if (!r.ok) return null;
  const j = await r.json();
  return { n: j.disclosure?.returned_count ?? 0, guard: j.guard };
};

const a = await probe(12);
const b = await probe(12, 31);
if (a && b) {
  const delta = a.n - b.n;
  const caught = b.guard && b.guard.risk && b.guard.risk !== 'none';
  console.log(`\n  differencing probe  >12mm=${a.n}  +<=31wk=${b.n}  delta=${delta}`);
  console.log(`  guard on 2nd query: risk=${b.guard?.risk} action=${b.guard?.action}`);
  if (delta > 0 && delta < K && !caught) {
    fail(`guard did NOT fire on a sub-k delta of ${delta} — the "try to break it" ` +
         `invitation is not yet safe to offer`);
  }
} else {
  console.log('\n  differencing probe skipped (a probe was refused)');
}

console.log(failures ? `\n${failures} FAILURE(S)` : '\nlive chain verified');
process.exit(failures ? 1 : 0);
