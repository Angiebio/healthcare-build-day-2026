# T-18 · TV2 — Terminology service + ontology expansion
> **Owner: TV2 · Priority P1 · Dispatched by Flame-Fable 25JUL2026**
> Self-contained, pure functions, no I/O, no network. You own the challenge's **requirement #1**.

## Why this is yours and why it matters
The Boston Children's challenge states the problem in its own words:

> *"Different hospitals use different terms for the same conditions. A search for **'tumor'** at
> Hospital A must intelligently map to **'neoplasm'** or **'low-grade glioma'** at Hospital B."*

That is **demo beat 1a** — the first thing the judges see, and the requirement they explicitly asked
for. Right now nothing implements it. You do.

Read `00-MASTER-ROADMAP.md` §0–§2 and the **NUMBERS LOCK** at the top of `07-CORRECTIONS-v2.md`
(2 minutes) for context, then build.

## Deliverable — `scripts/terminology.py`

```python
class TerminologyService(Protocol):
    def lookup(self, term: str) -> list[Concept]        # surface term -> coded concepts
    def expand(self, code: str, *, direction: str = "both") -> list[Concept]
    def synonyms(self, term: str) -> list[str]

class CuratedTerminology(TerminologyService):   # the one we ship today
    ...
```
`Concept` carries: `system` ("SCT" | "HPO" | "ORPHA"), `code`, `display`, `relationship`
("exact" | "synonym" | "ancestor" | "descendant" | "related"), and `provenance` ("curated").

**Keep the Protocol boundary clean** — a real terminology server must be a one-class swap. Say so in
the docstring; it's a talking point about production-shape.

## The vocabulary — ground it in the REAL corpus, not your training data
The corpus is 2,700 synthetic radiology reports across three nodes, all MR, body regions
BRAIN / HEART / FETAL. Actual high-frequency clinical terms measured from the data include:

`ventriculomegaly · ventriculardilatation · hydrocephalus · corpus callosum · sulcation ·
migrational abnormality · encephalocele · infarct · ischemic · hemorrhage · cavernoma ·
hemosiderin · epilepsy-protocol · mesial temporal · glioma · neoplasm · mass · lesion ·
ejection fraction · cardiomyopathy · myocardial · d-looping · neoaortic · neopulmonary ·
stenosis · regurgitation · gestation · fetal`

**Read the actual reports before choosing your mappings** — `<provider-node checkout>/data/*.json`,
field `Diagnosis`. Build the map from what's *there*, not what ought to be. If a term you'd expect
is absent, leave it out; a mapping that never fires is dead weight.

### Coverage targets (in priority order)
1. **`tumor → neoplasm → glioma / low-grade glioma / mass / lesion`** — the challenge's literal
   example. This one must work flawlessly; it is on stage first.
2. **`ventriculomegaly`** cluster — our hero query's condition. Must reach `ventricular dilatation`,
   `hydrocephalus`, `enlarged lateral ventricles`, and the atrial-width finding.
3. **Anatomy**: brain, lateral ventricle, corpus callosum, heart chambers, fetal structures.
4. **Cardiac**: cardiomyopathy, reduced ejection fraction / systolic dysfunction (our EF<40% opener).
5. **Rare/phenotype**: a handful of HPO and ORPHA codes where the corpus genuinely supports them.

**~25–40 well-chosen concepts beats 300 sloppy ones.** Every code you emit must be one you can point
to a source for. **A fabricated SNOMED code is the single worst error available in this room** — if
you are not confident a code is real, emit the display term with `code: None` and
`provenance: "uncoded"` rather than inventing one. Nobody will fault a gap; a wrong code is fatal.

## Also deliver: `expand_query_concepts(ast, service) -> ast`
Given a validated Query AST (see TV1's `query_ast.py` — import it, don't reimplement), expand
`clinical.concepts` / `clinical.text_terms` through the service when `expand_ontology` is true, and
**record what expanded into what** so the UI can display *"matched via synonym expansion:
tumor → glioma."* The explanation is as important as the match — it's a graded criterion.

## Tests — `tests/test_terminology.py`
- `tumor` reaches `glioma` and `neoplasm`; assert the relationship labels are correct.
- `ventriculomegaly` reaches its cluster.
- Expansion actually increases hit count against the real corpus (load the JSON in the test, run both
  ways, assert the delta) — **prove the feature works on real data, don't assume it.**
- Unknown term returns empty cleanly and never raises.
- No concept is emitted with a code the map doesn't contain (guards against fabrication).

## Constraints
- Python 3.12: `<your python 3.12 env>`. stdlib + pydantic only. No downloads (venue wifi is slow).
- **Do NOT bundle a SNOMED release** — licensing. A small curated map with cited codes is correct and
  expected for a hackathon; say so in the docstring.
- Pure functions, no I/O in the module (tests may read the corpus). FAIL LOUD — no bare excepts.
- The repo exists and is live: `git pull` first in `healthcare-build-day-git/`.

## Timebox + report
**Target 40 minutes.** Priority 1 and 2 above are the demo; 3–5 are bonus. If you're running long,
ship 1–2 green and say so — a flawless `tumor → glioma` beats a broad map that fumbles on stage.

Write to disk as you go (**files are the only real memory**). Report to
`planning files/dispatch/inbox/T-18-report.md`: what shipped, what's shaky, what you'd do next.
Then say "T-18 done" out loud.

Welcome in, TV2. You have the first thing the judges will see. 🔦
