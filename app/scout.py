"""Scout: a narrator that is structurally incapable of leaking a record.

Scout writes a plain-language summary of a cohort and points at published
literature. It is deliberately not a chatbot and it is not in the search path.

The design claim, and the whole reason this is safe to ship in a privacy tool:

    Scout receives a whitelist of already-disclosed aggregates. Not a passport,
    not a snippet, not a study identifier, not an age, not a sex, and never a
    suppressed hospital's count. It cannot leak a record because it is never
    given one.

That whitelist is built here, positively, field by field. It is not a passport
with sensitive keys filtered out, because a filter is a list of things someone
remembered to remove, and the next field someone adds to the passport would sail
straight through it. `build_payload` can only emit what it explicitly constructs.

The model runs locally through Ollama, so nothing leaves the machine. When it is
unavailable the deterministic summary takes over and the feature behaves
identically in shape. That fallback is not an error state; it is the other path.
"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
CACHE = REPO / "data" / "literature_cache.json"

OLLAMA = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = "granite4:micro"
TIMEOUT_S = 45.0

SYSTEM = (
    "You summarise medical imaging cohort statistics for a research index. "
    "Use ONLY the numbers in the user's JSON. Never invent a value, a finding, "
    "a diagnosis, or a hospital. Never describe an individual patient. "
    "Do not speculate about clinical significance. "
    "Write exactly three sentences of plain prose. No bullet points, no headings, "
    "no preamble such as 'Here is a summary'. Report what the cohort contains."
)


def build_payload(query: str, per_node: list[dict[str, Any]],
                  stats: list[dict[str, Any]], concepts: list[str]) -> dict[str, Any]:
    """Construct the ONLY thing Scout is allowed to see.

    Positive construction, never filtering. A hospital that is withholding
    contributes its withheld status and nothing else, so a suppressed count
    cannot reach the model even as a number it was told to ignore.
    """
    nodes = []
    for n in per_node or []:
        if not isinstance(n, dict):
            continue
        withheld = n.get("k_anon_ok") is False
        entry: dict[str, Any] = {"hospital": str(n.get("label") or n.get("node") or "")}
        if withheld:
            entry["status"] = "withheld under the disclosure threshold"
        else:
            count = n.get("records_returned")
            entry["studies"] = int(count) if isinstance(count, int) else 0
        nodes.append(entry)

    measures = []
    for s in stats or []:
        if not isinstance(s, dict):
            continue
        measures.append({
            "quantity": str(s.get("quantity", "")).replace("_", " "),
            "n": s.get("n"),
            "mean": s.get("mean"),
            "median": s.get("median"),
            "min": s.get("min"),
            "max": s.get("max"),
            "unit": s.get("unit", ""),
        })

    return {
        "query": str(query or "")[:200],
        "hospitals": nodes,
        "measurements": measures,
        "clinical_concepts": [str(c) for c in (concepts or [])][:8],
        "note": "Counts reflect records released under disclosure policy only.",
    }


def deterministic_brief(payload: dict[str, Any]) -> str:
    """The summary when the model is unavailable. Same numbers, fewer adjectives."""
    shown = [n for n in payload["hospitals"] if "studies" in n]
    held = [n for n in payload["hospitals"] if "status" in n]
    total = sum(n["studies"] for n in shown)

    where = ", ".join(f"{n['hospital']} {n['studies']}" for n in shown) or "no hospital"
    first = f"This cohort returned {total} studies across {len(shown)} hospitals ({where})."

    if held:
        names = ", ".join(n["hospital"] for n in held)
        second = (f"{names} withheld records because the matching group fell below the "
                  f"disclosure threshold, so only a count band was released.")
    elif payload["measurements"]:
        m = payload["measurements"][0]
        second = (f"The dominant measurement is {m['quantity']}, with {m['n']} values "
                  f"ranging {m['min']} to {m['max']} {m['unit']} and a median of "
                  f"{m['median']} {m['unit']}.")
    else:
        second = "No quantitative measurements were extracted for this cohort."

    third = ("Every figure here comes from values compiled inside the hospital boundary; "
             "no report text and no images were released.")
    return " ".join([first, second, third])


def model_brief(payload: dict[str, Any]) -> tuple[str, str]:
    """Ask the local model. Returns (text, source). Never raises."""
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            data = json.loads(r.read())
        text = (data["choices"][0]["message"]["content"] or "").strip()
        if len(text) < 40:
            return deterministic_brief(payload), "deterministic"
        return text, f"local model ({MODEL})"
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        # A narrator being unavailable must never take the product down.
        return deterministic_brief(payload), "deterministic"


def literature(concepts: list[str], limit: int = 4) -> list[dict[str, Any]]:
    """Published work on these concepts, from the pre-fetched cache.

    Cache-only on purpose: a demo should not depend on venue wifi, and only a
    concept label is ever involved, never anything patient-derived.
    """
    if not CACHE.exists():
        return []
    try:
        cached = json.loads(CACHE.read_text(encoding="utf-8")).get("concepts", {})
    except (ValueError, OSError):
        return []

    wanted = [c.casefold() for c in (concepts or [])]
    for key, papers in cached.items():
        k = key.casefold()
        if any(k in w or w in k for w in wanted):
            return papers[:limit]
    return []
