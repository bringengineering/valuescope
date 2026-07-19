"""리모델링(value-add) 시뮬레이션 테스트 — 손계산 골든값과 0원 오차."""

from __future__ import annotations

from decimal import Decimal

import pytest

from valuescope import Money
from valuescope.calculators.valueadd import simulate_renovation


def test_standard_renovation_matches_hand_calc():
    r = simulate_renovation(
        monthly_rent=Money.won(3_000_000),      # 월 300만
        area_m2=Decimal("400"),
        value_before=Money.won(800_000_000),    # 8억
        cost_per_m2=Money.won(350_000),         # 35만/㎡
        rent_uplift=Decimal("0.18"),            # +18%
        opex_ratio=Decimal("0.25"),
    )
    assert r.cost == Money.won(140_000_000)               # 400×35만
    assert r.monthly_rent_after == Money.won(3_540_000)   # ×1.18
    assert r.annual_noi_before == Money.won(27_000_000)   # 300만×12×0.75
    assert r.annual_noi_after == Money.won(31_860_000)
    assert r.value_after == Money.won(944_000_000)        # 8억×1.18
    assert r.value_uplift == Money.won(144_000_000)
    assert r.net_gain == Money.won(4_000_000)             # 1.44억 − 1.4억
    assert r.cap_rate == Decimal("0.03375")               # 2700만/8억
    # ROI = 400만 / 1.4억
    assert r.roi == Decimal("4000000") / Decimal("140000000")


def test_high_value_cheap_uplift_is_strongly_accretive():
    # 값비싼 건물 + 저렴하지만 효과 큰 리모델링 → 순증분 큼
    r = simulate_renovation(
        monthly_rent=Money.won(5_000_000),
        area_m2=Decimal("300"),
        value_before=Money.won(1_200_000_000),   # 12억
        cost_per_m2=Money.won(150_000),          # 15만/㎡ = 4,500만
        rent_uplift=Decimal("0.20"),             # +20%
    )
    assert r.cost == Money.won(45_000_000)
    assert r.value_uplift == Money.won(240_000_000)       # 12억×0.20
    assert r.net_gain == Money.won(195_000_000)           # 2.4억 − 4,500만
    assert r.roi is not None and r.roi > Decimal("4")     # 400%+ ROI


def test_payback_years_from_delta_noi():
    r = simulate_renovation(
        monthly_rent=Money.won(3_000_000),
        area_m2=Decimal("400"),
        value_before=Money.won(800_000_000),
        cost_per_m2=Money.won(350_000),
        rent_uplift=Decimal("0.18"),
    )
    # ΔNOI = 4,860,000/년, cost = 140,000,000 → 회수 ≈ 28.8년
    assert r.payback_years == Decimal("140000000") / Decimal("4860000")


def test_zero_cost_returns_none_roi():
    r = simulate_renovation(
        monthly_rent=Money.won(3_000_000),
        area_m2=Decimal("400"),
        value_before=Money.won(800_000_000),
        cost_per_m2=Money.won(0),
        rent_uplift=Decimal("0.10"),
    )
    assert r.roi is None
    assert r.payback_years is not None


def test_zero_value_before_keeps_value_and_no_cap():
    r = simulate_renovation(
        monthly_rent=Money.won(1_000_000),
        area_m2=Decimal("100"),
        value_before=Money.won(0),
        cost_per_m2=Money.won(300_000),
        rent_uplift=Decimal("0.15"),
    )
    assert r.cap_rate is None
    assert r.value_after == Money.won(0)
    assert r.value_uplift == Money.won(0)
    assert r.net_gain == Money.won(-30_000_000)   # 순전히 −투입비


def test_no_uplift_means_uplift_equals_cost_loss():
    r = simulate_renovation(
        monthly_rent=Money.won(2_000_000),
        area_m2=Decimal("200"),
        value_before=Money.won(500_000_000),
        cost_per_m2=Money.won(200_000),
        rent_uplift=Decimal("0"),
    )
    assert r.value_uplift == Money.won(0)
    assert r.net_gain == Money.won(-40_000_000)   # 투입 4,000만 손실
    assert r.roi == Decimal("-1")


def test_rejects_bad_assumptions():
    with pytest.raises(ValueError):
        simulate_renovation(
            monthly_rent=Money.won(1_000_000), area_m2=Decimal("100"),
            value_before=Money.won(100_000_000), cost_per_m2=Money.won(100_000),
            rent_uplift=Decimal("0.1"), opex_ratio=Decimal("1.5"),
        )


# --- 상세 밸류애드 분석 -----------------------------------------------------
from valuescope.calculators.valueadd import analyze_renovation  # noqa: E402


def test_analyze_renovation_hand_calc():
    # 노후(35년) → 표준 리모델링으로 유효 15년, 임대 +18%
    r = analyze_renovation(
        monthly_rent=Money.won(3_000_000), area_m2=Decimal("400"),
        value_before=Money.won(800_000_000), cost_per_m2=Money.won(350_000),
        rent_uplift=Decimal("0.18"), age_before=35, age_after=15, hold_years=5,
    )
    assert r.cost == Money.won(140_000_000)
    assert r.annual_rent_gain == Money.won(6_480_000)          # (354−300)만×12
    assert r.value_after == Money.won(944_000_000)
    assert r.value_gain == Money.won(144_000_000)
    # 실현 순현금: 노후 15,660,000 → 리모델링후 27,259,416
    assert r.net_noi_before == Money.won(15_660_000)
    assert r.net_noi_after == Money.won(27_259_416)
    assert r.annual_net_gain == Money.won(11_599_416)
    assert r.net_gain == Money.won(4_000_000)                  # 가치 관점 순증분
    # 투입 대비 임대수익 ROI가 가치 ROI보다 크다(노후개선 효과)
    assert r.income_roi > r.value_roi
    # 리모델링이 실현 수익률을 끌어올린다
    assert r.realized_yield_after > r.realized_yield_before
    # 5년 종합수익 = 가치상승분 + 5×연실현증가 − 투입
    assert r.total_profit == Money.won(144_000_000) + Money.won(11_599_416) * 5 - Money.won(140_000_000)


def test_analyze_income_roi_formula():
    r = analyze_renovation(
        monthly_rent=Money.won(2_000_000), area_m2=Decimal("300"),
        value_before=Money.won(500_000_000), cost_per_m2=Money.won(200_000),
        rent_uplift=Decimal("0.15"), age_before=40, age_after=20,
    )
    assert r.income_roi == r.annual_net_gain.amount / r.cost.amount
    assert r.payback_years == r.cost.amount / r.annual_net_gain.amount


def test_analyze_zero_cost_none_roi():
    r = analyze_renovation(
        monthly_rent=Money.won(1_000_000), area_m2=Decimal("100"),
        value_before=Money.won(200_000_000), cost_per_m2=Money.won(0),
        rent_uplift=Decimal("0.1"), age_before=30, age_after=20,
    )
    assert r.value_roi is None and r.income_roi is None
