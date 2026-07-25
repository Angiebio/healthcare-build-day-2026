/* Drive the REAL console.js matcher headlessly and assert the demo ladder.
 *
 * A passing pytest on the fixtures proves the DATA is right. It does not prove the
 * UI reads that data correctly -- and the thing on the projector is the UI. This
 * loads console.js with a stub DOM, clicks each demo-ladder beat, and checks the
 * per-node numbers the console would actually paint. Wrong filter wiring, a typo in
 * a quantity name, an inverted operator: all of it surfaces here instead of at 3:30.
 *
 * Run: node tools/verify_console.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..');
const staticDir = path.join(repo, 'app', 'static');

const fixtures = JSON.parse(readFileSync(path.join(staticDir, 'fixtures.json'), 'utf8'));

/* ---- the smallest DOM that console.js will accept ---- */
const els = new Map();
function el(id) {
  if (!els.has(id)) {
    els.set(id, {
      id, value: '', checked: false, textContent: '', innerHTML: '', hidden: false,
      className: '', dataset: {}, style: {}, onclick: null, onchange: null,
      onkeydown: null, onsubmit: null,
      insertAdjacentHTML() {}, focus() {},
    });
  }
  return els.get(id);
}
// checkboxes live outside getElementById; querySelectorAll must find them
const boxes = [
  { name: 'body', value: 'FETAL', checked: false },
  { name: 'body', value: 'BRAIN', checked: false },
  { name: 'body', value: 'HEART', checked: false },
  { name: 'modality', value: 'MR', checked: true },
];
const document = {
  getElementById: el,
  querySelectorAll(sel) {
    let m = sel.match(/^input\[name="(\w+)"\]:checked$/);
    if (m) return boxes.filter((b) => b.name === m[1] && b.checked);
    m = sel.match(/^input\[name="(\w+)"\]$/);
    if (m) return boxes.filter((b) => b.name === m[1]);
    return [];
  },
  addEventListener() {},
  body: { insertAdjacentHTML() {} },
};

const ctx = vm.createContext({
  document, performance, console,
  fetch: async () => { throw new Error('offline'); },
  AbortSignal: { timeout: () => undefined },
  Math, Date, JSON, Number, Object, Array, String, Set, Map, isNaN, parseFloat, parseInt,
});

// strip the trailing boot() call -- we drive the module ourselves
let src = readFileSync(path.join(staticDir, 'console.js'), 'utf8');
src = src.replace(/boot\(\)\.catch[\s\S]*$/, '');
// `DATA` is a script-scoped `let`, so assigning ctx.DATA from out here would create
// an unrelated global and leave the module's own binding null. Inject via a setter
// that closes over the real binding.
vm.runInContext(
  src + '\nglobalThis.__api = { runSearch, readFilters, BEATS, reset,' +
        ' setData: (d) => { DATA = d; } };',
  ctx,
);

const api = ctx.__api;
api.setData({ nodes: fixtures.nodes, passports: fixtures.passports, live: false });

/* ---- expectations: CORRECTIONS-v2 NUMBERS LOCK ---- */
const EXPECT = {
  '1b': { name: 'EF < 40%',            nodes: { BCH: 30, MGH: 53, BWH: 73 }, suppress: false },
  '2':  { name: 'atrial width > 10mm', nodes: { BCH: 87, MGH: 78, BWH: 60 }, suppress: false },
  '3':  { name: 'severe > 15mm',       nodes: { BCH: 7,  MGH: 6,  BWH: 3  }, suppress: true  },
};

let failures = 0;
for (const [beat, want] of Object.entries(EXPECT)) {
  api.BEATS[beat]();
  const res = api.runSearch();
  const got = {};
  for (const n of res.nodes_queried) {
    got[n.node] = n.k_anon_ok ? n.count : n.approximate_count;
  }

  if (want.suppress) {
    const allSup = res.nodes_queried.every((n) => !n.k_anon_ok);
    const leaked = res.nodes_queried.filter((n) => 'count' in n);
    const line = `beat ${beat}  ${want.name.padEnd(22)} ${JSON.stringify(got)}`;
    if (allSup && leaked.length === 0) {
      console.log(`  PASS  ${line}  -> all suppressed, no exact counts emitted`);
    } else {
      console.log(`  FAIL  ${line}  -> expected every node suppressed with counts omitted`);
      failures++;
    }
    // the CORRECTION-1b guarantee, checked on the wire and not just in the renderer
    if (leaked.length) {
      console.log(`        LEAK: exact count present on ${leaked.map((n) => n.node).join(',')}`);
    }
  } else {
    const ok = Object.entries(want.nodes).every(([n, v]) => got[n] === v);
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  beat ${beat}  ${want.name.padEnd(22)} ` +
                `${JSON.stringify(got)}${ok ? '' : `  expected ${JSON.stringify(want.nodes)}`}`);
    if (!ok) failures++;
  }
}

/* the ontology beat: expansion must actually fire, or requirement #1 is unmet */
api.BEATS['1a']();
const r1a = api.runSearch();
const fired = r1a.ontology_expansion?.fired || [];
console.log(`  ${fired.includes('tumor') ? 'PASS' : 'FAIL'}  beat 1a  ` +
            `ontology expansion    fired=[${fired}] results=${r1a.results.length}`);
if (!fired.includes('tumor')) failures++;

console.log(failures ? `\n${failures} FAILURE(S)` : '\nconsole ladder verified');
process.exit(failures ? 1 : 0);
