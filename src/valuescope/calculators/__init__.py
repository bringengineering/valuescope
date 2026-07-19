"""Deterministic financial calculators (no I/O, no AI)."""

from .amortization import DebtSchedule, PaymentRow, build_schedule
from .cashflow import ProjectionInputs, ProjectionResult, YearRow, project
from .irr import equity_multiple, irr, npv
from .valueadd import RenovationResult, simulate_renovation
from .net_yield import (
    NetYieldResult,
    OperatingAssumptions,
    assumptions_for_age,
    compute_net_yield,
)
from . import metrics

__all__ = [
    "build_schedule",
    "DebtSchedule",
    "PaymentRow",
    "project",
    "ProjectionInputs",
    "ProjectionResult",
    "YearRow",
    "irr",
    "npv",
    "equity_multiple",
    "simulate_renovation",
    "RenovationResult",
    "compute_net_yield",
    "NetYieldResult",
    "OperatingAssumptions",
    "assumptions_for_age",
    "metrics",
]
