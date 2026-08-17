# Agent Playground

A multi-agent system that analyzes account data and produces PDF reports.

---

## The Problem

**Meridian Health** (account `MERID-001`) is a healthcare-tech customer whose
contract renewal is approaching. The account team relies on this system to turn
billing, product usage, and support data into reports they take into customer
conversations.

The system has the pieces: agents that can read CSV data and generate PDFs.
But the current implementation is rough — the agent wastes steps, and the
architecture has blind spots.

---

## How this works

There are two parts:

1. **A short task, on your own time** (30–60 minutes) — described below. It's
   deliberately small: the point is to get you into the repo before we meet,
   not to see how much you can build in an hour. You send us a PR and a few
   lines of notes.
2. **A live session** (60–90 minutes) — we extend this same repo together with
   a new requirement. AI tools allowed and expected.

We then spend a bit of time talking through what you built.

---

## Setup

Clone the repo. Read the code. Come with questions.

```bash
git clone <repo-url>
cd nanzen-agents-playground
make install

# Configure your LLM provider (see .env.example)
cp .env.example .env
# Edit .env with your MODEL_ID, API_KEY, and API_BASE
set -a && source .env && set +a

# Try running it
make run ARGS="--task billing_summary"
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MODEL_ID` | Yes | Model identifier (e.g. `accounts/fireworks/models/minimax-m2p5`, `qwen3.5-35b`) |
| `API_KEY` | No | API key for your provider (not needed for local servers) |
| `API_BASE` | No | Base URL (e.g. `http://localhost:8080/v1` for llama.cpp) |

Works with any OpenAI-compatible API: Fireworks, Together, OpenRouter, OpenAI,
Ollama, llama.cpp, etc. See `.env.example` for examples.

### What to look at

The codebase is small. Read it however you like. The key pieces:

- `src/challenge/agent.py` — the `ActorAgent` wraps a
  [smolagents CodeAgent](https://huggingface.co/docs/smolagents) that writes
  and executes Python to use tools
- `src/challenge/tools/` — `CSVReaderTool` reads data, `PDFReportTool`
  generates reports
- `src/challenge/tasks.py` — task definitions that drive the agents
- `src/challenge/runner.py` — spawns agents and collects results
- `data/*.csv` — the raw data the agents work with

---

## Part 1 — Before we meet

Meridian's renewal is coming up, and the account manager is preparing for it.
They ran the `billing_summary` task, looked at the numbers, and said the
billing total "doesn't look right". They can't tell us why — it's a hunch.

**Your task: produce a billing summary for `MERID-001` that you'd be willing
to put in front of the customer**, and make whatever changes to the repo you
think that requires.

That's the whole brief. There's no hidden checklist, and how you scope this is
part of what we're looking at. If something about it is unclear, ask — that
counts in your favour, not against it.

**Timebox it to 30–60 minutes.** We're not looking for polish.

**Send us:**

- A PR with whatever you changed. The repo is public — fork it, push your
  branch to your fork, and open the PR from there.
- A short note, 5–10 lines: what you'd do with more time, and anything you
  decided to leave alone on purpose.

---

## Part 2 — The live session

We'll extend this repo together with a new requirement. There's no fixed
checklist, we'll go where the conversation leads, and we'll be more
interested in your reasoning out loud than in finished code. You'll drive the
coding agents — we're interested in how you direct them and what you check,
not in watching you type.

Come with observations, questions, or opinions about the code and the data.
The questions you ask tell us as much as the code you write.

---

## Project Structure

```
nanzen-agents-playground/
├── README.md
├── pyproject.toml
├── Makefile                 # install, style, test, run
├── .env.example             # LLM provider config template
├── data/                    # CSV data (shared context)
│   ├── accounts.csv
│   ├── billing.csv
│   ├── product_usage.csv
│   ├── support_tickets.csv
│   ├── crm_interactions.csv
│   ├── emails.csv
│   ├── contracts.csv
│   └── purchase_orders.csv
├── output/                  # Generated PDF reports (gitignored)
├── src/
│   └── challenge/
│       ├── agent.py         # ActorAgent
│       ├── runner.py        # Task runner
│       ├── tasks.py         # Task definitions
│       └── tools/
│           ├── csv_reader.py
│           └── pdf_report.py
└── tests/
    └── test_tools.py
```

---

## Commands

```bash
make install              # Install dependencies
make test                 # Run tests
make style                # Format with ruff
make run                  # Run all tasks
make run ARGS="--task X"  # Run a specific task
make run ARGS="--list"    # List available tasks
make run ARGS="--parallel"  # Run tasks concurrently
```
