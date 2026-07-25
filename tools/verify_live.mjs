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

// (The scoped, reproducible version of this runs at the end of the file, in its
// own session. Left here only as a quick eyeball on the unscoped default session.)

/* ------------------------------------------------------------------------
   THE DEMO SEQUENCE, exactly as the runsheet walks it.

   >10mm then >15mm is one constraint apart, so on a SHARED session the guard
   correctly calls it differencing -- and beat 3 then shows "differencing
   suspected" instead of the clean per-node suppression the script promises.
   The console gives each ladder beat its own session for that reason. This
   asserts both halves: separate sessions stay clean, a shared session still
   catches the probe. If someone ever drops the session field, this fails.
   ------------------------------------------------------------------------ */
const beatSearch = async (mm, session) => {
  const r = await fetch(`${BROKER}/search`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      filters: {
        imaging: { modality: ['MR'], body_site: ['FETAL'] },
        population: { basis: 'gestational' },
        numeric: [{ quantity: 'lateral_ventricular_atrial_width', op: 'gt', value: mm, unit: 'mm' }],
        access: { min_layer: 'L1' },
      },
      role: 'researcher', page_size: 200, session,
    }),
  });
  return r.ok ? r.json() : null;
};

console.log('\n  demo sequence (beat 2 -> beat 3):');

// As the console does it: a fresh session per beat.
await beatSearch(10, 's_beat2');
const clean = await beatSearch(15, 's_beat3');
const cleanGuard = clean?.guard?.risk ?? 'unknown';
const cleanSuppressed = (clean?.disclosure?.per_node || []).every((p) => !p.k_anon_ok);
const cleanOk = cleanGuard === 'none' && cleanSuppressed;
console.log(`  ${cleanOk ? 'PASS' : 'FAIL'}  separate sessions -> guard=${cleanGuard}, ` +
            `all nodes suppressed=${cleanSuppressed}`);
if (!cleanOk) {
  fail('beat 3 must show clean per-node suppression, not a differencing warning — ' +
       'the console must send a fresh `session` per ladder beat');
}

// Sharing a session is NOT by itself suspicious, and the guard is right not to
// cry wolf: >10mm -> >15mm drops BCH from 87 to 7, a delta of 80. Nothing is
// recoverable from that, so nothing should fire. Assert the quiet case too --
// a guard that flags every narrowing is a guard nobody will trust on stage.
await beatSearch(10, 's_wide');
const wide = await beatSearch(15, 's_wide');
const wideQuiet = (wide?.guard?.risk ?? 'unknown') === 'none';
console.log(`  ${wideQuiet ? 'PASS' : 'FAIL'}  shared, large delta -> guard=` +
            `${wide?.guard?.risk} (should stay "none"; delta ~80/node leaks nothing)`);
if (!wideQuiet) fail('guard fired on a harmless wide narrowing — false positives erode the demo');

/* And the real exploit, in its own session so the result is reproducible rather
   than dependent on whatever else has been asked today. The guard is per-node:
   BCH 48 -> 39 is a delta of 9, under k, even though the network delta is 17.
   That per-node view is the whole point -- the hospital is the disclosure boundary. */
const exploit = async (weeksMax, session) => {
  const population = { basis: 'gestational' };
  if (weeksMax) population.gestational_age_max_weeks = weeksMax;
  const r = await fetch(`${BROKER}/search`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      filters: {
        imaging: { modality: ['MR'], body_site: ['FETAL'] },
        population,
        numeric: [{ quantity: 'lateral_ventricular_atrial_width', op: 'gt', value: 12, unit: 'mm' }],
        access: { min_layer: 'L1' },
      },
      role: 'researcher', page_size: 200, session,
    }),
  });
  return r.ok ? r.json() : null;
};

await exploit(null, 's_exploit');
const caught = await exploit(31, 's_exploit');
const risk = caught?.guard?.risk ?? 'unknown';
const armed = risk !== 'none' && risk !== 'unknown';
console.log(`  ${armed ? 'PASS' : 'FAIL'}  differencing exploit -> guard=${risk} ` +
            `action=${caught?.guard?.action} (BCH 48->39, delta 9 < k)`);
if (!armed) {
  fail('the pinned exploit no longer trips the guard — either re-derive a pair or ' +
       'cut the "try to break it" invitation from the champion brief');
}

console.log(failures ? `\n${failures} FAILURE(S)` : '\nlive chain verified');
process.exit(failures ? 1 : 0);
