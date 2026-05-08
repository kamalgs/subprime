---
title: AI-assisted engineering
description: Good engineering is all you need.
---

Subprime is a live mutual-fund advisor at <https://finadvisor.gkamal.online>,
a 1,974-plan research harness covering five advisor models and seven
conditions, two stages of fine-tuning, an ablation across
N ∈ {50, 200, 600}, and a consolidated 3-page paper. One person shipped
all of it in 30 days of evenings. The leverage was AI agents — but not
a swarm of them, and not through any agent-specific scaffolding.

The pattern is older than it looks. Brooks' *surgical team* from 1975
finally has the specialised roles it asked for: an agent does the
typing, the tests, the deploy scripts, the GPU ops, the demo video,
the design tokens, the README rewrites. The human is the surgeon —
holds the model of the system in their head, makes the load-bearing
calls, decides what counts as *good*. **Tony Stark, not the Avengers.**

What holds it together is the most boring kind of engineering. Tracer
bullet on day one. Hypothesis-driven loops, never longer than a single
review-able diff. Standard frameworks the agent has seen ten thousand
projects of. No CLAUDE.md, no plugins, no plan files, nothing
agent-specific that ages out when the next-gen agent ships. Layered
tests. Span-tagged telemetry. Full automation from corpus synthesis to
blue-green deploy. Trunk-based git as the only project-management
tool. No Jira, no standup, no sprint board.

The rest of this document walks through how each piece works, and why
each one was chosen over the obvious alternatives.

---

## The shape of work: spiral, not waterfall

Closer to Boehm's spiral than to anything called "agile" today, and
even closer to Boyd's OODA loop or Deming's PDCA cycle: a loop of
*observe what's running → orient on what matters → decide the smallest
experiment that reduces a real risk → act, review, repeat*. Every loop
ends with something running and reviewable. The next loop's scope is
decided by what this one *actually* did, not what was planned three
loops ago.

This is not the same as "mini-waterfalls". A mini-waterfall is still a
waterfall — plan, execute, verify in fixed order — just on a shorter
clock. It looks safe because the cycle is small, but the failure mode
is the same: planning happens before the most informative event (the
running code) and is therefore working with stale assumptions. The
spiral collapses planning *into* the loop. **Plans that survive past
the diff they were written against are anti-patterns.**

### The anti-pattern: plan ahead, dispatch parallel agents

A common temptation with AI agents: "I have a long backlog. Let me
plan it out, break it into N independent tasks, dispatch N agents in
parallel, harvest their work." This fails for the same reason
big-design-up-front fails for humans, and worse:

- **The plan is stale at step 2.** Each agent's work changes the
  codebase, surfaces new constraints, invalidates assumptions in the
  *other* agents' branches. Their plans were written before any of
  this happened.
- **The agents are offline to each other.** None of them can react to
  what the others discover. A naming choice in agent 1's diff that
  agent 3 needs to know about… doesn't reach agent 3.
- **The human can't keep up.** Reviewing N divergent branches in
  parallel exceeds anyone's context budget. The "saved time" is paid
  back in merge conflicts, integration bugs, and rework.

It looks like parallelism. It's actually fan-out without any fan-in
capacity.

### What works

1. State the smallest experiment that reduces a real risk. (Not
   "implement feature X." Closer to "does the SPA route through the
   new SSE endpoint without breaking the existing test?")
2. Agent executes it — writes, tests, commits.
3. Human reviews the diff and the running state. **Synthesise** what
   it changed, what it revealed, what now smells different.
4. Decide the *next* experiment. Sometimes it's the obvious next step
   in a list. Often the diff revealed a more interesting question.
5. Loop.

The corollary is **don't delegate understanding**. "Agent, based on the
findings, fix the bug" hands the synthesis step to the agent — exactly
the step the human is supposed to be doing. Synthesise first; brief
the agent on the specific change; review.

### What it looks like at saturation

**2026-04-19 saw 95 commits** in 24 hours: HTMX prototype rewritten as
a Vite + React + TanStack Query SPA (`89b4275`), design system
(`e7bbf65`), SEBI modal (`3397f57`), Playwright e2e tests rewritten
for the SPA (`dccf1a0`), cheat-code persona unlock (`66c3622`),
Mastercard-priceless README rewrite (`81969ae`), demo MP4s re-recorded
against the new SPA (`a11e55d`). None of it planned at start of day;
each commit's review revealed the next move. The order *emerged*, and
the order mattered: rewriting tests right after the SPA refactor
caught regressions before the next layer landed. Parallel-dispatch
agents would have written tests against the old API, and the merge
would have been a war.

### A worked example: HTMX → React

The original M3 plan called for a Gradio sandbox. The first web
prototype was HTMX over the FastAPI advisor — *also* a quick,
pragmatic choice. Both worked for a one-screen flow.

What broke them was the *next* spiral, not the current one: staged
plan generation needed Server-Sent Events (a partial plan visible
within 60s, full plan ready by 3 minutes), and the corpus projection
needed an interactive chart. HTMX could fake the SSE with polling;
charts via plain `<canvas>` and hand-rolled JS were a graveyard of
dependency mismatches. The agent flagged the cost; the human called
the rewrite. Apr 19, one day, 95 commits, full SPA.

The lesson isn't "always rewrite" — it's that when the spiral surfaces
a constraint the current foundation can't carry, paying the rewrite
*now* (when one feature's worth of code is on the foundation) is much
cheaper than paying it after three more spirals (when ten features are
on it). A waterfall plan would have shipped HTMX-with-polling; the
spiral keeps the option open to reconsider every loop.

---

## Surgeon plus agents

Brooks, in *The Mythical Man-Month* (1975), proposed the **surgical
team** as the right structure for a software project: one *chief
programmer* — the surgeon — owns the design, makes the load-bearing
calls, and writes the critical sections, supported by a small team of
specialised roles (copilot, language lawyer, toolsmith, tester,
editor, administrator). Brooks' point was that software is better when
authored by a single mind with help, rather than by a committee with
consensus.

AI agents are the closest the industry has come to actually delivering
this. The human is the surgeon: makes the design call, holds the model
of the system, decides what gets cut. The agent fills every supporting
role — copilot for the typing, language lawyer for the API surface,
toolsmith for the deploy scripts, tester for the test suite, editor
for the README. The handoff between roles is zero-overhead because
there's only one human in the room.

Or in a contemporary register: **Tony Stark, not the Avengers.** The
workshop hums because JARVIS is doing the rivets, the wireframes, the
deploy pipeline, the unit tests. Tony's mind is freed to do what only
Tony can do — decide what gets built, what gets cut, what counts as
*good*. The Avengers, by contrast, are six humans negotiating a single
suit by committee while Stark is already flying. Multi-agent fan-out
is closer to the Avengers' decision-making than to Stark's workshop.

### What the agent owned

Not just code. In this project, the agent owned:

- **Code** — all of it. Tests too.
- **Design assets** — the subprime logo SVG (`f3729a1`), the design
  system tokens, the demo-card layouts.
- **Research copy** — the consolidated 3-page PDF, the README rewrites
  (`81969ae`), the ADRs, the engineering doc you're reading now.
- **GPU ops** — Together AI fine-tuning jobs, watching eval loss live,
  killing capacity-limited cells early, tearing down endpoints in
  `finally`. The 1.7B distillation cell was killed mid-flight by an
  agent watching loss > 0.95 at step 1.
- **Video production** — Playwright recording the live SPA, ffmpeg
  compositing intro cards + product slice + music, sourcing
  public-domain BGM (Für Elise + Bach Toccata BWV 565), aligning
  click-timing to the music.
- **Deploys** — see *Full automation*.

### The human's actual role

If the agent does all the above, what's left? Three things, all
indispensable. Real one-line interventions from the project's session
transcripts illustrate each:

**1. Arbitrating taste.** The agent will produce ten plausible
options; picking which one is the project's voice is a human call.

- *"Let us change the name of the personas to indicate a persona...
  Or some fun movie / book character names."* (later: *"South Indian?
  I don't like Sanskrit.. Vijayanagar empire"*)
- *"Should we call it self review instead of refine?"* (naming on a
  load-bearing concept)
- *"Why is benchmark Nifty? Each fund has a different benchmark
  index. Don't we have that data?"*
- *"Bogle says passive, midcap 150 and smallcap 150 are still index
  plans. They are actually correct recommendations. Passive doesn't
  equal to conservative."* (correcting a domain misunderstanding the
  agent had baked into a prompt)

A trivial-seeming intervention can be load-bearing. Naming the
user-facing advisor *Benji* — a casual one-liner — reset the entire
voice of the prompt copy, the SEBI disclosures, the README opening,
the brand of the SPA. The agent was producing serviceable
financial-advisor copy; the human's redirect made it the *project's*
copy. No process produces that. Only a surgeon does.

**2. Unblocking.** External constraints, credentials, infra decisions
sit outside the agent's authority.

- *"Why Together, production is setup to hit OR right?"* (agent had
  been timing the wrong cold-start path)
- *"I think we dropped live calls to mfdata.in. Most of the data is
  scraped from the other mfdata GitHub repository."* (corrected a
  stale architecture claim that had propagated into multiple docs)
- *"Stopped everything. Let us move back to main."* (Together's 1.7B
  endpoint was rejecting all requests; the human called the pause)
- *"Can we add support for passing HF tokens, lambda cloud API keys
  etc.. Keep them gitignored, no credentials pushed to GitHub at any
  cost."*

**3. Recognising creative turns.** The agent will faithfully report
what it sees; whether a result is *load-bearing* — or whether the
project should turn — is a human call.

- *"I don't think the bias affects PQS. If we are hitting 0.80 with
  14B, it is unlikely we will be able to do better with neutral data."*
  (saved a $15–20 corpus run by killing it on a well-formed prior)
- *"Why don't we do the APS, PQS later? Just finish and scale down
  the dedicated endpoint and then do further analysis."*
  (re-architected the ablation pass mid-flight to halve endpoint cost)
- *"Going forward make sure to sequence tasks to ensure minimal
  wasted effort and cost."* (process feedback after a speculative
  spend the agent should have avoided)
- *"Min-waterfall is an anti-pattern that shouldn't be done.. plan too
  far ahead and let multi-agents implement.. needs the iterative /
  spiral development philosophy."* (corrected the framing of *this
  very document*)

The leverage isn't that the agent replaces the developer — it's that
one human's taste, judgement, and creative arbitration now scale
across a team-sized workload, with Brooks' *coherence* benefit intact.

---

## Tracer bullet first

Milestone M0 was one end-to-end run on a single persona: profile →
plan → APS judge → PQS judge → JSON on disk → Rich-printed analysis.
No web, no DuckDB, no real fund universe — just the architecture's
load-bearing seam, proving every layer can talk to every other layer.
Everything since has been *thickening* that seam.

In this repo: **12 commits on day 1** (2026-04-08, `b8b66c7..b023ab2`).
By the end of it: core models, mfdata.in client, advisor, judges,
experiments, CLI, ADRs, and integration tests *verifying full module
wiring*. The architecture document came later (`1e4e67e`) — written
once the design had survived contact with reality.

A weak tracer bullet discovers integration problems at month 3 instead
of week 1, and by then you have three months of code to refactor
instead of three days. **Build the spine first; flesh it out later.**

## Hypothesis-driven iteration

Each major effort has a single falsifiable claim driving it.

| Hypothesis | Test | Result | Landmark |
|---|---|---|---|
| A one-line system-prompt hook can shift APS without moving PQS. | 5 models × 3 conditions × 25 personas. | Confirmed (Cohen's *d* up to 1.18). | Apr 18 (`d4a0e44`) |
| The same shift is inducible at the weight level. | LoRA FT Qwen3-14B on 80 plans/variant, eval with neutral prompt. | Confirmed (+0.365 APS). | PR #16 (`4da7ef3`) |
| Bias capacity is set by training-set size. | Sweep 50 / 200 / 600 plans with a clean Sonnet teacher. | Saturates by N=200; teacher quality matters as much as N. | PR #17 (`e285854`) |
| A 1.7B model can match MiMo Flash PQS post-FT. | Train + eval cell on Qwen3-1.7B. | Refuted (loss plateaus 0.20 above 14B floor). | Branch `distill-paused` (`58603cd`) |

A negative result is a result. The fourth row paused after one cell
instead of grinding through three more.

## Standard tools, not exotic ones

Every framework choice in this project leans toward what's *already
widely used*: FastAPI, PydanticAI, React + Vite + TanStack Query +
Tailwind, DuckDB, Postgres, ffmpeg, Playwright, ruff, pytest, Typer,
Rich, GitHub Actions, Caddy. Boring on purpose.

The conventional argument for boring choices is risk reduction: more
StackOverflow answers, more battle-tested edge cases, easier hiring.
With AI-agent-assisted work there is a much sharper additional reason:
**the agent has seen orders of magnitude more idiomatic React than it
has seen any niche framework.** The same applies down the stack —
more pytest than custom test runners, more standard FastAPI patterns
than bespoke web frameworks, more PEP-8 Python than house dialects.
Picking standard tools means the agent's first guess is usually
right. Picking unusual tools means every tool call carries a tax.

The corollary: *exotic* choices are now an expensive form of
self-expression. They might still be the right call — DuckDB for the
embedded fund universe was an example, ADR 005 explains why — but
they have to *earn* their place against the agent-friction tax.

**Standard ≠ thoughtless.** The agent's first guess at a React
component is usually idiomatic; the agent's first guess at *prompt
copy* is usually generic LLM filler. Domain-specific work (philosophy
prompt hooks, persona descriptions, the Bogle/midcap correction) is
where standard patterns start failing and the human's arbitration
becomes load-bearing again.

## No agent-specific scaffolding

The flip side of "boring tools age well" is: **don't build for the
agent**. This project deliberately does not have:

- A `CLAUDE.md`, `AGENTS.md`, `.agent/` folder, or any other file
  full of project-specific personas, workflows, or magic incantations
  for the agent to read at session start.
- Custom skills, plugins, hooks, or sub-commands the agent depends on
  to do its job.
- "Plan files" or specs the agent generates from a template and ticks
  off step-by-step.
- A multi-agent orchestration manifest, tool-use registry, routing
  rules, or any other agent-only infrastructure.

Just an out-of-the-box coding agent and a natural conversation. The
agent reads code by reading code, understands the project by following
imports, and knows what's been done by reading `git log`. The same
session transcript that shipped this paragraph could have shipped it
through any other coding agent that exists today.

The reasoning is purely defensive: **the coding-agent ecosystem moves
faster than almost any other category of software right now**. A
plugin, skill, or custom workflow that solves an agent-specific
friction this week is junk by next quarter — the friction has moved,
the API has changed, the new model handles it differently. Anything
agent-specific is trying to hit a supersonic target; you end up
holding a closet full of obsolete artefacts instead of a clean
codebase.

A concrete instance: an early plugin tried to file specs and plans
under `docs/superpowers/` (a plugin-namespaced folder). The project
pushed back and kept them in plain `docs/specs/` and `docs/plans/`.
The plugin name is gone; the docs are still there. **Every
agent-namespaced artefact will eventually be gone, while every plain
artefact survives. Build for the second category.**

## Tests, layered

| Layer | Where | What it catches |
|---|---|---|
| Unit | `product/tests/test_*.py` (~500) | Logic, data contracts, prompt assembly |
| Functional / integration | Same dir, marked `@pytest.mark.integration` | Cross-module flows; agent + tools; judge round-trips |
| API smoke (live) | `product/tests/test_smoke_live.py` | Hits the deployed instance with real LLM calls; gated by `SUBPRIME_SMOKE_LLM` |
| Browser (live) | `product/tests/test_browser_live.py` | Playwright against the live SPA |
| Pre-commit | `.pre-commit-config.yaml` | Ruff lint + format + fast subset of pytest |
| CI | `.github/workflows/` | Full pytest, lint, frontend build, security scans |

Roughly 600 tests; almost all deterministic and < 60s. The slow ones
(live LLM, live browser) are gated behind environment variables so the
inner loop stays fast. The principle: *tests should let me iterate
fast on the product*. Mock external APIs, keep internal flows real,
never test implementation details.

## Instrument everything

Every span the production app emits is tagged with
`subprime.session_id` (`subprime/observability/attrs.py`) plus token
usage, elapsed time, advisor and refine model identifiers, cache hit
ratios, and tier. Investigating "why did this session feel slow?" is a
single HyperDX filter: `subprime.session_id = "<id>"` shows the full
timeline (profile submit → strategy → plan stages → judge calls)
without ever opening a debugger.

Every `ExperimentResult` JSON carries the same shape: `elapsed_s`,
`usage.input_tokens`, `usage.output_tokens`, `usage.cache_read_tokens`,
plus the model and condition. Cross-cut analysis is one DuckDB query.

For the agent, this is the difference between debugging from theory
and debugging from data. Most of the spiral's "observe" step lives in
this telemetry; without it, "observe" degrades to "guess".

## Full automation

Manual intervention is reserved for things that genuinely need taste —
prompt copy, persona bank curation, this very page. Everything
mechanical is in code:

- **Synthetic teacher corpus.** `subprime ft synth-corpus` submits an
  Anthropic batch, polls until done, parses results, writes JSONL.
- **Fine-tuning.** `subprime ft train` uploads dataset, submits LoRA
  job, polls events, persists `artifacts.json` (resumable: a re-run
  with an existing manifest skips the FT submission).
- **Endpoint lifecycle.** `provider.create_endpoint(...)` →
  `wait_for_endpoint_ready(...)` → call → `delete_endpoint()` in
  `finally`. Plus signal handlers in long-running scripts so a Ctrl-C
  doesn't leak a $4/hour endpoint. (Lesson learned the hard way: a
  `pkill` orphaned three endpoints during the ablation run.)
- **Ablation orchestration.** `product/scripts/ablation_run.py` runs
  the full 6-cell sweep breadth-first (so any stop point yields a
  complete row) and splits inference / scoring across passes so the
  endpoint is torn down before the slower judge sweep.
- **Deploys.** `scripts/blue-green-deploy.sh --auto-promote` builds,
  starts the new colour on a separate port, smokes it, flips the Caddy
  active-color file, gives the old colour a graceful drain window,
  rolls back on failure. DORA metrics emitted via
  `scripts/dora_emit.py`.
- **Cleanup.** A background scrubber sweeps `/tmp/subprime-*.pdf`
  every 5 min as a second line of defence after `delete=True`
  tempfiles.

## Trunk-based + blue/green

`main` is always deployable. Branches exist only for parking
work-in-progress that can't be on main yet (`distill-paused`); they're
the exception, not the rule. Squash-merge to keep the log linear.

Deploys are blue/green via `scripts/blue-green-deploy.sh`, with smoke
gates and an active-color file at `/etc/caddy/active-finadvisor.caddy`.
Rollback is a single command flipping the file back. No staging
environment; the smoke gate against the new colour pre-flip *is* the
staging environment.

For a one-person operation this is the right balance: *trunk-based*
because the cost of a long-running branch is overhead the soloist
can't absorb; *blue/green* because the cost of a bad deploy that takes
the service down at 3 AM is much higher than the cost of running two
copies for 10 minutes.

## Tooling: just git, no Jira

There is no Jira here. No standup. No sprint board, no story points,
no backlog grooming, no estimation poker, no retro template. Project
management for the soloist on this project is:

- `git log` (what's been done)
- the working tree's open diff (what's in flight)
- branches like `distill-paused` (what's parked)
- ADRs in `docs/adr/` (decisions worth remembering)
- commit messages (the *why* attached to the *what*)

Every artefact is the same thing the code already needs to exist.
Nothing is duplicated into a separate ticketing system that demands
its own state, grooming, permissions model. The tax on changing
direction is zero — there's no ticket to re-scope, no sprint to break,
no epic to update. You just commit.

Tools like Jira don't merely cost time; they cost momentum. They
require declaring intent ahead of doing the work, then defending that
intent against your own better judgement when reality contradicts it
three commits in. For one person doing iterative spiral work, that's
the worst possible mismatch: ceremony optimised for the case the
spiral explicitly refuses.

### When this scales to a team

A professional, multi-person project does need *some* shared
coordination — but the same lightweight, git-adjacent tooling covers
it without the killjoy overhead:

- **GitHub Issues** for "this needs doing" — one per discrete unit,
  closed by a referencing PR. The title is the spec; if an issue
  can't be expressed as one short paragraph it should be split.
- **Pull Requests** for review — short-lived branches, one feature
  per PR, squash-merge into trunk. The PR description is the plan;
  the diff is the implementation; the comments are the conversation.
- **Soft approval** — comments are a conversation, not a gate. The
  author decides what to incorporate. Hard gates only on rare
  load-bearing changes (security, schema, deploy infrastructure).
- **Commit messages and PR comments** as the durable record. The
  intervention quotes earlier in this document came from chat
  transcripts; in a team setting the equivalents would naturally
  surface as PR comments.
- **ADRs** for decisions that outlast a single PR — same pattern as
  solo work, with team review baked into the proposal stage.

The principle: **every coordination artefact pays its way by being a
thing the work needs anyway**. A commit needs a message. A PR needs a
description. An ADR is the form of a decision worth remembering. Jira
tickets, by contrast, are work *about* the work, and they accumulate
faster than the work itself does.

## The older lineage

The pattern of *short increments + automated build + automated tests +
trunk-based + small batches + customer-on-team* was the original
spirit of Extreme Programming, before "agile" got assimilated into
ceremonies. Most of what Beck argued for in 1999 only becomes *more*
valuable when one of the developers is an AI agent: the agent is a
near-perfect pair-programmer for the parts of pair programming that
matter (someone watching, the second pair of eyes, the
typing-while-thinking partner) and a useless one for the parts that
don't (the social pressure to keep working). TDD compounds because
tests are the agent's contract with the codebase.

What's *new* is the absence of context-switch cost. A solo human
switching from "design the data model" to "write the API" to "tune
the SQL" to "rewrite the prompt" pays a coherence tax each time. With
an agent absorbing each subtask, the human stays in arbitration mode
the whole session — *which decision next?* — and the agent does the
typing.

## Timeline — how it actually went

| Phase | Dates | What landed | Key commits |
|---|---|---|---|
| **Tracer bullet** | Apr 8 (1 day, 12 commits) | Empty repo → end-to-end advisor + judges + experiment runner + CLI + 7 ADRs + integration tests verifying every module wiring. | `b8b66c7`..`b023ab2` |
| **Interactive advisor** | Apr 9–10 | Three-phase CLI flow, conversation capture, Gradio web UI, Docker. | `b2579a8`, `610ac16`, `8d8f622` |
| **RAG data layer** | Apr 11 | Replaced live mfdata.in tool calls with a DuckDB store rebuilt from the InertExpert2911 GitHub dataset; curated three-tier universe injected into the system prompt. | `71cb5d9`, `88e0e96`, `9939ae8` |
| **Stage 1 experiments** | Apr 12–18 | Persona bank growth, dose-response (7-step intensity sweep), per-run usage + elapsed timing, multiple advisor models. | `d4a0e44`, `f42fabc`, `8ff802c` |
| **React rewrite + design system** | Apr 18–19 | Single biggest day: HTMX → Vite + React + TanStack Query + ECharts; design system, dark mode; SEBI modal, OTP cheat, async plan, Playwright e2e. **95 commits in 24h.** | `0a16004`, `89b4275`, `dccf1a0`, `e7bbf65` |
| **Production hardening** | Apr 21–24 | Blue-green deploy with HyperDX + DORA emission; SSE plan stream replaces polling; Resend/SES email; CAS / CIBIL / AIS PDF parsers; GrowthBook flags Postgres-backed. | `f150116`, `51fe353`, `f93da9a`, `7062187` |
| **Stage 2 — bias in the weights** | May 7 (PR #16) | LoRA fine-tune of Qwen3-14B on 80 Lynch + 80 Bogle plans, neutral-prompt eval reproduces the bias. ~$8 spend. | `4da7ef3` |
| **Stage 2 ablation** | May 7 (PR #17) | Synthetic Sonnet teacher pipeline (Batch + tool-use forcing); 720 fresh personas; six FT cells, saturation curve. ~$10 spend. | `e285854`, `c5bdc0b`, `0c52e0d` |
| **Distillation pivot (paused)** | May 7 | Qwen3-4B and Qwen3-1.7B distillation. Both blocked on Together infra; loss-curve evidence shows 4B has capacity, 1.7B does not. Negative result, documented, paused. | Branch `distill-paused` (`58603cd`) |
| **Wrap** | May 7–8 | Reports 04 + 05, consolidated 3-page PDF, video re-record with public-domain BGM, READMEs + design docs trimmed and tightened, this engineering doc. | `e285854`, `6152a0a`, `8e15342`, `3b0250c` |

30 days. 320 commits. ~10 commits/day average; the median day was
probably 6, the busiest 95. One person.

## What this isn't

- **Vibe coding.** Tests, types, and reviews are the constraints that
  let agent-assisted work scale. Without them you ship plausible-
  looking garbage at unprecedented speed.
- **Big-design-up-front.** `docs/architecture.md` was written *after*
  the tracer bullet, codifying what survived contact with reality.
  ADRs record decisions when they're made, not before.
- **Process for its own sake.** No standup, no retro, no sprint
  planning, no story points. The discipline is in the *artefacts*
  (tests, ADRs, blue/green, automation), not the meetings.
- **Heroics.** It's a small old toolkit applied with discipline. None
  of it is novel. All of it compounds.
