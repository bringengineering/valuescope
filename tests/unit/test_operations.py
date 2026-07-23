"""건물 운영손익 & 밸류업 실증 엔진 테스트 (밸류업 프로젝트 예시 기반)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from valuescope import Money
from valuescope.calculators.operations import OperatingSnapshot, compare_valueup


def _before():
    return OperatingSnapshot(
        total_units=12, occupied_units=10, avg_unit_rent=Money.won(350_000),
        monthly_costs=Money.won(400_000), avg_vacancy_days=60, monthly_complaints=8,
    )


def _after():
    return OperatingSnapshot(
        total_units=12, occupied_units=11, avg_unit_rent=Money.won(350_000),
        monthly_costs=Money.won(280_000), avg_vacancy_days=30, monthly_complaints=5,
    )


def test_snapshot_derived_numbers():
    b = _before()
    assert b.vacant_units == 2
    assert b.effective_rent == Money.won(3_500_000)       # 35만×10
    assert b.gross_potential_rent == Money.won(4_200_000)  # 35만×12
    assert b.vacancy_loss == Money.won(700_000)           # 35만×2
    assert b.monthly_noi == Money.won(3_100_000)          # 350만−40만
    assert b.annual_noi == Money.won(37_200_000)
    assert b.occupancy_rate == Decimal(10) / Decimal(12)


def test_valueup_comparison_matches_hand_calc():
    r = compare_valueup(_before(), _after(), investment=Money.won(3_500_000))
    assert r.monthly_rent_gain == Money.won(350_000)      # 385만−350만
    assert r.monthly_cost_change == Money.won(-120_000)   # 28만−40만(절감)
    assert r.monthly_noi_gain == Money.won(470_000)       # 357만−310만
    assert r.complaints_change == -3
    assert r.occupancy_gain == Decimal(11) / Decimal(12) - Decimal(10) / Decimal(12)
    # 회수기간 = 투자 / 월 NOI 증가 = 350만 / 47만
    assert r.payback_months == Decimal("3500000") / Decimal("470000")
    # 연 ROI = 47만×12 / 350만
    assert r.annual_roi == Decimal("5640000") / Decimal("3500000")


def test_no_gain_gives_none_payback():
    # 투자했지만 NOI 개선 없음(솔직 공개 케이스)
    same = _before()
    r = compare_valueup(same, same, investment=Money.won(3_000_000))
    assert r.monthly_noi_gain == Money.won(0)
    assert r.payback_months is None
    assert r.annual_roi is None


def test_cost_only_improvement():
    # 임대 그대로, 수리비만 절감 → NOI 개선
    after = OperatingSnapshot(total_units=12, occupied_units=10,
                              avg_unit_rent=Money.won(350_000), monthly_costs=Money.won(250_000))
    r = compare_valueup(_before(), after, investment=Money.won(1_500_000))
    assert r.monthly_rent_gain == Money.won(0)
    assert r.monthly_noi_gain == Money.won(150_000)       # 40만−25만 절감분
    assert r.payback_months == Decimal("1500000") / Decimal("150000")  # 10개월


def test_invalid_units_rejected():
    with pytest.raises(ValueError):
        OperatingSnapshot(total_units=10, occupied_units=12, avg_unit_rent=Money.won(1),
                          monthly_costs=Money.won(0))
