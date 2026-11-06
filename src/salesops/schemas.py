from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountQuery(Arguments):
    account_name_or_id: str = Field(min_length=1, max_length=120)


class OpportunityQuery(Arguments):
    stage: str | None = Field(default=None, max_length=60)


class DraftRequest(AccountQuery):
    purpose: str = Field(min_length=1, max_length=800)


class SendRequest(Arguments):
    draft_id: str = Field(min_length=1, max_length=64)


class AnalysisRequest(Arguments):
    dataset: Literal["opportunities", "support_tickets", "accounts", "product_usage"]
    operation: Literal["count", "sum", "average", "group_sum", "group_count"]
    field: str | None = None
    group_by: str | None = None
