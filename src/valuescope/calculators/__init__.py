"""Deterministic financial calculators (no I/O, no AI)."""

from .amortization import DebtSchedule, PaymentRow, build_schedule
from .cashflow import ProjectionInputs, ProjectionResult, YearRow, project
from .irr import equity_multiple, irr, npv
from .valueadd import RenovationResult, simulate_renovation
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
    "metrics",
]
