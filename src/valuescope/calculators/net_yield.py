"""실현 가능 수익률(net yield) — 공실·운영비·노후 자본지출을 반영.

총수익률(gross = 임대료×12÷가격)은 "허수"다. 실제로 손에 남는 수익률은
공실 손실, 운영비(관리·수선·세금·보험), 그리고 노후 건물의 자본지출(capex)을
빼야 나온다. 노후할수록 이 셋이 모두 커지므로, 건물 연식으로 가정을 잡는다.

원칙(CLAUDE.md):
- 금액은 Decimal(Money). float 금지.
- 공실률·운영비율·자본지출률은 '가정'이다(신뢰도 D). 엔진은 계산만 하고
  임의 생성하지 않는다. 호출자가 실제값을 주면 그것을 쓴다.
- 연식 기반 기본 가정은 한국 다가구·원룸의 통상 rule-of-thumb이며 확정이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ..domain.money import Money

ONE = Decimal(1)


@dataclass(frozen=True)
class OperatingAssumptions:
    """운영 가정(모두 분수). 신뢰도 D — 실제값으로 대체 권장."""
    vacancy_rate: Decimal      # 공실률
    opex_ratio: Decimal        # 운영비율(유효총소득 대비)
    capex_rate: Decimal        # 자본지출 충당률(유효총소득 대비)
    label: str = ""
    confidence: str = "D"


# 연식 구간별 기본 가정 — 노후할수록 공실·운영비·자본지출 ↑
_AGE_TABLE = (
    (10, OperatingAssumptions(Decimal("0.05"), Decimal("0.20"), Decimal("0.03"), "신축(≤10년)")),
    (20, OperatingAssumptions(Decimal("0.07"), Decimal("0.25"), Decimal("0.06"), "준신축(11–20년)")),
    (30, OperatingAssumptions(Decimal("0.10"), Decimal("0.30"), Decimal("0.10"), "중년(21–30년)")),
    (40, OperatingAssumptions(Decimal("0.13"), Decimal("0.35"), Decimal("0.15"), "노후(31–40년)")),
)
_OLDEST = OperatingAssumptions(Decimal("0.16"), Decimal("0.40"), Decimal("0.20"), "고령(>40년)")


def assumptions_for_age(age_years: Optional[int]) -> OperatingAssumptions:
    """건물 연식(년)에 맞는 기본 운영 가정을 반환. 연식 미상이면 중년 가정."""
    if age_years is None:
        return _AGE_TABLE[2][1]  # 보수적으로 중년 가정
    for threshold, a in _AGE_TABLE:
        if age_years <= threshold:
            return a
    return _OLDEST


@dataclass(frozen=True)
class NetYieldResult:
    gpr: Money                 # 연 잠재총임대료(gross potential rent)
    egi: Money                 # 유효총소득(공실 차감)
    opex: Money                # 운영비
    noi: Money                 # 순영업소득(egi − opex)
    capex_reserve: Money       # 자본지출 충당
    realizable_noi: Money      # 실현 순현금(noi − capex)
    gross_yield: Optional[Decimal]      # gpr / price (허수)
    noi_yield: Optional[Decimal]        # noi / price
    realizable_yield: Optional[Decimal]  # realizable_noi / price (실현)
    equity_yield: Optional[Decimal]     # realizable_noi / (price − deposit)
    assumptions: OperatingAssumptions

    def to_dict(self) -> dict:
        def m(x: Money) -> str:
            return str(x.rounded().amount)
        def d(x: Optional[Decimal]) -> Optional[str]:
            return None if x is None else str(x)
        return {
            "gpr": m(self.gpr), "egi": m(self.egi), "opex": m(self.opex),
            "noi": m(self.noi), "capex_reserve": m(self.capex_reserve),
            "realizable_noi": m(self.realizable_noi),
            "gross_yield": d(self.gross_yield), "noi_yield": d(self.noi_yield),
            "realizable_yield": d(self.realizable_yield), "equity_yield": d(self.equity_yield),
            "assumptions": {
                "vacancy_rate": str(self.assumptions.vacancy_rate),
                "opex_ratio": str(self.assumptions.opex_ratio),
                "capex_rate": str(self.assumptions.capex_rate),
                "label": self.assumptions.label,
                "confidence": self.assumptions.confidence,
            },
        }


def _scale(m: Money, f: Decimal) -> Money:
    return Money(m.amount * f, m.currency)


def _ratio(num: Money, den: Money) -> Optional[Decimal]:
    return None if den.amount == 0 else num.amount / den.amount


def compute_net_yield(
    *,
    monthly_rent: Money,
    price: Money,
    age_years: Optional[int] = None,
    deposit: Optional[Money] = None,
    assumptions: Optional[OperatingAssumptions] = None,
) -> NetYieldResult:
    """월 임대료·매매가·연식으로 실현 가능 수익률을 계산한다.

    assumptions 미지정 시 age_years 기반 기본 가정을 쓴다.
    equity_yield 는 보증금을 뺀 실질 투자금 대비 수익률(보증금 있을 때만).
    """
    a = assumptions or assumptions_for_age(age_years)
    if not (0 <= a.vacancy_rate < 1 and 0 <= a.opex_ratio < 1 and a.capex_rate >= 0):
        raise ValueError("invalid operating assumptions")

    gpr = _scale(monthly_rent, Decimal(12))
    egi = _scale(gpr, ONE - a.vacancy_rate)
    opex = _scale(egi, a.opex_ratio)
    noi = egi - opex
    capex = _scale(egi, a.capex_rate)
    realizable = noi - capex

    equity_yield = None
    if deposit is not None:
        equity = price - deposit
        if equity.amount > 0:
            equity_yield = realizable.amount / equity.amount

    return NetYieldResult(
        gpr=gpr, egi=egi, opex=opex, noi=noi,
        capex_reserve=capex, realizable_noi=realizable,
        gross_yield=_ratio(gpr, price),
        noi_yield=_ratio(noi, price),
        realizable_yield=_ratio(realizable, price),
        equity_yield=equity_yield,
        assumptions=a,
    )
