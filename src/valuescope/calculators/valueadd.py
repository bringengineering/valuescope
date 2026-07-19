"""Value-add(리모델링) 시뮬레이션 — 투입비 대비 가치·수익 개선.

BRING 운영모델의 3단계(가치상승)를 뒷받침한다. "싸게 사서 → 고쳐서 →
가치를 올린다"를 결정론적 숫자로 보여준다. 공식은 docs/formulas.md 참조.

원칙(CLAUDE.md):
- 금액은 모두 Decimal(Money). float 금지.
- 임대료 상승률·투입 단가·공실·비용률은 '가정'이며 호출자가 주입한다.
  엔진은 가정을 계산할 뿐, 임의로 만들어내지 않는다.
- 리모델링 후 자본환원율(cap rate)은 현재가치에서 역산한 값을 그대로 쓴다
  (cap 압축을 임의로 가정해 가치를 부풀리지 않는다).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ..domain.money import Money
from .net_yield import compute_net_yield

ONE = Decimal(1)


@dataclass(frozen=True)
class RenovationResult:
    cost: Money                       # 리모델링 투입비
    monthly_rent_before: Money
    monthly_rent_after: Money
    annual_noi_before: Money
    annual_noi_after: Money
    value_before: Money
    value_after: Money
    value_uplift: Money               # 후가치 − 전가치
    net_gain: Money                   # value_uplift − cost
    roi: Optional[Decimal]            # net_gain / cost (분수, None=투입 0)
    payback_years: Optional[Decimal]  # cost / ΔNOI(연) (None=ΔNOI 0)
    cap_rate: Optional[Decimal]       # 현재가치 역산 cap (분수)

    def to_dict(self) -> dict:
        def m(x: Money) -> str:
            return str(x.rounded().amount)
        def d(x: Optional[Decimal]) -> Optional[str]:
            return None if x is None else str(x)
        return {
            "cost": m(self.cost),
            "monthly_rent_before": m(self.monthly_rent_before),
            "monthly_rent_after": m(self.monthly_rent_after),
            "annual_noi_before": m(self.annual_noi_before),
            "annual_noi_after": m(self.annual_noi_after),
            "value_before": m(self.value_before),
            "value_after": m(self.value_after),
            "value_uplift": m(self.value_uplift),
            "net_gain": m(self.net_gain),
            "roi": d(self.roi),
            "payback_years": d(self.payback_years),
            "cap_rate": d(self.cap_rate),
        }


def _scale(money: Money, factor: Decimal) -> Money:
    return Money(money.amount * factor, money.currency)


def simulate_renovation(
    *,
    monthly_rent: Money,
    area_m2: Decimal,
    value_before: Money,
    cost_per_m2: Money,
    rent_uplift: Decimal,
    opex_ratio: Decimal = Decimal("0.25"),
) -> RenovationResult:
    """리모델링 전/후 가치·수익을 계산한다.

    Args:
        monthly_rent: 현재 월 임대수입(건물 전체).
        area_m2: 연면적(㎡). 투입비 산정 기준.
        value_before: 현재(추정) 시장가치.
        cost_per_m2: ㎡당 리모델링 투입 단가(가정).
        rent_uplift: 리모델링 후 임대료 상승률(분수, 예 0.18 = +18%).
        opex_ratio: 운영비율(분수). NOI = 임대수입 × (1 − opex).

    Returns:
        RenovationResult. 후 cap rate는 현재가치 역산값을 그대로 적용한다.
    """
    if area_m2 < 0 or rent_uplift < -1 or not (0 <= opex_ratio < 1):
        raise ValueError("invalid renovation assumptions")

    cost = _scale(cost_per_m2, area_m2)
    rent_after = _scale(monthly_rent, ONE + rent_uplift)

    noi_before = _scale(monthly_rent, Decimal(12) * (ONE - opex_ratio))
    noi_after = _scale(rent_after, Decimal(12) * (ONE - opex_ratio))

    # 현재가치에서 역산한 cap rate를 후가치에 그대로 적용(가치 부풀림 방지).
    cap = None
    if value_before.amount > 0:
        cap = noi_before.amount / value_before.amount

    if cap and cap > 0:
        value_after = Money(noi_after.amount / cap, value_before.currency)
    else:  # 현재가치/NOI가 0이면 가치 상승 산정 불가 → 전가치 유지
        value_after = value_before

    value_uplift = value_after - value_before
    net_gain = value_uplift - cost

    roi = None
    if cost.amount > 0:
        roi = net_gain.amount / cost.amount

    delta_noi = noi_after.amount - noi_before.amount
    payback_years = None
    if delta_noi > 0:
        payback_years = cost.amount / delta_noi

    return RenovationResult(
        cost=cost,
        monthly_rent_before=monthly_rent,
        monthly_rent_after=rent_after,
        annual_noi_before=noi_before,
        annual_noi_after=noi_after,
        value_before=value_before,
        value_after=value_after,
        value_uplift=value_uplift,
        net_gain=net_gain,
        roi=roi,
        payback_years=payback_years,
        cap_rate=cap,
    )


# --- 상세 밸류애드 분석 (투입 대비 다각도 수익) -----------------------------
@dataclass(frozen=True)
class RenovationAnalysis:
    """리모델링 투입 대비 상세 분석.

    총수익률이 아니라 실현(공실·운영비·노후 자본지출 반영) 기준으로,
    리모델링이 (1) 임대료를 올리고 (2) 노후 운영부담을 줄이는 두 효과를
    모두 반영한다. 후자는 age_after < age_before 로 표현한다.
    """
    cost: Money
    rent_before: Money
    rent_after: Money
    annual_rent_gain: Money            # 연 임대수입 증가(총, 공실전)
    value_before: Money
    value_after: Money
    value_gain: Money                  # 가치 상승분
    value_gain_pct: Optional[Decimal]  # 가치 상승률(분수)
    net_noi_before: Money              # 실현 순현금(연)
    net_noi_after: Money
    annual_net_gain: Money             # 실현 순현금 증가(연)
    net_gain: Money                    # 가치상승분 − 투입 (순증분)
    value_roi: Optional[Decimal]       # 순증분 / 투입 (가치 관점 ROI)
    income_roi: Optional[Decimal]      # 연 실현순현금증가 / 투입 (투입금 연수익률)
    payback_years: Optional[Decimal]   # 투입 / 연 실현순현금증가
    realized_yield_before: Optional[Decimal]
    realized_yield_after: Optional[Decimal]
    hold_years: int
    total_profit: Money                # 가치상승분 + hold년 누적 실현순현금증가 − 투입
    total_roi: Optional[Decimal]       # total_profit / 투입

    def to_dict(self) -> dict:
        def m(x: Money) -> str:
            return str(x.rounded().amount)
        def d(x: Optional[Decimal]) -> Optional[str]:
            return None if x is None else str(x)
        return {k: (m(v) if isinstance(v, Money) else d(v) if isinstance(v, Decimal) else v)
                for k, v in self.__dict__.items()}


def analyze_renovation(
    *,
    monthly_rent: Money,
    area_m2: Decimal,
    value_before: Money,
    cost_per_m2: Money,
    rent_uplift: Decimal,
    age_before: Optional[int] = None,
    age_after: Optional[int] = None,
    hold_years: int = 5,
) -> RenovationAnalysis:
    """리모델링 투입 대비 상세 수익을 계산한다.

    age_after 는 리모델링 후 '유효 노후'(운영부담 개선 반영). 미지정 시 age_before.
    가치는 동일 cap 모델(가치 = 가치_before × (1+상승률))을 따른다.
    """
    if area_m2 < 0 or rent_uplift < -1 or hold_years < 0:
        raise ValueError("invalid renovation inputs")

    cost = _scale(cost_per_m2, area_m2)
    rent_after = _scale(monthly_rent, ONE + rent_uplift)
    annual_rent_gain = _scale(rent_after - monthly_rent, Decimal(12))

    value_after = _scale(value_before, ONE + rent_uplift)
    value_gain = value_after - value_before
    value_gain_pct = (value_gain.amount / value_before.amount) if value_before.amount > 0 else None

    nb = compute_net_yield(monthly_rent=monthly_rent, price=value_before, age_years=age_before)
    na = compute_net_yield(monthly_rent=rent_after, price=value_after,
                           age_years=age_after if age_after is not None else age_before)
    annual_net_gain = na.realizable_noi - nb.realizable_noi

    net_gain = value_gain - cost
    value_roi = (net_gain.amount / cost.amount) if cost.amount > 0 else None
    income_roi = (annual_net_gain.amount / cost.amount) if cost.amount > 0 else None
    payback = (cost.amount / annual_net_gain.amount) if annual_net_gain.amount > 0 else None

    total_profit = value_gain + _scale(annual_net_gain, Decimal(hold_years)) - cost
    total_roi = (total_profit.amount / cost.amount) if cost.amount > 0 else None

    return RenovationAnalysis(
        cost=cost, rent_before=monthly_rent, rent_after=rent_after,
        annual_rent_gain=annual_rent_gain,
        value_before=value_before, value_after=value_after,
        value_gain=value_gain, value_gain_pct=value_gain_pct,
        net_noi_before=nb.realizable_noi, net_noi_after=na.realizable_noi,
        annual_net_gain=annual_net_gain, net_gain=net_gain,
        value_roi=value_roi, income_roi=income_roi, payback_years=payback,
        realized_yield_before=nb.realizable_yield, realized_yield_after=na.realizable_yield,
        hold_years=hold_years, total_profit=total_profit, total_roi=total_roi,
    )
