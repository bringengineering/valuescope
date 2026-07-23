"""Deterministic financial calculators (no I/O, no AI)."""

from .amortization import DebtSchedule, PaymentRow, build_schedule
from .cashflow import ProjectionInputs, ProjectionResult, YearRow, project
from .irr import equity_multiple, irr, npv
from .valueadd import RenovationResult, RenovationAnalysis, simulate_renovation, analyze_renovation
from .net_yield import (
    NetYieldResult,
    OperatingAssumptions,
    assumptions_for_age,
    compute_net_yield,
)
from .operations import OperatingSnapshot, ValueUpResult, compare_valueup
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
    "RenovationAnalysis",
    "analyze_renovation",
    "compute_net_yield",
    "NetYieldResult",
    "OperatingAssumptions",
    "assumptions_for_age",
    "OperatingSnapshot",
    "ValueUpResult",
    "compare_valueup",
    "metrics",
]
