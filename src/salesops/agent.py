import json
import os

from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call, wrap_tool_call
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from salesops.config import Settings
from salesops.data import normalized
from salesops.observability import Run
from salesops.policy import blocked, input_reason, output_reason
from salesops.tools import ToolSurface


class ScriptedModel(BaseChatModel):
    steps: list[dict]

    @property
    def _llm_type(self):
        return "scripted-offline-test-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        index = sum(isinstance(message, AIMessage) for message in messages)
        step = self.steps[index] if index < len(self.steps) else {"content": "No further action."}
        step = dict(step)
        calls = step.get("tool_calls", [])
        for call in calls:
            for key, value in list(call["args"].items()):
                if value == "$draft_id":
                    previous = next(
                        message for message in reversed(messages)
                        if isinstance(message, ToolMessage) and message.name == "draft_email"
                    )
                    call["args"][key] = json.loads(previous.content)["draft_id"]
        if step.get("content") == "$last_tool":
            previous = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
            step["content"] = "Offline CRM result: " + previous.content
        step.setdefault("content", "")
        message = AIMessage(**step)
        return ChatResult(generations=[ChatGeneration(message=message)])


def call_step(name: str, arguments: dict) -> dict:
    return {"tool_calls": [{"name": name, "args": arguments, "id": f"call_{name}"}]}


def offline_model(question: str, surface: ToolSurface) -> ScriptedModel:
    query = normalized(question)
    account_id = next((
        account["account_id"] for account in surface.crm.tables["accounts"]
        if normalized(account["name"]) in query.split(" 's")[0]
        or normalized(account["account_id"]) in query.split()
    ), None)
    if "pipeline" in query:
        steps = [call_step("summarize_pipeline", {})]
    elif "email" in query and account_id:
        steps = [call_step("draft_email", {
            "account_name_or_id": account_id, "purpose": "the next steps discussed with your team"
        })]
        if "send" in query:
            steps.append(call_step("send_email", {"draft_id": "$draft_id"}))
    elif account_id:
        steps = [call_step("lookup_account_context", {"account_name_or_id": account_id})]
    elif "opportunit" in query:
        steps = [call_step("list_open_opportunities", {})]
    else:
        return ScriptedModel(steps=[{"content": "Specify an exact CRM account name, ID or pipeline task."}])
    return ScriptedModel(steps=steps + [{"content": "$last_tool"}])


def ask(
    question: str, settings: Settings, approval: str | None = None,
    task_id: str | None = None, model: BaseChatModel | None = None,
) -> dict:
    run = Run(settings, question, task_id=task_id)
    reason = input_reason(question, settings.values["max_input_characters"])
    if reason:
        run.event("guardrail", **blocked(reason, "input"))
        return run.finish("blocked", "This request is outside the allowed SalesOps policy.", reason)
    try:
        surface = ToolSurface(run, approval)
        if model is None:
            if settings.backend == "offline":
                model = offline_model(question, surface)
            else:
                if not os.getenv("OPENAI_API_KEY"):
                    return run.finish("failed", "No API credential is configured.", "missing_api_key")
                model = ChatOpenAI(
                    model=settings.model, temperature=settings.values["temperature"],
                    timeout=settings.values["model_timeout_seconds"], max_retries=0,
                )

        @wrap_tool_call
        def enforce_tools(request, handler):
            call = request.tool_call
            result = surface.invoke(call["name"], call["args"])
            return ToolMessage(
                content=json.dumps(result), name=call["name"], tool_call_id=call["id"]
            )

        @wrap_model_call
        def record_model(request, handler):
            run.model_calls += 1
            if run.model_calls > settings.values["max_model_calls"]:
                raise RuntimeError("model_budget_exceeded")
            response = handler(request)
            for message in response.result:
                usage = getattr(message, "usage_metadata", None) or {}
                run.input_tokens += usage.get("input_tokens", 0)
                run.output_tokens += usage.get("output_tokens", 0)
            run.event("model", call=run.model_calls, model=settings.model,
                      input_tokens=run.input_tokens, output_tokens=run.output_tokens)
            return response

        agent = create_agent(
            model, tools=surface.langchain_tools(), system_prompt=settings.prompt,
            middleware=[enforce_tools, record_model],
        )
        response = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            config={"recursion_limit": 24},
        )
        answer = response["messages"][-1].content
        if not isinstance(answer, str):
            answer = json.dumps(answer)
        reason = output_reason(answer)
        if reason:
            run.event("guardrail", **blocked(reason, "output"))
            return run.finish("blocked", "The generated response did not pass the output policy.", reason)
        interventions = [event for event in run.events if event["kind"] == "guardrail"]
        if interventions:
            return run.finish("blocked", "A proposed action was blocked by policy.", interventions[-1]["reason"])
        decisions = [
            event for event in run.events if event["kind"] == "hitl" and event["action"] == "decision"
        ]
        if decisions:
            decision = decisions[-1]
            status = decision["status"]
            if status in {"awaiting_approval", "rejected", "sent"}:
                answer = json.dumps({
                    "email_status": status, "draft_id": decision["draft_id"], "simulated": True,
                    "message": "No real email is delivered.",
                })
                return run.finish("success" if status == "sent" else status, answer)
        return run.finish("success", answer)
    except Exception as error:
        error_kind = type(error).__name__
        reason = "model_budget_exceeded" if str(error) == "model_budget_exceeded" else error_kind
        run.event("error", error_type=error_kind, reason=reason)
        return run.finish("failed", "The run failed. Inspect its redacted trace.", reason)
