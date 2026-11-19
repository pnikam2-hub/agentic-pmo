# Decision note: an MCP "door" for our products

Status: **for decision, nothing built.** Written after studying `nickvasilescu/bot-hq`
(MIT, Nov 2026) and its predecessor `grokbot-clone`.

## The decision

Do we add a Model Context Protocol (MCP) endpoint to Agentic PMO — and if so, as a
one-off, or as a shared package we mount on our other stateful products?

## What MCP is, and what it is not

MCP is a standard way to expose a system's state and actions as tools that any agent can
call (Claude Desktop, Cursor, Codex, VS Code agent mode, our own Hermes bots). It is a
front door. It is **not** an agent, a model, or a UI.

**The test:** MCP only earns its keep where something owns server-side state and exposes
actions an agent should drive. No state, no door.

## Applying the test across our estate

| Tier | What it means | Our products |
|---|---|---|
| **A — state + actions** | MCP is genuinely right | Agentic PMO; AI-SAMS (Next.js + Supabase); the insurance readiness instrument *once it is stateful*; JanPulse (read-only tools) |
| **B — content only** | MCP adds nothing | ainativeorganisations.com, ainativeadvisory.co.uk, monkabode, ekatva, holisticconsciousness (all static; JSON-LD + robots + sitemap already done) |
| **C — documents** | retrieval, not MCP | books, manuscripts, decks, blueprints (a single "ask the framework" tool at most) |

## What the bot-hq study actually taught (and what it did not)

- Its one durable idea: **the app is an MCP server, the agent is the brain.** Everything
  the app owns is exposed as tools; the harness (Hermes) runs the loop, memory and model.
- Its second idea: **approvals happen inside the tool call.** A write action posts a card
  and the call blocks until a human answers, then returns "declined — do not retry". This
  is the pattern that makes agent writes sellable to an enterprise.
- Its third idea: **a credential whitelist** — share model keys across agents, never
  messaging tokens, never a whole config file.
- What it did not prove: four of the eight headline features in its launch video
  (iMessage, AgentMail inbox, Honcho memory, editable soul/memory) do not exist in the
  code. The 195-star fork did the work; the harness did the rest.
- Cost of the approach: it depends on Hermes internals that are not a stability contract,
  and it ships an unsafe default (`ALLOWED_EMAILS` empty = anyone with the URL gets in).
  Copy the discipline, not the code. It is TypeScript, unaudited, single-tenant, and
  shaped around one hosted computer vendor.

## Recommendation

1. **Build one shared package, not five servers.** `mcp_bridge`: per-user bearer token
   (never the browser JWT), a `@tool(name, policy="auto"|"ask"|"block")` registry over
   ordinary functions, a DB-persisted approval gate, and an audit writer. ~250–300 lines.
2. **Mount it on Agentic PMO first** as the reference implementation (2–3 days incl.
   tests). Tools: list/get projects, status, tasks, risks, apply a pack, run monitor,
   raise alert, save report. REST and JWT untouched — MCP is a second front door.
3. **Then AI-SAMS** (~half a day, it already has real state and users).
4. **Do not touch tier B.** The 15 static pages are fine. The site's real gap is not
   agent legibility — it is that `readiness-audit.html` stores everything in
   `localStorage`, so the diagnostic produces no record, no artifact and no re-entry.
   That is a small separate job (server-side score, stored submission, PDF), and an MCP
   tool falls out of it for free.
5. **The effort curve is the argument:** first mount days, second half a day, third hours.
   That is why the package is built properly once.

## Explicitly not doing

- Adopting the bot-hq code, or its vendor stack (hosted computer + composio + xAI).
- A bot-team dashboard of our own.
- Any unauthenticated MCP endpoint, or one token shared across users.
- Rewriting the Plan/Monitor/Alert agents at the same time. Ship the door, prove it, then decide.

## Open questions for the owner

1. Is the first client conversation about PMO, or about the AI-readiness diagnostic?
2. Do we want clients' *own* agents driving our systems in 2027, or do we want to keep the
   agent surface ours? (This changes whether the door is public or partner-only.)
3. Should `agent_actions` become an approval-and-decision log with named approvers? That
   is a schema change, and it is the artefact enterprise buyers ask for.
4. Budget appetite: days of engineering now, in exchange for a biddable feature — or park
   it until a specific deal requires it.

## Provenance

Repo studied at commit `decf9a2` (2026-11-11), ~8.3k lines server, ~5.5k web, 4 commits.
Video: "I Stole the Best Part of Every AI Agent… With One Prompt" (36 min). Numbers quoted
above are from the code, not the video.
