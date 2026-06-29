"""Unified, provider-agnostic billing analytics schema.

A single normalized bucket-row (`BillingRecord`) that both the Runpod and Modal
providers map into, plus the response envelopes the admin endpoints return.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["runpod", "modal"]


class BillingRecord(BaseModel):
    """One normalized billing bucket-row from a provider."""

    provider: Provider
    object_id: str
    object_name: str
    timestamp: datetime  # UTC, start of the bucket
    cost: float  # USD
    runtime_ms: Optional[int] = None
    storage_gb: Optional[float] = None
    gpu: Optional[str] = None
    environment: Optional[str] = None
    tags: dict[str, str] = Field(default_factory=dict)
    resource_breakdown: dict[str, float] = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class HighestCost(BaseModel):
    name: str
    cost: float


class SummaryResponse(BaseModel):
    total_spend: float
    avg_daily_spend: float
    total_runtime_ms: int
    avg_daily_runtime_ms: float
    total_storage_gb: float
    active_endpoints: int
    active_modal_apps: int
    highest_cost_endpoint: Optional[HighestCost] = None
    highest_cost_platform: Optional[HighestCost] = None
    num_days: int
    warnings: list[str] = Field(default_factory=list)


class TimeseriesResponse(BaseModel):
    labels: list[str]
    cost: list[float]
    runtime_ms: list[float]
    storage_gb: list[float]
    cost_by_group: dict[str, list[float]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ProvidersResponse(BaseModel):
    labels: list[str]
    cost: list[float]
    runtime_ms: list[float]
    storage_gb: list[float]
    warnings: list[str] = Field(default_factory=list)


class BreakdownRow(BaseModel):
    key: str
    cost: float
    runtime_ms: int
    storage_gb: float
    count: int


class BreakdownResponse(BaseModel):
    group_by: str
    rows: list[BreakdownRow]
    warnings: list[str] = Field(default_factory=list)


class TableResponse(BaseModel):
    rows: list[BillingRecord]
    total: int
    page: int
    page_size: int
    warnings: list[str] = Field(default_factory=list)
