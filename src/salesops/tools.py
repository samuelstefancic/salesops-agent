import json

from langchain_core.tools import StructuredTool
from pydantic import ValidationError

from salesops.data import CRM
from salesops.observability import Run
from salesops.policy import blocked, input_reason, output_reason, redact
from salesops.sandbox import analyze
from salesops.schemas import (
    AccountQuery,
    AnalysisRequest,
    Arguments,
    DraftRequest,
    OpportunityQuery,
    SendRequest,
)
from salesops.state import StateStore


class ToolSurface:
    def __init__(self, run: Run, approval: str | None = None):
        self.run = run
        self.approval = approval
        self.crm = CRM(run.settings)
        self.store = StateStore(run.settings.root)
        self.definitions = {
            "lookup_account": (
                AccountQuery,
                "Look up one allowed CRM account by exact name or ID.",
            ),
            "lookup_account_context": (
                AccountQuery,
                "Read CRM context for account risk, renewals, usage and support.",
            ),
            "list_open_opportunities": (
                OpportunityQuery,
                "List open opportunities in the allowed CRM scope, with optional stage.",
            ),
            "summarize_pipeline": (Arguments, "Summarize open pipeline value by stage."),
            "analyze_crm": (
                AnalysisRequest,
                "Run bounded CRM aggregates. No Python, files, imports or network. "
                "For open pipeline value use opportunities/group_sum/amount_usd/stage.",
            ),
            "draft_email": (DraftRequest, "Create a follow-up draft for a CRM primary contact."),
            "send_email": (
                SendRequest,
                "Request human approval for a stored draft; simulate sending locally.",
            ),
        }

    def deny(self, reason: str, name: str) -> dict:
        result = blocked(reason, "tool")
        self.run.event("guardrail", name=name, **result)
        return result

    def invoke(self, name: str, arguments: dict) -> dict | list:
        run = self.run
        run.tool_calls += 1
        run.event("tool_call", name=name, arguments=arguments)
        if name not in self.definitions:
            return self.deny(
                "restricted_internal_data" if "internal" in name else "unknown_tool", name
            )
        if run.tool_calls > run.settings.values["max_tool_calls"]:
            return self.deny("tool_budget_exceeded", name)
        schema = self.definitions[name][0]
        try:
            parsed = schema.model_validate(arguments)
            reason = input_reason(json.dumps(arguments))
            if reason:
                return self.deny(reason, name)
            result = self.execute(name, parsed)
        except (ValueError, TypeError, KeyError, ValidationError):
            return self.deny("invalid_or_out_of_scope_arguments", name)
        result = redact(result)
        run.event("tool_result", name=name, result=result)
        return result

    def execute(self, name: str, args: Arguments):
        if name == "lookup_account":
            return self.crm.account(args.account_name_or_id)
        if name == "lookup_account_context":
            return self.crm.context(args.account_name_or_id)
        if name == "list_open_opportunities":
            return self.crm.open_opportunities(args.stage)
        if name == "summarize_pipeline":
            return analyze(
                self.crm.tables,
                AnalysisRequest(
                    dataset="opportunities",
                    operation="group_sum",
                    field="amount_usd",
                    group_by="stage",
                ),
            )
        if name == "analyze_crm":
            return analyze(self.crm.tables, args)
        if name == "draft_email":
            context = self.crm.context(args.account_name_or_id)
            contacts = context["contacts"]
            contact = next((row for row in contacts if row.get("is_primary")), None)
            if contact is None:
                raise ValueError("No primary contact")
            body = {
                "to": contact["email"],
                "subject": f"Following up on {context['account']['name']}",
                "body": f"Hi {contact['first_name']},\n\nI wanted to follow up regarding "
                f"{args.purpose}. Please let us know a suitable time to discuss next steps.\n\n"
                "Best,\nUdaCenture SalesOps",
            }
            reason = output_reason(json.dumps(body))
            if reason:
                return self.deny(reason, name)
            return self.store.draft(self.run.settings.scope, body, self.run.run_id)
        if name == "send_email":
            self.run.event("hitl", action="approval_requested", draft_id=args.draft_id)
            self.run.approval = self.approval
            result = self.store.decide(self.run.settings.scope, args.draft_id, self.approval)
            self.run.event("hitl", action="decision", decision=self.approval, **result)
            return result
        raise ValueError("Unsupported tool")

    def langchain_tools(self) -> list[StructuredTool]:
        def bound(name):
            def execute(**kwargs):
                return self.invoke(name, kwargs)

            return execute

        return [
            StructuredTool(
                name=name,
                description=description,
                args_schema=schema,
                func=bound(name),
                handle_validation_error="Invalid arguments: follow the tool schema.",
            )
            for name, (schema, description) in self.definitions.items()
        ]
