# SalesOps Agent — Validation Report

## Scope and result

Validation date: 6 November 2026. The application was developed from the public Udacity starter, with its original notebook retained in `starter/` and its license preserved.

Measured locally: **60 passing regression tests**, **18 passing offline evaluation tasks**, Ruff lint/format checks, a consistent uv lockfile, and successful source/wheel builds. GitHub Actions also completed the initial published verification successfully; the current commit’s workflow result is available under the repository Actions tab.

The course Cloud Resources panel displayed **“Your Cloud Resource is inactive”**. The live provider path has not been validated successfully. Offline results verify the graph, policies, CRM tools, approval state and reporting, not live LLM reasoning. A reviewer should distinguish this limitation from the completed local checks.

## Requirements and evidence

| Rubric requirement | Implementation | Evidence |
|---|---|---|
| Reproducible Python structure | Root `src/`, `data/`, `logs/`, `traces/`, `reports/`; Python 3.13; uv metadata and lockfile | `uv sync --locked`, `uv lock --check`, `reports/verification.txt` |
| Separate versioned components | External prompt/config/tasks, dedicated schemas/tools/policy modules | `src/salesops/resources/`, `schemas.py`, `tools.py`, published commit history |
| Meaningful Git evolution | Separate scaffolding, prompt/schema, CRM, policy, analysis, approval, CLI, evaluation, tests and packaging commits | `GITLOG.txt`, generated from the actual public branch |
| Local question entry point | `uv run salesops-agent ask "..."`; explicit `--offline` test path | Run IDs and log/trace artifacts; CLI verification capture |
| Prototype and architecture review | README includes all required named sections and explains production hardening | `README.md`, `docs/IMPLEMENTATION_FR.md` |
| Automated evaluation | 18 versioned tasks; per-task result, latency, cost, run ID and reason | `reports/evaluation_report.json`, `reports/evaluation_report.md` |
| Input guardrail | Runs before model initialization and data loading | `input-compensation`, `input-hr`, `input-strategy`, `input-layoffs`, `input-injection`; pytest missing-data-root tests |
| Tool/action guardrail | Allowlisted tools and strict schemas; forbidden calls cross real LangChain middleware | `tool-hr`, `tool-strategy`, schema/capability-injection tests |
| Output guardrail | Generated sensitive content replaced before returning; sensitive data excluded from traces | `sensitive-output`, protected-field/credential and log-redaction tests |
| Constrained analysis | CRM-only aggregate DSL; allowed tables/columns, row ceiling, no code capability | `sandbox-allowed`, `sandbox-restricted`, `sandbox-code-denied`; independent pipeline-total test |
| Human approval | Stored draft, external CLI signal, pause/resume, terminal rejection | `email-approved`, `email-rejected`, `email-awaits-approval`; outbox assertions |
| No approval bypass / duplicate send | Sender only accepts a draft ID; transactional SQLite transitions | Repeated resume, reject-then-approve, forged arguments and cross-scope tests |
| Structured logs and traces | Run metadata, tool arguments/results, policy events and approval decisions | `reports/evidence/runs.jsonl`, per-run JSON files referenced by the evaluation report |
| Consolidated monitoring | Counts/rates/means, tool usage, policy blocks, decisions and reasons | `reports/monitoring_report.md`, generated from the captured evidence log |
| Optional persistence and isolation | User/session/thread scoped SQLite drafts/outbox; fresh conversation per question | Cross-user/session/thread tests; README scope limitations |
| Optional CI and packaging | GitHub Actions plus non-root Docker recipe | Actions tab; Docker recipe provided, image build/run not measured |

## Recorded evaluation outcomes

The 18-task local capture contains:

- 6 completed functional/action runs;
- 10 expected policy blocks;
- 1 rejected email action;
- 1 email action waiting for approval;
- 0 technical failures.

All 18 scenarios passed their expected outcomes. A blocked/rejected/paused application run is not counted as operational completion, even when it is the correct evaluation result. This explains the monitoring completion rate of 6/18 without suggesting a 67% test failure rate.

Each captured task uses the offline scripted model. Its API token counts and estimated API cost are zero. The mean latency in the monitoring report is local application overhead, not a provider latency benchmark. Configurable live pricing estimates are kept separate from a billing claim.

## Concrete data checks

The approved CRM fixtures contain 133 open opportunities with total value **26,525,000 USD**. An independent calculation in the regression tests agrees with the constrained analysis tool. Closed Won and Closed Lost opportunities are excluded.

TechStart A003 has a health score of 95 but a contract end of 2026-05-28, before the configured reference date 2026-11-06. GlobalRetail A002 has a health score of 25, declining usage, unresolved high/critical support issues and a stalled renewal. Offline evaluation checks that the corresponding evidence flows through the tool path. It does not establish that the live model will interpret it correctly.

## Reproduction

```bash
uv sync --locked
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q
uv run evaluate
uv run generate-monitoring-report --log reports/evidence/runs.jsonl
uv lock --check
uv build
```

To complete provider/model validation once the course resource is active:

```bash
uv run evaluate --live
```

The functional rows will then use the configured live model; forced security probes remain deterministic and identify their backend. Inspect failed task traces before interpreting aggregate scores. Commit the new measured reports only after reviewing their contents for secrets.

## Submission boundary

The public repository contains the runnable project, source provenance, tests, reports and real Git history. No personal API credential is included. No Udacity submission was sent. Live-model validation and a Docker image execution remain explicitly unverified.
