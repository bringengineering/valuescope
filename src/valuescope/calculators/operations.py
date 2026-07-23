"""건물 운영손익 & 밸류업 실증 — 개선 전/후 운영성과 비교.

BRING '건물 밸류업 실증 프로젝트'를 뒷받침한다. 한 건물의 개선 전/후
운영 스냅샷(세대·공실·임대·비용·민원)을 받아 결정론적으로 계산한다:

- 유효임대수입(EGI)·공실손실·운영비·순영업소득(NOI)
- 개선 전/후 변화(공실·임대·비용·민원)
- 투자 대비 회수기간·연 ROI

원칙(CLAUDE.md): 금액은 Decimal(Money). float 금지. 핵심 숫자는 엔진이 계산.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ..domain.money import Money


@dataclass(frozen=True)
class OperatingSnapshot:
    """특정 시점의 건물 운영 상태(월 단위)."""
    total_units: int
    occupied_units: int
    avg_unit_rent: Money        # 세대 평균 월세
    monthly_costs: Money        # 월 운영비 합계(청소·수리·소모품·공용관리 등)
    avg_vacancy_days: Optional[int] = None   # 평균 공실기간(일)
    monthly_complaints: Optional[int] = None  # 월 민원 건수

    def __post_init__(self):
        if self.total_units < 0 or not (0 <= self.occupied_units <= self.total_units):
            raise ValueError("invalid unit counts")

    @property
    def vacant_units(self) -> int:
        return self.total_units - self.occupied_units

    @property
    def occupancy_rate(self) -> Optional[Decimal]:
        if self.total_units == 0:
            return None
        return Decimal(self.occupied_units) / Decimal(self.total_units)

    @property
    def gross_potential_rent(self) -> Money:
        """만실 가정 월 임대수입(GPR)."""
        return self.avg_unit_rent * self.total_units

    @property
    def effective_rent(self) -> Money:
        """실제 월 임대수입(입주 세대 기준, EGI)."""
        return self.avg_unit_rent * self.occupied_units

    @property
    def vacancy_loss(self) -> Money:
        """공실로 인한 월 손실."""
        return self.avg_unit_rent * self.vacant_units

    @property
    def monthly_noi(self) -> Money:
        """월 순영업소득 = 실임대수입 − 운영비."""
        return self.effective_rent - self.monthly_costs

    @property
    def annual_noi(self) -> Money:
        return self.monthly_noi * 12


@dataclass(frozen=True)
class ValueUpResult:
    before: OperatingSnapshot
    after: OperatingSnapshot
    investment: Money                 # 누적 투자비
    occupancy_gain: Optional[Decimal]  # 점유율 변화(분수)
    monthly_rent_gain: Money          # 월 실임대수입 증가
    monthly_cost_change: Money        # 월 운영비 변화(음수=절감)
    monthly_noi_gain: Money           # 월 NOI 증가
    complaints_change: Optional[int]  # 민원 변화(음수=감소)
    payback_months: Optional[Decimal]  # 투자 / 월 NOI 증가
    annual_roi: Optional[Decimal]     # 연 NOI 증가 / 투자

    def to_dict(self) -> dict:
        def m(x: Money) -> str:
            return str(x.rounded().amount)
        def d(x: Optional[Decimal]) -> Optional[str]:
            return None if x is None else str(x)
        return {
            "investment": m(self.investment),
            "monthly_rent_gain": m(self.monthly_rent_gain),
            "monthly_cost_change": m(self.monthly_cost_change),
            "monthly_noi_gain": m(self.monthly_noi_gain),
            "occupancy_gain": d(self.occupancy_gain),
            "complaints_change": self.complaints_change,
            "payback_months": d(self.payback_months),
            "annual_roi": d(self.annual_roi),
        }


def compare_valueup(
    before: OperatingSnapshot,
    after: OperatingSnapshot,
    investment: Money,
) -> ValueUpResult:
    """개선 전/후 스냅샷과 투자비로 밸류업 성과를 계산한다."""
    occ_gain = None
    if before.occupancy_rate is not None and after.occupancy_rate is not None:
        occ_gain = after.occupancy_rate - before.occupancy_rate

    rent_gain = after.effective_rent - before.effective_rent
    cost_change = after.monthly_costs - before.monthly_costs
    noi_gain = after.monthly_noi - before.monthly_noi

    comp_change = None
    if before.monthly_complaints is not None and after.monthly_complaints is not None:
        comp_change = after.monthly_complaints - before.monthly_complaints

    payback = None
    annual_roi = None
    if investment.amount > 0 and noi_gain.amount > 0:
        payback = investment.amount / noi_gain.amount             # 개월
        annual_roi = (noi_gain.amount * 12) / investment.amount

    return ValueUpResult(
        before=before, after=after, investment=investment,
        occupancy_gain=occ_gain, monthly_rent_gain=rent_gain,
        monthly_cost_change=cost_change, monthly_noi_gain=noi_gain,
        complaints_change=comp_change, payback_months=payback, annual_roi=annual_roi,
    )
