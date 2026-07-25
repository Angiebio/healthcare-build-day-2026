# Lantern honest delta: keyword search vs. compiled facts

| Intent | Node | Extractor-derived truth | Keyword hits | Baseline recall | Baseline precision | What it means |
|---|---:|---:|---:|---:|---:|---|
| Reduced EF <40% | BCH | 30 | 191 | 60.0% | 9.4% | Reduced/low language is broad and noisy across cardiac findings; it also misses numeric-only phrasing. |
| Reduced EF <40% | MGH | 53 | 211 | 71.7% | 18.0% | Reduced/low language is broad and noisy across cardiac findings; it also misses numeric-only phrasing. |
| Reduced EF <40% | BWH | 73 | 215 | 71.2% | 24.2% | Reduced/low language is broad and noisy across cardiac findings; it also misses numeric-only phrasing. |
| Fetal atrial width >10 mm | BCH | 87 | 88 | N/A — not expressible | 85.2% | Keywords can find named ventriculomegaly, but cannot execute the >10 mm threshold. |
| Fetal atrial width >10 mm | MGH | 78 | 92 | N/A — not expressible | 76.1% | Keywords can find named ventriculomegaly, but cannot execute the >10 mm threshold. |
| Fetal atrial width >10 mm | BWH | 60 | 75 | N/A — not expressible | 69.3% | Keywords can find named ventriculomegaly, but cannot execute the >10 mm threshold. |
| Severe fetal width >15 mm | BCH | 7 | 29 | N/A — not expressible | 24.1% | The word severe often modifies another finding; keywords cannot order the measured width. |
| Severe fetal width >15 mm | MGH | 6 | 27 | N/A — not expressible | 22.2% | The word severe often modifies another finding; keywords cannot order the measured width. |
| Severe fetal width >15 mm | BWH | 3 | 17 | N/A — not expressible | 17.6% | The word severe often modifies another finding; keywords cannot order the measured width. |
| Pediatric brain tumor + expansion | BCH | 179 | 11 | 6.1% | 100.0% | Literal tumor search is highly precise and simpler; expansion earns recall at the cost of broader related terms. |
| Pediatric brain tumor + expansion | MGH | 0 | 0 | N/A | N/A | Literal tumor search is highly precise and simpler; expansion earns recall at the cost of broader related terms. |
| Pediatric brain tumor + expansion | BWH | 0 | 0 | N/A | N/A | Literal tumor search is highly precise and simpler; expansion earns recall at the cost of broader related terms. |

## Honest finding

Literal keyword search is a strong, cheap precision tool when a report uses the expected words; for pediatric brain tumor it avoids the broader related terms admitted by our curated expansion. Lantern's advantage is not that keywords are bad—it is that keywords cannot execute numeric comparisons already trapped in prose.

## Limitations

- Ground truth is **extractor-derived**, not clinician-adjudicated.
- The challenge corpus is synthetic and may not reproduce real institutional language or prevalence.
- There is no independent annotator set; precision here measures agreement with Lantern's extracted result set.
- Numeric-query recall is reported as **N/A — not expressible**, not zero, because literal search has no numeric comparator.
- The terminology expansion is a small corpus-grounded map, not a production terminology server.

## Reproduce offline

```powershell
C:\Users\ajohn\venvs\hack25\Scripts\python.exe -B evals\delta.py
```
