# UdaCenture SalesOps Agent

A command-line assistant for the mock CRM supplied with Udacity's AgentOps course. It answers account and renewal questions, calculates open pipeline totals, and prepares follow-up emails. Email sending is simulated in a local outbox.

The project adds the controls missing from the starter notebook: restricted data access, checks around tool calls, email approval, tests, and a record of what happened during each run.

## Setup

You need Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/samuelstefancic/salesops-agent.git
cd salesops-agent
uv sync --locked
```

To try it without an API key:

```bash
uv run salesops-agent --offline ask "Summarize the current open sales pipeline by stage."
```

Offline mode uses a scripted test model with the same tools and checks as the live agent. It is useful for checking the application locally; it does not test an LLM's answers.

For live requests, copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Use `https://openai.vocareum.com/v1` as `OPENAI_BASE_URL` for a Vocareum key, or `https://api.openai.com/v1` for a direct OpenAI key. The default model is `gpt-4o-mini`; `SALESOPS_MODEL` overrides it. The `.env` file is ignored by Git.

```bash
uv run salesops-agent ask "Summarize the account risk for TechStart Inc."
```

The response includes the answer, run ID, status, tools used, latency, token counts and estimated cost. If the key is missing, the command records a failed run and exits with code 1.

## Prototype Review

The starter worked as a demo, but several parts needed changing:

- HR and confidential financial data were loaded with the CRM data and exposed through unrestricted tools.
- The email tool could write any recipient and body straight to the outbox, without approval.
- Fuzzy account matching could choose the wrong account. Pipeline totals also included closed deals.
- Prompts, tools and execution were mixed in the notebook, with no pinned dependencies, automated checks or run history.

The original notebook remains in `starter/` for reference. The application runs from the repository root.

## Architecture

`cli.py` reads the request and passes it to `ask()` in `agent.py`. The input check runs first. If it passes, a LangChain `create_agent` graph chooses from the available CRM tools.

Every proposed tool call goes through `ToolSurface`, which checks the tool name and arguments before doing any work. Tools receive only the allowed CRM tables and fields. The final answer is checked before it is returned, and the run is saved to a log and trace file.

The main files are:

| Area | Files in `src/salesops/` |
|---|---|
| Agent and command-line interface | `agent.py`, `cli.py` |
| CRM access and tool arguments | `data.py`, `tools.py`, `schemas.py` |
| Policies and analysis | `policy.py`, `sandbox.py` |
| Email state and approvals | `state.py` |
| Logs, evaluation and reports | `observability.py`, `evaluation.py`, `reporting.py` |

## Versioned Components

The prompt, configuration and evaluation tasks are separate files in `src/salesops/resources/`. Tool definitions and schemas have their own modules. Python is pinned in `.python-version`, and `uv.lock` fixes the dependency versions.

Each trace includes the prompt hash and configuration version. `GITLOG.txt` contains a snapshot of the published commit history, taken before the commit that saved it.

## Guardrail Design

There are three places where a request can be stopped:

- **Input:** requests for restricted HR information, acquisition strategy, layoffs, credentials or common policy overrides are blocked before the model or CRM is loaded.
- **Tools:** unknown tools, extra arguments and out-of-scope account lookups are rejected. The application never loads the internal HR or financial strategy files. Suspicious text in CRM notes is redacted before it reaches the model.
- **Output:** restricted content, credentials and unsupported customer commitments are blocked before returning an answer or saving an email draft.

Account lookup requires an exact normalized name or ID. `Settings.allowed_accounts` can restrict the accounts available to both lookup and analysis tools.

These checks are Python code, so they do not depend on the model following its prompt. The text filters use regular expressions and have coverage gaps; they need broader testing before use with real data.

## Sandboxed Execution

`analyze_crm` supports counts, sums, averages and grouped totals over approved CRM data. For example, it can total open opportunity value by stage or count support tickets by severity.

The tool accepts only listed datasets, operations and fields. It processes at most 2,000 rows and rejects non-finite numbers. It has no argument for Python code, imports, file access or network calls, and does not use `eval` or `exec`. Opportunity analysis excludes Closed Won and Closed Lost deals.

This keeps analysis within a small set of operations. It is not an OS sandbox: if arbitrary generated code is added later, it will need a separate isolated worker.

## Human-in-the-Loop Workflow

`draft_email` takes the recipient from the account's primary CRM contact and stores a draft in SQLite. `send_email` accepts only that draft's ID. Approval comes from the CLI, outside the model's tool arguments.

```bash
uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp about next steps." --approval approve
uv run salesops-agent ask "Draft and send a follow-up email to Acme Corp about next steps." --approval reject
```

Without a decision, the run returns `awaiting_approval` and a draft ID. To approve that stored draft:

```bash
uv run salesops-agent resume DRAFT_ID --approval approve
```

Approval adds one entry to the local outbox. Repeating the same approved action does not add another. Rejection leaves the outbox untouched and is final for that draft. Approval requests and decisions are recorded in the log and trace.

Drafts belong to a user, session and thread. The global `--user-id`, `--session-id` and `--thread-id` options must match when resuming. These are local namespaces, not authenticated identities. Questions start fresh conversations; SQLite stores email state rather than chat history.

For an offline example, put `--offline` before `ask`.

## Evaluation

```bash
uv run pytest -q
uv run evaluate
uv run evaluate --live
```

The default suite has 18 scenarios covering CRM questions, account risk, pipeline totals, restricted inputs, forbidden tools, sensitive outputs, analysis restrictions and email decisions. Each result records pass/fail, latency, estimated cost and a failure reason when needed. Email checks also inspect the outbox to confirm what actually changed.

`--live` uses the configured API for functional questions. Tests that force a forbidden tool call or sensitive output stay scripted, so the exact case is exercised on each run. The report identifies which model mode each task used.

Results are saved in [reports/evaluation_report.md](reports/evaluation_report.md) and its JSON equivalent. The matching redacted logs and traces are in `reports/evidence/`. Each evaluation uses a temporary database, separate from interactive runs.

GitHub Actions runs installation, lint, formatting, tests, offline evaluation and package builds. It needs no API key.

## Logging and Tracing

Runs append to `logs/runs.jsonl`. Each also creates `traces/<run_id>.json` with the input, selected tools, arguments, redacted results, policy decisions, approval decisions, final output and errors. The summary includes the run and scope IDs, timestamp, status, latency, token counts, estimated cost and failure reason.

Sensitive text is redacted before saving. Provider errors retain their type without copying exception messages that might contain credentials. Runtime logs, traces, databases and `.env` files are excluded from Git; `reports/evidence/` holds the saved validation run using fictional data.

To inspect a run, use the same scope options as the original command:

```bash
uv run salesops-agent inspect RUN_ID
```

This reads the trace without repeating the action.

## Monitoring Report

```bash
uv run generate-monitoring-report
uv run generate-monitoring-report --log reports/evidence/runs.jsonl
```

The first command uses interactive logs; the second uses the saved evaluation logs. Both write `reports/monitoring_report.md` with run counts, completion and failure rates, average latency, estimated total and average cost, tool usage, policy blocks, approval decisions and common failure reasons.

A blocked request can be a passing security test. The report therefore lists blocks, rejections and pending approvals separately from technical failures.

Cost estimates use the model's token metadata and the rates in `config.v1.json`. Check those rates for your provider. Offline runs make no API calls and have zero API cost.

## Validation Status

Checks on 6 November 2026 passed **60 tests** and **18/18 offline scenarios**, along with lint, formatting, lockfile checks and source/wheel builds. The same checks passed from a clean public clone. Details are in [WRITEUP.md](WRITEUP.md) and [reports/verification.txt](reports/verification.txt).

Live model validation is still pending. During those checks, Udacity displayed “Your Cloud Resource is inactive”. Once the resource is active, run `uv run evaluate --live` to check provider integration and model answers.

## Packaging

The Dockerfile runs the application as a non-root user:

```bash
docker build -t salesops-agent .
docker run --rm salesops-agent --offline ask "Summarize the open sales pipeline."
```

The Python packages were built with `uv build`. The Docker image has not been built or run as part of the recorded validation.

## Known Limitations and Production Hardening

Before using this with real customers, the main work would be:

- Authenticate users and enforce account permissions on the server. Bind approvals to the exact email shown to the reviewer.
- Move secrets into managed storage and add a request deadline and spending limits.
- Expand live evaluations and attack cases, especially paraphrases, other languages and instructions hidden in retrieved data.
- Replace local logs and SQLite with shared storage and telemetry suited to concurrent users, with access controls and retention rules.
- Add delivery status, retry handling and provider idempotency if connecting a real email service. Use an isolated worker if analysis is extended to generated code.

## Source

Based on [Udacity's SalesOps starter](https://github.com/udacity/cd15157-agent-ops-starter), revision `640790c2d2de6187a34f69154d2060916918a2fc`. The original notebook and fixtures are kept in `starter/`; all company and CRM data is fictional. See [LICENSE.txt](LICENSE.txt) for the original terms.

A longer explanation in French is available in [docs/IMPLEMENTATION_FR.md](docs/IMPLEMENTATION_FR.md).
