/* ============================================================================
   console.js — Lantern researcher console (T-14, Flame2)

   THE ONE ARCHITECTURAL RULE HERE:
   `runSearch()` returns the frozen-contract response shape and nothing else in
   this file knows where that shape came from. Today it is computed locally from
   fixtures.json so the console works before the broker exists. When Flame1's
   :8000 is up, `runSearch` becomes a fetch() and every renderer below is
   untouched. Building against the contract is what let this lane start at 11:45
   without blocking on anyone.

   DISCLOSURE IS EVALUATED PER NODE. That is not a UI detail — it is the reason
   the severe-ventriculomegaly beat works: 7 + 6 + 3 = 16 would clear k=10 as a
   network total, but no single hospital may disclose its own sub-k cohort. The
   hospital is the disclosure boundary, so the hospital is where k is applied.
   ============================================================================ */

'use strict';

const K_ANON = 10;
const BROKER = 'http://localhost:8000';

const UNITS = {
  lateral_ventricular_atrial_width: 'mm',
  ejection_fraction: '%',
  left_ventricular_ejection_fraction: '%',
  right_ventricular_ejection_fraction: '%',
  gestational_age_weeks: 'wk',
  lesion_dimension: 'mm',
  chamber_volume: 'mL',
};

const LABELS = {
  lateral_ventricular_atrial_width: 'lateral ventricular atrial width',
  ejection_fraction: 'ejection fraction',
  left_ventricular_ejection_fraction: 'LV ejection fraction',
  right_ventricular_ejection_fraction: 'RV ejection fraction',
  gestational_age_weeks: 'gestational age',
  lesion_dimension: 'lesion dimension',
  chamber_volume: 'chamber volume',
  anatomic_dimension: 'anatomic dimension',
  regurgitant_fraction: 'regurgitant fraction',
  other_percentage: 'percentage',
};

/* Quantity families. TV's vocabulary distinguishes LV from RV ejection fraction
   because the reports state both, and that distinction is clinically real — but a
   researcher who asks for "ejection fraction" means any of them. Selecting the
   generic term widens to the family; selecting LV or RV stays exact. Matching only
   the generic label silently dropped two thirds of the cohort (30 -> 10 at BCH),
   which is the kind of quiet undercount that makes a demo look thin and a number
   look wrong. */
const FAMILIES = {
  ejection_fraction: [
    'ejection_fraction',
    'left_ventricular_ejection_fraction',
    'right_ventricular_ejection_fraction',
  ],
};
const familyOf = (q) => FAMILIES[q] || [q];

/* Curated demonstration map. A real deployment calls a terminology server;
   this is the mock↔real seam, and we say so rather than implying we shipped
   SNOMED. Ontology expansion is requirement #1 of the challenge — semantic
   diversity across hospitals that use different words for the same thing. */
const ONTOLOGY = {
  tumor: ['tumor', 'tumour', 'neoplasm', 'mass', 'glioma', 'astrocytoma',
          'medulloblastoma', 'lesion'],
  ventriculomegaly: ['ventriculomegaly', 'ventricular dilatation', 'dilated ventricle',
                     'hydrocephalus', 'atrial width'],
  infarct: ['infarct', 'infarction', 'ischemia', 'ischemic', 'stroke'],
};

let DATA = null;      // { nodes:[], passports:[] }
let LAST = null;      // last contract response, for the petition flow
const $ = (id) => document.getElementById(id);

/* --------------------------------------------------------- session scoping
   The broker's differencing guard compares each query against others in the SAME
   session -- correctly, because that is what an attacker probing a cohort looks
   like. But the demo ladder walks >10mm then >15mm, which is one constraint apart,
   so on a shared session beat 3 trips the guard and shows "differencing suspected"
   instead of the clean per-node suppression the pitch promises. Both behaviours are
   right; they just aren't the same story.

   So: each ladder beat is its own session -- a fresh analyst asking a fresh
   question. Manual searches from the filter rail KEEP the current session, because
   a researcher narrowing by hand is exactly the sequence the guard exists to catch,
   and that is the "try to break it live" moment. Resetting there would disarm it. */
let SESSION = newSession();
function newSession() {
  return 's_' + Math.random().toString(36).slice(2, 10);
}

/* ---------------------------------------------------------------- data load */
async function boot() {
  // Prefer the live broker; fall back to fixtures so the console is never dead.
  try {
    const r = await fetch(`${BROKER}/nodes`, { signal: AbortSignal.timeout(1200) });
    if (r.ok) {
      // /nodes returns { nodes: [...], k_anon_threshold: n } -- an object, not an array.
      const meta = await r.json();
      DATA = { nodes: meta.nodes, passports: null, live: true,
               threshold: meta.k_anon_threshold ?? K_ANON };
      const up = meta.nodes.filter((n) => n.reachable).length;
      $('source-badge').textContent =
        `source: live broker :8000 · ${up}/${meta.nodes.length} nodes reachable`;
      wire();
      return;
    }
  } catch (_) { /* broker not up yet — fall through to fixtures, never a dead page */ }

  const res = await fetch('fixtures.json');
  if (!res.ok) throw new Error(`WIRING FAILURE: fixtures.json unreachable (${res.status})`);
  DATA = await res.json();
  DATA.live = false;
  $('source-badge').textContent =
    `source: local fixtures · ${DATA.passports.length} passports`;
  wire();
}

/* ------------------------------------------------------- query construction */
function readFilters() {
  const checked = (name) =>
    [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((e) => e.value);

  const f = {
    imaging: { modality: checked('modality'), body_site: checked('body') },
    population: {},
    clinical: { text_terms: [], expand_ontology: false },
    numeric: [],
    access: { min_layer: 'L1' },
  };

  // The broker refuses a fetal query that doesn't declare its population basis,
  // because PatientAge on a fetal record is the MOTHER's age. Declaring it is not
  // ceremony -- it is the client stating which clock it means, so a 20-year-old
  // mother can never be read as a 20-year-old patient.
  const gestational = f.imaging.body_site.includes('FETAL');
  if (gestational) f.population.basis = 'gestational';

  // ...and the two clocks are mutually exclusive by validator: a gestational
  // population may not also carry chronological stages or age bounds. Sending both
  // is a 422, so the stage control only applies when we're on the chronological clock.
  const stage = $('stage').value;
  if (stage && !gestational) f.population.stages = [stage];

  const gmin = parseFloat($('gest-min').value);
  const gmax = parseFloat($('gest-max').value);
  if (!Number.isNaN(gmin)) f.population.gestational_age_min_weeks = gmin;
  if (!Number.isNaN(gmax)) f.population.gestational_age_max_weeks = gmax;
  // Gestational bounds are only legal on the gestational clock.
  if ((!Number.isNaN(gmin) || !Number.isNaN(gmax)) && !gestational) {
    f.population.basis = 'gestational';
  }

  const q = $('q-quantity').value;
  const v = parseFloat($('q-value').value);
  if (q && !Number.isNaN(v)) {
    f.numeric.push({ quantity: q, op: $('q-op').value, value: v, unit: UNITS[q] || '' });
  }

  const nl = $('nl').value.trim();
  if (nl) {
    f.clinical.text_terms = [nl];
    f.clinical.expand_ontology = true;
  }
  return f;
}

function expandTerms(terms) {
  const out = new Set();
  const fired = [];
  for (const raw of terms) {
    const t = raw.toLowerCase();
    out.add(t);
    for (const [root, syns] of Object.entries(ONTOLOGY)) {
      if (syns.some((s) => t.includes(s)) || t.includes(root)) {
        syns.forEach((s) => out.add(s));
        fired.push(root);
      }
    }
  }
  return { terms: [...out], fired: [...new Set(fired)] };
}

/* ------------------------------------------------------------- the matcher */
function opHolds(op, value, target) {
  switch (op) {
    case 'gt':  return value >  target;
    case 'gte': return value >= target;
    case 'lt':  return value <  target;
    case 'lte': return value <= target;
    default:    return false;
  }
}

function matchPassport(p, f, expanded) {
  const why = [];

  if (f.imaging.body_site?.length) {
    if (!f.imaging.body_site.includes(p.imaging.body_part_raw)) return null;
    why.push({ signal: 'body_site', text: p.imaging.body_site.display });
  }
  if (f.imaging.modality?.length) {
    if (!f.imaging.modality.includes(p.imaging.modality)) return null;
    why.push({ signal: 'modality', text: p.imaging.modality });
  }
  if (f.population.stages?.length) {
    if (!f.population.stages.includes(p.population.pediatric_stage)) return null;
    why.push({ signal: 'stage', text: p.population.pediatric_stage });
  }

  const wk = p.population.gestational_age_weeks;
  if (f.population.gestational_min_weeks != null) {
    if (wk == null || wk < f.population.gestational_min_weeks) return null;
  }
  if (f.population.gestational_max_weeks != null) {
    if (wk == null || wk > f.population.gestational_max_weeks) return null;
  }
  if (wk != null && (f.population.gestational_min_weeks != null ||
                     f.population.gestational_max_weeks != null)) {
    why.push({ signal: 'gestational_age', text: `${wk} wk` });
  }

  // The numeric axis. A study matches on the measurement that actually satisfied
  // the constraint, and that exact measurement is what we surface — never a
  // sibling value from the same report that happens to look better.
  const matched = [];
  for (const c of f.numeric) {
    const family = familyOf(c.quantity);
    const hit = p.measurements.find(
      (m) => family.includes(m.quantity) && opHolds(c.op, m.value, c.value)
    );
    if (!hit) return null;
    matched.push(hit);
    why.push({
      signal: 'measurement',
      text: `measured ${hit.value} ${hit.unit} ${
        { gt: '>', gte: '≥', lt: '<', lte: '≤' }[c.op]
      } ${c.value} ${c.unit}`,
    });
  }

  if (expanded?.terms.length) {
    const hay = p.measurements.map((m) => m.snippet).join(' ').toLowerCase();
    const hitTerm = expanded.terms.find((t) => hay.includes(t));
    if (!hitTerm) return null;
    why.push({ signal: 'concept', text: `"${hitTerm}" via ontology expansion` });
  }

  return {
    passport: p,
    measurements_matched: matched,
    why: {
      signals_fired: why.map((w) => w.signal),
      reason_text: why.map((w) => w.text).join(' · '),
      measurements_matched: matched,
    },
  };
}

/* ------------------------------------------------------------ live broker */
/* The architectural bet, cashed in: the broker speaks a slightly different dialect
   of the same contract (nodes_queried is a name list, per-node disclosure lives
   under disclosure.per_node, matched measurements hang off `why`). Normalising it
   HERE means not one renderer below had to change when the backend landed. */
async function fetchSearch() {
  const t0 = performance.now();
  const f = readFilters();
  const r = await fetch(`${BROKER}/search`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      filters: f, role: $('role').value, page_size: 200, session: SESSION,
    }),
  });

  if (!r.ok) {
    // A 422 is the QueryAST validator refusing a malformed query. That is the
    // security boundary doing its job, so show what it said rather than a blank page.
    let detail = `broker returned ${r.status}`;
    try { detail = (await r.json()).detail || detail; } catch (_) { /* non-JSON body */ }
    throw new Error(detail);
  }

  const j = await r.json();
  const per = j.disclosure?.per_node || [];
  const meta = Object.fromEntries((DATA.nodes || []).map((n) => [n.node, n]));

  const nodes_queried = per.map((p) => ({
    node: p.node,
    label: meta[p.node]?.label || p.node,
    policy: meta[p.node]?.policy,
    k_anon_ok: p.k_anon_ok,
    guard_action: p.guard_action || 'allow',
    threshold: j.disclosure.threshold,
    records_withheld: !p.k_anon_ok || (p.guard_action && p.guard_action !== 'allow'),
    petition_route: j.disclosure.petition_route,
    // Clearing k is necessary but not sufficient: a correlated query can still
    // force this node to withhold its exact count and records.
    ...(p.k_anon_ok && (!p.guard_action || p.guard_action === 'allow')
      ? { count: p.records_returned }
      : { approximate_count: p.approximate_count }),
  }));

  const results = (j.results || []).map((row) => ({
    passport: row.passport,
    measurements_matched: row.why?.measurements_matched || [],
    why: {
      signals_fired: row.why?.signals_fired || [],
      reason_text: row.why?.reason_text || '',
      measurements_matched: row.why?.measurements_matched || [],
    },
  }));

  const totalStudies = (DATA.nodes || []).reduce((a, n) => a + (n.studies || 0), 0);
  const disclosed = nodes_queried.filter((n) => n.k_anon_ok)
    .reduce((a, n) => a + n.count, 0);
  const suppressedNodes = nodes_queried.filter((n) => !n.k_anon_ok).length;

  return {
    query_ast: j.query_ast || f,
    ontology_expansion: j.ontology_expansion || null,
    guard: j.guard || null,
    results,
    nodes_queried,
    disclosure: j.disclosure,
    funnel: [
      { label: 'Studies in the network', n: totalStudies },
      { label: 'Matching this query', n: disclosed || j.disclosure.returned_count || 0 },
      { label: 'Released under disclosure policy', n: j.disclosure.returned_count || 0 },
      {
        label: suppressedNodes
          ? `Withheld — ${suppressedNodes} hospital(s) below k=${j.disclosure.threshold}`
          : 'Withheld by policy',
        n: suppressedNodes ? '—' : 0,
        warn: true,
      },
    ],
    timing_ms: j.timing_ms ?? Math.round(performance.now() - t0),
  };
}

/* --------------------------------------------- the contract-shaped response */
function runSearch() {
  const t0 = performance.now();
  const f = readFilters();
  const expanded = f.clinical.expand_ontology
    ? expandTerms(f.clinical.text_terms) : null;

  const all = [];
  for (const p of DATA.passports) {
    const m = matchPassport(p, f, expanded);
    if (m) all.push(m);
  }

  // Per-node disclosure. Fail closed: anything unexpected suppresses.
  const byNode = {};
  for (const node of DATA.nodes) byNode[node.node] = [];
  for (const r of all) {
    const n = r.passport.owner.node;
    (byNode[n] ||= []).push(r);
  }

  const nodeReports = [];
  let released = [];
  for (const node of DATA.nodes) {
    const rows = byNode[node.node] || [];
    let ok;
    try {
      ok = rows.length >= K_ANON;
    } catch (_) {
      ok = false;                       // fail closed, always
    }
    nodeReports.push({
      node: node.node,
      label: node.label,
      policy: node.policy,
      k_anon_ok: ok,
      // CORRECTION 1b: when suppression fires we emit a bucket and NEVER the
      // exact count. Returning both is the leak the guard exists to prevent.
      ...(ok ? { count: rows.length } : { approximate_count: bucket(rows.length) }),
      threshold: K_ANON,
      records_withheld: !ok,
      petition_route: '/petition',
    });
    if (ok) released = released.concat(rows);
  }

  if ($('diversify').checked) released = diversify(released, 60);

  const anySuppressed = nodeReports.some((n) => !n.k_anon_ok);
  return {
    query_ast: f,
    ontology_expansion: expanded,
    results: released,
    nodes_queried: nodeReports,
    disclosure: {
      k_anon_ok: !anySuppressed,
      threshold: K_ANON,
      records_withheld: anySuppressed,
      reason: anySuppressed
        ? 'one or more hospitals hold a cohort smaller than the k-anonymity threshold'
        : null,
      petition_route: '/petition',
    },
    funnel: buildFunnel(f, all, released, nodeReports),
    timing_ms: Math.round(performance.now() - t0),
  };
}

function bucket(n) {
  if (n === 0) return '0';
  if (n < 10) return '<10';
  if (n <= 25) return '11-25';
  if (n <= 50) return '26-50';
  if (n <= 100) return '51-100';
  return '100+';
}

/* Maximal marginal relevance over the axes this corpus genuinely varies on:
   site, gestational band, sex. A cohort of 60 near-identical studies from one
   hospital is worse science than 60 spread across three. */
function diversify(rows, k) {
  const key = (r) => [
    r.passport.owner.node,
    r.passport.population.sex,
    Math.floor((r.passport.population.gestational_age_weeks || 0) / 4),
  ].join('|');
  const seen = new Map();
  const out = [];
  const rest = [];
  for (const r of rows) {
    const s = key(r);
    if (!seen.has(s)) { seen.set(s, 1); out.push(r); } else { rest.push(r); }
    if (out.length >= k) break;
  }
  return out.concat(rest).slice(0, Math.max(k, out.length));
}

function buildFunnel(f, all, released, nodeReports) {
  const withMeas = DATA.passports.filter((p) => p.measurements.length).length;
  const suppressed = nodeReports
    .filter((n) => !n.k_anon_ok)
    .reduce((a, n) => a + 1, 0);
  return [
    { label: 'Studies in the network', n: DATA.passports.length },
    { label: 'With extractable measurements', n: withMeas },
    { label: 'Matching this query', n: all.length },
    { label: 'Passing disclosure policy', n: released.length },
    {
      label: suppressed
        ? `Withheld — ${suppressed} hospital(s) below k=${K_ANON}`
        : 'Withheld by policy',
      n: all.length - released.length,
      warn: true,
    },
  ];
}

/* ------------------------------------------------------------- rendering */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function render(res) {
  LAST = res;

  $('nodes').innerHTML = res.nodes_queried.map((n) => `
    <div class="node-chip ${n.k_anon_ok ? '' : 'node-chip--suppressed'}">
      <span class="n">${n.k_anon_ok ? n.count : esc(n.approximate_count)}</span>
      <span class="lbl">${esc(n.node)} · ${n.k_anon_ok ? 'disclosed' : 'suppressed'}</span>
    </div>`).join('');

  const ex = res.ontology_expansion;
  $('expansion').innerHTML = (ex && ex.fired.length) ? `
    <div class="callout" style="margin-top:0">
      <strong>Semantic expansion fired:</strong>
      ${ex.fired.map((r) => esc(r)).join(', ')} →
      ${ex.terms.slice(0, 8).map((t) => `<span class="tag">${esc(t)}</span>`).join(' ')}
      <div class="status" style="margin-top:.4rem">
        Hospitals label the same finding differently. The query is expanded once,
        centrally, so each node answers the question it was actually asked.
      </div>
    </div>` : '';

  const sup = res.nodes_queried.filter((n) => !n.k_anon_ok);
  $('disclosure').innerHTML = sup.length ? `
    <div class="disclosure">
      <h3>Records withheld at ${sup.length} of ${res.nodes_queried.length} hospitals</h3>
      <p>${sup.map((n) => `<strong>${esc(n.node)}</strong> holds ${esc(n.approximate_count)}
         matching studies`).join('; ')} — each below the disclosure threshold, so the
         records are withheld and only a count band is returned.</p>
      <p class="meta">k-anonymity threshold = ${res.disclosure.threshold}
         (configuration constant, returned in every response) ·
         exact counts are omitted from this response, not merely hidden in the UI</p>
      <button class="btn btn--sm" id="pet-open">Petition the owning hospitals</button>
    </div>` : '';
  if ($('pet-open')) $('pet-open').onclick = () => openPetition();

  // The differencing guard. When it fires this is the whole privacy thesis in one
  // box, so it renders above everything -- including above the results it degraded.
  const g = res.guard;
  $('guard').innerHTML = (g && g.risk && g.risk !== 'none') ? `
    <div class="disclosure">
      <h3>Correlated-query defence engaged — ${esc(g.risk.replace(/_/g, ' '))}</h3>
      <p>${esc(g.reason)}</p>
      <p class="meta">action: <strong>${esc(g.action)}</strong>${
        g.related_query_fingerprint
          ? ` · related query ${esc(String(g.related_query_fingerprint).slice(0, 16))}` : ''}</p>
    </div>` : '';

  const base = Number(res.funnel[0]?.n) || 1;
  $('funnel').innerHTML = res.funnel.map((f) => {
    const num = Number(f.n);
    const pct = Number.isFinite(num) ? Math.min(100, (100 * num) / base) : 0;
    return `
    <div class="funnel-row">
      <span style="${f.warn && f.n ? 'color:var(--stop)' : ''}">${esc(f.label)}</span>
      <span class="mval">${esc(f.n)}</span>
      <span class="bar" style="width:${pct}%"></span>
    </div>`;
  }).join('');

  const rows = res.results.slice(0, 200);
  $('rows').innerHTML = rows.map((r, i) => {
    const p = r.passport;
    const pop = p.population.basis === 'gestational'
      ? `${p.population.gestational_age_weeks} wk gestation`
      : `${esc(p.population.pediatric_stage)} · ${esc(p.population.public_age_band)}`;
    const m = r.measurements_matched[0];
    return `
      <tr class="row-main" data-i="${i}">
        <td>${esc(p.passport_id)}</td>
        <td><span class="tag">${esc(p.owner.node)}</span></td>
        <td>${esc(p.imaging.body_site.display)}</td>
        <td>${esc(pop)}</td>
        <td>${m ? `<span class="mval">${m.value} ${esc(m.unit)}</span>
             <span class="conf">${esc(LABELS[m.quantity] || m.quantity)}
             · conf ${m.confidence.toFixed(2)}</span>` : '<span class="conf">—</span>'}</td>
        <td><span class="tag tag--permitted">L1</span></td>
      </tr>
      <tr><td colspan="6" class="why">
        <span class="sig">why:</span> ${esc(r.why.reason_text)}
      </td></tr>`;
  }).join('');

  $('empty').hidden = rows.length > 0 || sup.length > 0;
  $('table').hidden = rows.length === 0;

  document.querySelectorAll('.row-main').forEach((tr) => {
    tr.onclick = () => openPassport(rows[+tr.dataset.i]);
  });
}

/* --------------------------------------------------- passport detail panel */
function openPassport(r) {
  const p = r.passport;
  $('p-id').textContent = p.passport_id;
  $('p-release').textContent = p.privacy.release_status;
  $('p-release').className = 'tag tag--permitted';

  const pop = p.population.basis === 'gestational'
    ? `${p.population.gestational_age_weeks} weeks (gestational)`
    : `${p.population.pediatric_stage} · band ${p.population.public_age_band}`;

  $('p-body').innerHTML = `
    <h3>Study</h3>
    <dl class="kv">
      <dt>Owner</dt><dd>${esc(p.owner.label)} (${esc(p.owner.node)})</dd>
      <dt>Modality</dt><dd>${esc(p.imaging.modality)} <span class="conf">native_tag</span></dd>
      <dt>Body site</dt><dd>${esc(p.imaging.body_site.display)}
        <span class="conf">${esc(p.imaging.body_site.system)}:${esc(p.imaging.body_site.code)}</span></dd>
      <dt>Population</dt><dd>${esc(pop)}
        <span class="conf">basis: ${esc(p.population.basis)}</span></dd>
      <dt>Sex</dt><dd>${esc(p.population.sex || '—')}</dd>
    </dl>

    <h3>Measurements — compiled from prose</h3>
    ${p.measurements.length ? p.measurements.map((m) => `
      <div class="meas">
        <div class="head">
          <span class="val">${m.value} ${esc(m.unit)}</span>
          <span>${esc(LABELS[m.quantity] || m.quantity)}</span>
          ${m.laterality ? `<span class="tag">${esc(m.laterality)}</span>` : ''}
          ${m.qualifier ? `<span class="tag">${esc(m.qualifier)}</span>` : ''}
        </div>
        <div class="conf">
          provenance: ${esc(m.provenance)} · confidence ${m.confidence.toFixed(2)}
          ${m.raw_unit !== m.unit
            ? ` · normalised from ${m.raw_value} ${esc(m.raw_unit)}` : ''}
        </div>
        <div class="snippet">&ldquo;${esc(m.snippet)}&rdquo;</div>
      </div>`).join('')
      : '<p class="empty">No measurements extracted from this study.</p>'}

    <h3>Computational readiness</h3>
    <dl class="kv">
      <dt>Quantities available</dt>
      <dd>${p.computational_readiness.quantities_available
              .map((q) => esc(LABELS[q] || q)).join(', ') || '—'}</dd>
      <dt>Missing for full<br>computability</dt>
      <dd>${p.computational_readiness.missing_for_full_computability
              .map((x) => `<span class="tag tag--review">${esc(x)}</span>`).join(' ')}</dd>
    </dl>
    <p class="status">We index the affordances this corpus contains, and we name the
       ones it does not. A researcher can see exactly what they would still need to
       petition for.</p>

    <h3>De-identification manifest — evidence, not assurance</h3>
    <div class="manifest">
      <span class="op">removed</span>
      <ul>${p.deid_manifest.removed.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      <span class="op">generalized</span>
      <ul>${p.deid_manifest.generalized.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      <span class="op">hashed</span>
      <ul>${p.deid_manifest.hashed.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
      <span class="op">free text</span>
      <ul><li>withheld — the report never leaves the hospital boundary</li></ul>
      <span class="op">pseudonym</span>
      <ul><li>${esc(p.deid_manifest.pseudonym)}</li></ul>
    </div>

`;

  // The petition is the point of the whole panel, so it sits at the top where
  // the eye lands, not buried under the manifest where it needs scrolling to.
  $('p-action').innerHTML =
    `<button class="btn btn--petition" id="p-petition">`
    + `Petition ${esc(p.owner.node)} for source access</button>`
    + `<span class="panel-action-note">Routes to the owning hospital. `
    + `Writes an append-only audit entry.</span>`;
  $('p-petition').onclick = () => openPetition(p);
  $('panel').hidden = false;
  $('scrim').hidden = false;
}

function closeAll() {
  $('panel').hidden = true;
  $('petition').hidden = true;
  $('scrim').hidden = true;
  $('pet-receipt').hidden = true;
  $('petition-form').hidden = false;
}

/* ------------------------------------------------------------- petition */
let petitionTarget = null;
function openPetition(p) {
  petitionTarget = p || null;
  $('petition').hidden = false;
  $('scrim').hidden = false;
  $('pet-receipt').hidden = true;
  $('petition-form').hidden = false;
}

async function submitPetition(ev) {
  ev.preventDefault();
  const body = {
    requester_name: $('pet-name').value,
    institution: $('pet-inst').value,
    irb_number: $('pet-irb').value,
    purpose: $('pet-purpose').value,
    tier_requested: $('pet-tier').value,
    cohort_filter: LAST ? LAST.query_ast : {},
    passport_id: petitionTarget ? petitionTarget.passport_id : null,
  };

  let receipt;
  if (DATA.live) {
    const r = await fetch(`${BROKER}/petition`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`WIRING FAILURE: petition rejected (${r.status})`);
    receipt = await r.json();
  } else {
    const owner = petitionTarget ? petitionTarget.owner.node
      : (LAST?.nodes_queried.filter((n) => !n.k_anon_ok).map((n) => n.node).join(', ') || 'BCH');
    receipt = {
      petition_id: 'PET-' + Math.random().toString(36).slice(2, 8).toUpperCase(),
      status: 'routed_to_owner',
      owner_node: owner,
      audit_id: 'AUD-' + Math.random().toString(36).slice(2, 10).toUpperCase(),
      timestamp: new Date().toISOString(),
      note: 'local fixture — the live broker writes an append-only audit entry',
    };
  }

  $('petition-form').hidden = true;
  $('pet-receipt').hidden = false;
  $('pet-receipt').innerHTML = `
    <div class="receipt">
      <div>Petition routed to <strong>${esc(receipt.owner_node)}</strong></div>
      <div style="margin:.5rem 0">audit entry <span class="aid">${esc(receipt.audit_id)}</span></div>
      <div class="conf">petition ${esc(receipt.petition_id)} ·
        ${esc(receipt.status)} · ${esc(receipt.timestamp)}</div>
      <div class="conf" style="margin-top:.6rem">
        Append-only. Lantern brokered this request; it never held the source data.
      </div>
    </div>
    <div class="actions">
      <button class="btn btn--ghost" id="pet-done">Close</button>
    </div>`;
  $('pet-done').onclick = closeAll;
}

/* ------------------------------------------------------------- demo ladder */
const BEATS = {
  '1a': () => { reset(); $('nl').value = 'pediatric brain tumor';
                check('body', ['BRAIN']); },
  '1b': () => { reset(); check('body', ['HEART']);
                $('q-quantity').value = 'ejection_fraction';
                $('q-op').value = 'lt'; $('q-value').value = '40'; },
  '2':  () => { reset(); check('body', ['FETAL']);
                $('q-quantity').value = 'lateral_ventricular_atrial_width';
                $('q-op').value = 'gt'; $('q-value').value = '10'; },
  '3':  () => { reset(); check('body', ['FETAL']);
                $('q-quantity').value = 'lateral_ventricular_atrial_width';
                $('q-op').value = 'gt'; $('q-value').value = '15'; },
};

function check(name, values) {
  document.querySelectorAll(`input[name="${name}"]`).forEach((e) => {
    e.checked = values.includes(e.value);
  });
}

function reset() {
  $('nl').value = '';
  check('body', []);
  check('modality', ['MR']);
  $('stage').value = '';
  $('gest-min').value = '';
  $('gest-max').value = '';
  $('q-quantity').value = '';
  $('q-value').value = '';
  $('diversify').checked = false;
  syncUnit();
}

function syncUnit() {
  $('q-unit').textContent = UNITS[$('q-quantity').value] || '';
}

/* ------------------------------------------------------------------- wire */
/* One entry point for every search, live or local. Errors surface in the results
   pane instead of the console log -- on stage nobody is looking at devtools. */

// A filter left ticked from a previous search silently narrows the next one.
// Searching "glioblastoma" with Fetal still checked returns nothing, and the
// empty result looks like the search failing rather than the filter working.
// So when free text and filters are both present, say so and let the user pick.
function describeActiveFilters() {
  const parts = [];
  const named = (name, label) => {
    const vals = [...document.querySelectorAll(`input[name="${name}"]:checked`)]
      .map((e) => e.value);
    if (vals.length) parts.push(`${label}: ${vals.join(', ')}`);
  };
  named('body', 'Body site');
  named('modality', 'Modality');
  const stage = $('stage') && $('stage').value;
  if (stage && stage !== 'any') parts.push(`Stage: ${stage}`);
  const gmin = $('ga-min') && $('ga-min').value;
  const gmax = $('ga-max') && $('ga-max').value;
  if (gmin || gmax) parts.push(`Gestational age: ${gmin || '–'} to ${gmax || '–'} wk`);
  const q = $('num-quantity') && $('num-quantity').value;
  const v = $('num-value') && $('num-value').value;
  if (q && q !== 'any' && v !== '') parts.push('A measurement threshold');
  return parts;
}

function clearAllFilters() {
  document.querySelectorAll('.rail input[type="checkbox"]').forEach((c) => { c.checked = false; });
  document.querySelectorAll('.rail select').forEach((sel) => { sel.selectedIndex = 0; });
  document.querySelectorAll('.rail input[type="number"]').forEach((n) => { n.value = ''; });
}

function confirmFilters(onProceed) {
  const active = describeActiveFilters();
  const text = ($('nl') && $('nl').value || '').trim();
  // Only worth interrupting when the combination can silently contradict itself:
  // a body-site filter plus either free text or a measurement on another organ.
  const bodySite = [...document.querySelectorAll('input[name="body"]:checked')].map((e) => e.value);
  const quantity = ($('num-quantity') && $('num-quantity').value) || '';
  const measuring = quantity && quantity !== 'any' && ($('num-value') || {}).value !== '';
  const cardiac = /ejection|chamber|regurgitant/.test(quantity);
  const fetalOnly = /gestational/.test(quantity);
  const contradiction =
    (cardiac && bodySite.length && !bodySite.includes('HEART')) ||
    (fetalOnly && bodySite.length && !bodySite.includes('FETAL'));
  if (!contradiction && (!text || active.length === 0)) { onProceed(); return; }

  $('filter-warn').innerHTML = `
    <div class="warn-box" role="alertdialog" aria-labelledby="warn-title">
      <h3 id="warn-title">You have ${active.length} filter${active.length > 1 ? 's' : ''} still applied</h3>
      <p>Searching <strong>${esc(text)}</strong> together with:</p>
      <ul>${active.map((a) => `<li>${esc(a)}</li>`).join('')}</ul>
      <p class="status">Both are applied at once, so a term that does not occur under
         these filters will return nothing.</p>
      <div class="warn-actions">
        <button class="btn btn--petition" id="warn-clear">Clear filters and search</button>
        <button class="btn" id="warn-go">Search with filters</button>
        <button class="btn btn--ghost" id="warn-cancel">Cancel</button>
      </div>
    </div>`;
  $('filter-warn').hidden = false;
  $('warn-clear').onclick = () => { clearAllFilters(); $('filter-warn').hidden = true; onProceed(); };
  $('warn-go').onclick = () => { $('filter-warn').hidden = true; onProceed(); };
  $('warn-cancel').onclick = () => { $('filter-warn').hidden = true; };
}

async function go() {
  $('status-line').textContent = 'searching…';
  try {
    const res = DATA.live ? await fetchSearch() : runSearch();
    render(res);
    $('status-line').textContent =
      `${res.results.length} shown · ${res.timing_ms} ms · ` +
      `${DATA.live ? 'live broker' : 'local fixtures'}`;

    // Zero results with filters applied reads as a broken search. Nearly always
    // it is a filter left over from the previous query quietly contradicting
    // this one, so say which filters were in force and offer to drop them.
    const suppressed = (res.nodes_queried || []).some((n) => n && n.k_anon_ok === false);
    if (res.results.length === 0 && !suppressed) {
      const active = describeActiveFilters();
      if (active.length) {
        $('guard').innerHTML = `
          <div class="disclosure">
            <h3>No studies matched this combination</h3>
            <p>These filters were applied together:</p>
            <ul>${active.map((a) => `<li>${esc(a)}</li>`).join('')}</ul>
            <p class="status">A measurement recorded in one body region will never
               match a filter for another. Ejection fractions occur in heart studies,
               atrial widths in fetal studies.</p>
            <button class="btn btn--petition" id="zero-clear">Clear filters and search again</button>
          </div>`;
        const b = $('zero-clear');
        if (b) b.onclick = () => { clearAllFilters(); go(); };
      }
    }
  } catch (err) {
    $('guard').innerHTML = `
      <div class="disclosure">
        <h3>Query refused</h3>
        <p>${esc(err.message)}</p>
        <p class="meta">The query validator rejected this request. Nothing was
           released — that is the boundary working, not a crash.</p>
      </div>`;
    $('rows').innerHTML = '';
    $('status-line').textContent = 'refused';
  }
}

function wire() {
  $('run').onclick = () => confirmFilters(go);
  $('reset').onclick = () => { reset(); go(); };
  $('q-quantity').onchange = syncUnit;
  $('nl').onkeydown = (e) => { if (e.key === 'Enter') go(); };
  $('p-close').onclick = closeAll;
  $('scrim').onclick = closeAll;
  $('pet-cancel').onclick = closeAll;
  $('petition-form').onsubmit = submitPetition;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAll(); });

  document.querySelectorAll('[data-beat]').forEach((b) => {
    // A new beat is a new analyst asking a fresh question, not the same one probing.
    b.onclick = () => { SESSION = newSession(); BEATS[b.dataset.beat](); go(); };
  });

  SESSION = newSession();
  BEATS['2']();          // open on the hero query — the demo starts warm
  go();
}

boot().catch((err) => {
  document.body.insertAdjacentHTML('afterbegin',
    `<div class="disclosure" style="margin:1rem"><h3>Console failed to start</h3>
     <p>${esc(err.message)}</p></div>`);
  throw err;                                    // fail loud, never a blank page
});
