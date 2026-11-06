# SalesOps monitoring

Operational success means a completed answer/action. A policy block, rejection or pause is a separate outcome, and may be an expected pass in the evaluation suite. Failure rate counts technical failures only. These rates therefore need not sum to 100%.

Offline scripted calls have zero API cost; their latency is application overhead. They must not be interpreted as live model performance.

| Metric | Value |
|---|---|
| total_runs | 18 |
| success_rate | 0.3333333333333333 |
| failure_rate | 0.0 |
| average_latency_ms | 8.010055555555557 |
| total_estimated_cost_usd | 0.0 |
| tool_calls | {"analyze_crm": 3, "draft_email": 3, "lookup_account_context": 3, "lookup_internal_financial_data": 1, "lookup_internal_hr_data": 1, "send_email": 3, "summarize_pipeline": 1} |
| guardrail_blocks | 10 |
| hitl_approvals | 1 |
| hitl_rejections | 1 |
| statuses | {"awaiting_approval": 1, "blocked": 10, "rejected": 1, "success": 6} |
| failure_reasons | {"invalid_or_out_of_scope_arguments": 2, "prompt_injection": 1, "restricted_internal_data": 6, "sensitive_output": 1} |
| backends | {"offline": 18} |
| average_estimated_cost_usd | 0.0 |
