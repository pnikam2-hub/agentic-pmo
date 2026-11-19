# GPU trial — what to rent, how I get in, and what we will judge

Purpose: answer one question with evidence, cheaply — **can a model we host ourselves do the PMO's
reasoning well enough to be offered to a client who will not let data leave their building?**
Secondary: does it help our own coding. The trial is by the hour, under $10, and produces a written
comparison rather than an opinion.

## What to rent

| | Minimum (cheap, 24 GB) | Preferred (if you want a fair coding test) |
|---|---|---|
| GPU | 1 × RTX 4090 24 GB **or** RTX 3090 24 GB | 1 × A100 40/80 GB, or L40S 48 GB |
| VRAM | 24 GB (the model needs ~21 GB at 4-bit, 8K ctx) | 40 GB+ lets us run a bigger model or longer context |
| Disk | 60 GB | 100 GB |
| Image | Ubuntu 22.04/24.04, CUDA 12.x, Docker | same |
| Ports | 22 (SSH) + 8000 (inference) | same |
| Price reference | RTX 4090 $0.34–0.89/hr on RunPod | A100 80GB $1.19–2.19/hr |

Providers that let you paste an SSH public key at creation: RunPod, Vast.ai, Lambda, TensorDock.
Rent for 2–3 hours; we will not need more than one.

## How I get access — no password, ever

Add this public key at rental time (most providers have a "SSH public key" field; on Vast.ai paste it
into the `--ssh`/authorized-keys field):

    ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKPCsnKCpRBGty4daM3zgJZrEgR54R3L8GeFBImw42rj hermes-gpu-trial

Then send me only the connection string the provider shows, e.g. `ssh root@1.2.3.4 -p 40123`. The
private key stays on this machine at `/root/.ssh/gpu_trial` and is never printed.

If the provider only offers a web terminal, tell me — the trial still works, I'll give you a
paste-in script instead, but I lose the ability to measure anything myself.

**Important:** treat the box as disposable and assume it is visible on the public internet. It will
hold no client data beyond the prompt text of one project; the harness sends only task titles,
statuses and dependencies — no names, no emails, no attachments.

## What we measure

Two workloads, both real, neither synthetic.

**1. The PMO's own reasoning (the question that matters).** The monitor agent's actual prompt for the
live 165-task EPC project: 34,910 hours, 162 tasks waiting on unfinished predecessors, 211 dependency
edges — 20,227 characters, about 6,300 tokens. Run three times against the local model and compare with
the hosted baseline already measured (see below). Scored on:

  - does it return valid JSON every time (a parse failure is a hard fail for an agent loop)
  - does it name the same dominant chains (commissioning/handover, engineering, procurement)
  - does it name the *predecessor* rather than restating counts
  - latency and tokens/second

**2. A bounded coding task.** One small, real piece of our backlog, given to the local model through
the same harness: add a CSV export endpoint for tasks with two tests. Scored on: does the code run,
do the tests pass, how many turns, how much had to be repaired by hand.

## The bar — set against a measured baseline, not a guess

The hosted model was measured on this exact prompt set on 19 Nov 2026 (results/hosted-*.json):

  monitor reasoning, 165 tasks   3/3 valid JSON, 12.3 / 17.5 / 16.3 s, ~2,500–4,000 output tokens
  coding task (CSV endpoint)     3/3 returned, 3.8 / 4.3 / 3.9 s

Two harness bugs surfaced while getting that number, both worth remembering: DeepSeek's thinking mode
consumed the whole token budget and returned *empty* content (200 OK, zero characters), and a 4,096-token
cap truncated the JSON mid-object. A model that looks broken may simply be misconfigured.

A local 30B model must therefore:

  - return valid JSON on 3 of 3 runs (a parse failure is a hard fail for an agent loop)
  - name at least two of the three real critical chains, and at least one predecessor by name
  - answer in under ~45 s for this prompt (a 2.5k-token answer at ~100 tok/s is about 25 s; much
    slower than that and an interactive demonstration becomes a watching-paint-dry exercise)
  - pass the coding task's own tests without hand-repair

If it fails the coding task but passes the reasoning task, that is still a useful answer: on-prem for
the PMO, hosted models for our own development. That split is common and worth reporting honestly.

## Using the same setup in a client demonstration

This is the part that answers "may help us demonstrate capability". The demo is not the model — it is
that **the whole reasoning loop runs on hardware in the room**, on the client's own project data:

  1. rent the box, run `serve.sh`, confirm `curl localhost:8000/v1/models` answers
  2. pull the bag off the network: `iptables -A OUTPUT -m owner --uid-owner $(id -u) -j DROP` after the
     model is loaded, or simply unplug the uplink and show that the endpoint still answers
  3. push a 165-row plan into the PMO, run the Monitor agent, show it naming the commissioning chain
     and the predecessor that is holding it
  4. say the true sentence: "nothing left this machine — no API call, no data processor, no egress"

That is a defensible claim, and it is the one government and regulated buyers ask about. What we must
not claim is that a 30B local model matches a frontier model — the comparison table exists precisely so
we can show a client the honest delta and let them choose.

## What it costs

Two hours of a 4090 plus a few cents of electricity-equivalent: under $10. Against that, the answer
decides whether "runs inside your network" goes in the enterprise pitch as a capability or as a
roadmap item — and it decides it with numbers rather than a vendor's benchmark table.

## Scripts in this directory

  setup_llamacpp.sh   installs llama.cpp (CUDA build) and fetches a 4-bit GGUF coder model
  setup_vllm.sh       alternative for a 40 GB+ card: vLLM serving the same model, more throughput
  serve.sh            starts an OpenAI-compatible endpoint on :8000
  make_prompt.py      builds the real monitor prompt from a PMO export (no live database needed)
  bench.py            runs a prompt set against any OpenAI-compatible endpoint, records JSON validity,
                      latency, tokens/second, and writes a side-by-side comparison file
  sample_prompt.json  the prompt set: one reasoning task, one coding task

The comparison is written to `results/compare-<model>-<timestamp>.md`, which is what you show a
prospective client — not the marketing benchmark of whichever model we happened to rent.
