# Pooja's lane 🎨

**This folder is yours.** Everything in it is safe to change. Nothing outside it is.

## What's here

| File | What it is |
|---|---|
| `lantern.css` | **The shared stylesheet for the entire product.** Content pages *and* the researcher search console import it. Restyle here and the whole site changes |
| `about.html` | The About page — the project's story, written and ready to be made beautiful |
| `how-it-works.html` | The method page, for people who want to check our work |
| `privacy.html` | Privacy & compliance — controls table, and what we deliberately don't claim |

## Your job

The **content is already written and fact-checked** — the numbers in it are real and were measured
against the actual dataset. You don't have to write copy or verify claims (though if something reads
wrong to your regulatory eye, say so immediately — that's exactly the catch we need).

**Your job is to make it beautiful and credible.** Type, spacing, hierarchy, color, rhythm. The CSS
has a starting direction with comments explaining the reasoning; disagree with any of it.

The audience is clinical researchers and hospital privacy officers. It should look like a scientific
instrument, not a startup landing page. Dense, legible, calm. **Data density reads as serious to this
crowd.** Specifically avoid the default AI look: purple-to-indigo gradient hero, big rounded cards on
pastel, centered emoji.

## The one thing that makes your work go furthest

`lantern.css` is imported by the search console too. So when you improve the type scale or the table
styling, **the researcher-facing product gets better as well** — without you touching that code, and
without any risk of collision. That's why the shared stylesheet is in your folder and not somewhere else.

## Rules (same as always)

- Edit only inside `contrib/pooja/`. Never anything outside.
- Client-side only: HTML, CSS, and vanilla JS. No backend, no build step, no npm.
- Any claim, statistic, or regulation on a page must be verified — but everything currently there
  already is. **If you add a new claim, verify it or ask.**
- Commit often, push when a chunk is ready, and announce "pushed!" — Flame merges around 1:30 and 2:40.

## Preview it

Just open the `.html` files directly in a browser. No server needed. Nav links to `/` (the search
console) won't resolve until the backend is up — that's expected, not something you broke.
