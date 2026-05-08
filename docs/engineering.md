# Engineering

How this project is built, not what it builds.

A single person — wearing product, design, frontend, backend, ML, infra,
and research hats — shipped Subprime in a few weeks of evenings: a live
production advisor, a 1,974-plan research harness, two stages of
fine-tuning, and a 3-page paper. The leverage came from a small, old
toolkit applied with discipline. None of it is novel. All of it
compounds.

## Tracer bullet first

Milestone M0 was one end-to-end run on a single persona: profile → plan
→ APS judge → PQS judge → JSON on disk → Rich-printed analysis. No web,
no DuckDB, no real fund universe — just the architecture's load-bearing
seam, proving every layer can talk to every other layer. Everything
since has been *thickening* that seam.

In this repo: **12 commits on day 1** (2026-04-08, `b8b66c7..b023ab2`).
By the end of it: core models, mfdata.in client, advisor, judges,
experiments, CLI, ADRs, and integration tests *verifying full module
wiring*. The architecture document came later (`1e4e67e`) — written
once the design had survived contact with reality.

The cost of getting this wrong is enormous. A weak tracer bullet
discovers integration problems at month 3 instead of week 1, and by then
you have three months of code to refactor instead of three days. **Build
the spine first; flesh it out later.**

## Hypothesis-driven iteration

Each major effort has a single falsifiable claim driving it.

| Hypothesis | Test | Result | Landmark |
|---|---|---|---|
| A one-line system-prompt hook can shift APS without moving PQS. | 5 models × 3 conditions × 25 personas. | Confirmed (Cohen's *d* up to 1.18). | Apr 18 (`d4a0e44` adds dose-response) |
| The same shift is inducible at the weight level. | LoRA FT Qwen3-14B on 80 plans/variant, eval with neutral prompt. | Confirmed (+0.365 APS). | PR #16 (`4da7ef3`, 2026-05-07) |
| Bias capacity is set by training-set size. | Sweep 50 / 200 / 600 plans with a clean Sonnet teacher. | Saturates by N=200; teacher quality matters as much as N. | PR #17 (`e285854`, 2026-05-07) |
| A 1.7B model can match MiMo Flash PQS post-FT. | Train + eval cell on Qwen3-1.7B. | Refuted (loss plateaus 0.20 above 14B floor). Negative result; documented; moved on. | Branch `distill-paused` (`58603cd`) |

A negative result is a result. The fourth row above paused after one
cell instead of grinding through three more.

## Mini-waterfalls, not megaplans

When the human is doing the work, big up-front plans are reasonable —
the planner and the executor share a brain. When an AI coding agent is
doing the work, big plans are a disaster. The agent's coherence over
long tool-call chains is brittle; the human's ability to verify long
agent outputs is worse. By the time you notice the agent went sideways
on step 4, it's also done steps 5–10 with the same wrong assumption.

The pattern that works:

1. State the next ~30-min increment of work.
2. Agent executes it (writes, tests, commits).
3. Human verifies the diff and the running state.
4. Decide what's next based on what the diff actually did, not what was
   planned three increments ago.

This is XP's "ten-minute build" idea pulled forward: every short
increment ends in something that runs and is reviewable. Plans longer
than the human's review-budget are anti-patterns. Push the planning
cost into the loop, not before it.

The corollary is **don't delegate understanding**. "Agent, based on the
findings, fix the bug" hands the synthesis step to the agent — exactly
the step the human is supposed to be doing. Synthesise first; brief the
agent on the specific change; review.

What this looks like at saturation: **2026-04-19 saw 95 commits** —
the day the HTMX prototype was rewritten as a Vite + React + TanStack
Query SPA (`89b4275`), the design system landed (`e7bbf65`), the SEBI
modal shipped (`3397f57`), Playwright e2e tests were rewritten for the
SPA (`dccf1a0`), the cheat-code persona unlock went in (`66c3622`),
the Mastercard-priceless README rewrite happened (`81969ae`), and the
demo MP4s were re-recorded against the new SPA (`a11e55d`). One
person; ~30-min increments; each commit reviewed before the next was
queued.

## Tests, layered

| Layer | Where | What it catches |
|---|---|---|
| Unit | `product/tests/test_*.py` (~500) | Logic, data contracts, prompt assembly |
| Functional / integration | Same dir, marked `@pytest.mark.integration` | Cross-module flows; agent + tools; judge round-trips |
| API smoke (live) | `product/tests/test_smoke_live.py` | Hits the deployed instance with real LLM calls; gated by `SUBPRIME_SMOKE_LLM` |
| Browser (live) | `product/tests/test_browser_live.py` | Playwright against the live SPA; verifies routing, OTP cheat, persona bank |
| Pre-commit | `pre-commit-config.yaml` | Ruff lint + format + fast subset of pytest |
| CI | `.github/workflows/` | Full pytest, lint, frontend build, security scans |

Roughly 600 tests; almost all are deterministic and run in < 60s. The
slow ones (live LLM, live browser) are gated behind environment
variables so the inner loop stays fast.

The principle from a memory line: *tests should let me iterate fast on
the product*. Mock external APIs, keep internal flows real, never test
implementation details.

## Full automation, no manual steps

Everything from corpus generation to model deployment to experiment
sweeps runs unattended. Concretely:

- **Synthetic teacher corpus.** `subprime ft synth-corpus` submits an
  Anthropic batch, polls until done, parses results, writes JSONL.
  Zero clicks.
- **Fine-tuning.** `subprime ft train` uploads dataset, submits LoRA
  job, polls events, persists `artifacts.json` (resumable: a re-run
  with an existing manifest skips the FT submission entirely).
- **Endpoint lifecycle.** `provider.create_endpoint(...)` →
  `wait_for_endpoint_ready(...)` → call → `delete_endpoint()` in
  `finally`. Plus signal handlers in long-running scripts so a Ctrl-C
  doesn't leak a $4/hour endpoint. (Lesson learned the hard way during
  the ablation run, when a `pkill` orphaned three endpoints; commit
  trail in the orchestrator follows.)
- **Ablation orchestration.** `product/scripts/ablation_run.py` runs
  the full 6-cell sweep breadth-first (so any stop point yields a
  complete row) and splits inference / scoring across passes so the
  endpoint is torn down before the slower judge sweep.
- **Deploys.** `scripts/blue-green-deploy.sh --auto-promote` builds,
  starts the new colour on a separate port, smokes it, flips the Caddy
  active-color file, gives the old colour a graceful drain window,
  rolls back on failure. DORA metrics emitted via
  `scripts/dora_emit.py`.
- **Cleanup.** A background scrubber sweeps `/tmp/subprime-*.pdf` every
  5 min as a second line of defence after the per-request `delete=True`
  tempfiles.

Manual intervention is reserved for things that genuinely need taste —
prompt copy, persona bank curation, this very page. Everything
mechanical is in code.

## Trunk-based + blue/green

`main` is always deployable. Branches exist only for parking
work-in-progress that can't be on main yet (`distill-paused`); they're
the exception, not the rule. Squash-merge to keep the log linear.

Deploys are blue/green via `scripts/blue-green-deploy.sh`, with smoke
gates and an active-color file at `/etc/caddy/active-finadvisor.caddy`.
Rollback is a single command flipping the file back. No staging
environment; the smoke gate against the new colour pre-flip is the
staging environment.

For a one-person operation this is the right balance: *trunk-based*
because the cost of a long-running branch is overhead the soloist can't
absorb; *blue/green* because the cost of a bad deploy that takes the
service down at 3 AM is much higher than the cost of running two
copies for 10 minutes.

## Timeline — how it actually went

| Phase | Dates | What landed | Key commits |
|---|---|---|---|
| **Tracer bullet** | Apr 8 (1 day, 12 commits) | Empty repo → end-to-end advisor + judges + experiment runner + CLI + 7 ADRs + integration tests verifying every module wiring. | `b8b66c7`..`b023ab2` |
| **Interactive advisor** | Apr 9–10 | Three-phase CLI flow (profile → strategy → plan), conversation capture, Gradio web UI, Docker. | `b2579a8`, `610ac16`, `8d8f622` |
| **RAG data layer (M2)** | Apr 11 | Replaced live mfdata.in tool calls with a DuckDB store rebuilt from the InertExpert2911/Mutual_Fund_Data GitHub dataset; curated three-tier universe injected into the system prompt. | `71cb5d9`, `88e0e96`, `9939ae8` |
| **Stage 1 experiments** | Apr 12–18 | Persona bank growth, dose-response conditions (7-step intensity sweep), per-run usage + elapsed timing, multiple advisor models (Together, Anthropic, Bedrock, Groq, OpenRouter, AI Gateway). | `d4a0e44`, `f42fabc`, `8ff802c` |
| **React rewrite + design system** | Apr 18–19 | Single biggest day: HTMX → Vite + React + TanStack Query + ECharts (`89b4275`); new design system, dark mode, mobile (`e7bbf65`); SEBI modal, OTP cheat, async plan + confetti, Playwright e2e against the deployed SPA. **95 commits in 24 hours.** | `0a16004`, `89b4275`, `dccf1a0`, `e7bbf65` |
| **Production hardening** | Apr 21–24 | Blue-green deploy with HyperDX health-check + DORA event emission (`f150116`); SSE plan stream replaces /plan/status polling (`51fe353`, `6e41bb1`); Resend/SES email backends; CAS / CIBIL / AIS PDF parsers; GrowthBook feature flags Postgres-backed; per-tier feature gating. | `f150116`, `51fe353`, `f93da9a`, `7062187` |
| **Stage 2 — bias in the weights** | May 7 (PR #16) | Harvested 80 Lynch + 80 Bogle plans from Stage 1, LoRA fine-tune of Qwen3-14B on Together AI, neutral-prompt evaluation reproducing the bias purely at the weight level. ~$8 spend. | `4da7ef3` |
| **Stage 2 ablation** | May 7 (PR #17) | Synthetic Sonnet teacher pipeline (Anthropic Batch + tool-use forcing); 720 fresh personas; six FT cells across N ∈ {50, 200, 600} × {Lynch, Bogle}; saturation curve. ~$10 spend. | `e285854`, `c5bdc0b`, `0c52e0d` |
| **Distillation pivot (paused)** | May 7 | Tried Qwen3-4B and Qwen3-1.7B distillation. 4B trained but Together has no dedicated-endpoint hardware; 1.7B trained but rejected at the gateway. Loss-curve evidence: 4B can match 14B's loss floor; 1.7B is genuinely capacity-limited. Negative result, documented, paused. | Branch `distill-paused` (`58603cd`) |
| **Wrap** | May 7–8 | Reports 04 + 05 (Stage 2 + ablation), consolidated 3-page PDF, video re-record with public-domain BGM (Für Elise + Bach Toccata BWV 565), READMEs + design docs trimmed and tightened. | `e285854`, `6152a0a`, `8e15342`, `3b0250c` |

30 days. 320 commits. ~10 commits/day average; the median day was probably
6, the busiest 95. One person.

## What this is, in older words

The pattern of *short increments + automated build + automated tests +
trunk-based + small batches + customer-on-team* was the original spirit
of Extreme Programming, before "agile" got assimilated into ceremonies.
Most of the practices Beck argued for in 1999 only become *more*
valuable when one of the developers is an AI agent: the agent is a
near-perfect pair-programmer for the parts of pair programming that
matter (someone watching, the second pair of eyes, the typing-while-thinking
partner) and a useless one for the parts that don't (the social pressure
to keep working). TDD compounds because tests are the agent's contract
with the codebase.

What's *new* with agent-assisted coding is the absence of context-switch
cost. A solo human switching from "design the data model" to "write
the API" to "tune the SQL" to "rewrite the prompt" pays a coherence tax
each time. With an agent absorbing each subtask, the human stays in
arbitration mode the whole session — *which decision next?* — and the
agent does the typing.

## How a single person ships product + research + infra

It's not heroics. It's:

1. A tracer bullet that proves the architecture early, so refactors are
   cheap.
2. Tests that absorb the cost of regressions, so each new feature
   doesn't have to re-verify the world.
3. Mini-waterfalls so the human's review budget is the unit of work, not
   the project.
4. Hypothesis-driven so the next chunk of work always answers something
   you didn't already know.
5. Automation everywhere, so the marginal cost of one more experiment is
   minutes, not hours.
6. Trunk + blue/green so deploys are routine, not events.
7. An agent doing the typing and the boilerplate, leaving the human in
   the seat that needs taste.

Pick any three. You can ship a research-grade product with a small team.
Pick all seven, you can ship one alone.

## What this isn't

- **Vibe coding.** Tests, types, and reviews are the constraints that
  let agent-assisted work scale. Without them you ship plausible-looking
  garbage at unprecedented speed.
- **Big-design-up-front.** The architecture record (`docs/architecture.md`)
  was written *after* the tracer bullet, codifying what survived contact
  with reality. ADRs (`docs/adr/`) record decisions when they're made,
  not before.
- **Process for its own sake.** No standup, no retro, no sprint planning,
  no story points. The discipline is in the *artefacts* (tests, ADRs,
  blue/green, automation), not the meetings.
