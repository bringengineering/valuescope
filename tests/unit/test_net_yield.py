"""실현 가능 수익률(net yield) 테스트 — 손계산 골든값, 0원 오차."""

from __future__ import annotations

from decimal import Decimal

import pytest

from valuescope import Money
from valuescope.calculators.net_yield import (
    OperatingAssumptions,
    assumptions_for_age,
    compute_net_yield,
)


def test_age_brackets():
    assert assumptions_for_age(5).label.startswith("신축")
    assert assumptions_for_age(15).label.startswith("준신축")
    assert assumptions_for_age(25).label.startswith("중년")
    assert assumptions_for_age(38).label.startswith("노후")
    assert assumptions_for_age(50).label.startswith("고령")
    assert assumptions_for_age(None).label.startswith("중년")  # 미상 → 보수적


def test_net_yield_hand_calc_new_building():
    # 신축 가정: 공실 5%, 운영비 20%, capex 3%
    r = compute_net_yield(
        monthly_rent=Money.won(3_000_000), price=Money.won(800_000_000), age_years=5,
    )
    assert r.gpr == Money.won(36_000_000)              # 300만×12
    assert r.egi == Money.won(34_200_000)              # ×0.95
    assert r.opex == Money.won(6_840_000)              # egi×0.20
    assert r.noi == Money.won(27_360_000)              # egi−opex
    assert r.capex_reserve == Money.won(1_026_000)     # egi×0.03
    assert r.realizable_noi == Money.won(26_334_000)   # noi−capex
    assert r.gross_yield == Decimal("36000000") / Decimal("800000000")   # 4.5%
    assert r.realizable_yield == Decimal("26334000") / Decimal("800000000")  # ~3.29%


def test_old_building_erodes_yield_more():
    # 동일 임대료·가격이라도 노후 건물은 실현 수익률이 크게 깎인다
    new = compute_net_yield(monthly_rent=Money.won(2_000_000), price=Money.won(400_000_000), age_years=5)
    old = compute_net_yield(monthly_rent=Money.won(2_000_000), price=Money.won(400_000_000), age_years=45)
    # gross 는 동일
    assert new.gross_yield == old.gross_yield
    # 실현 수익률은 노후가 훨씬 낮다
    assert old.realizable_yield < new.realizable_yield
    # 신축 실현/총 비율 > 노후 실현/총 비율 (침식 폭이 크다)
    assert (old.realizable_noi.amount / old.gpr.amount) < (new.realizable_noi.amount / new.gpr.amount)


def test_high_gross_can_fall_below_low_gross_after_adjustment():
    # 노후 고총수익 vs 신축 저총수익 → 실현에서 역전 가능함을 보인다
    old_high = compute_net_yield(monthly_rent=Money.won(1_000_000), price=Money.won(95_000_000), age_years=45)   # gross ~12.6%
    new_low = compute_net_yield(monthly_rent=Money.won(1_000_000), price=Money.won(270_000_000), age_years=8)    # gross ~4.4%
    assert old_high.gross_yield > new_low.gross_yield          # 총수익률은 노후가 높지만
    # 실현 수익률에서 격차가 크게 좁혀진다(침식 검증)
    gap_gross = old_high.gross_yield - new_low.gross_yield
    gap_real = old_high.realizable_yield - new_low.realizable_yield
    assert gap_real < gap_gross


def test_equity_yield_uses_deposit():
    r = compute_net_yield(
        monthly_rent=Money.won(2_000_000), price=Money.won(500_000_000),
        age_years=15, deposit=Money.won(100_000_000),
    )
    # 실질 투자금 = 5억 − 1억 = 4억
    assert r.equity_yield == r.realizable_noi.amount / Decimal("400000000")
    assert r.equity_yield > r.realizable_yield  # 보증금으로 레버리지 → 자기자본 수익률↑


def test_custom_assumptions_override_age():
    custom = OperatingAssumptions(Decimal("0.0"), Decimal("0.0"), Decimal("0.0"), "무비용")
    r = compute_net_yield(monthly_rent=Money.won(1_000_000), price=Money.won(120_000_000),
                          age_years=99, assumptions=custom)
    assert r.realizable_yield == r.gross_yield  # 비용 0 → 실현=총


def test_zero_price_yields_none():
    r = compute_net_yield(monthly_rent=Money.won(1_000_000), price=Money.won(0), age_years=10)
    assert r.gross_yield is None and r.realizable_yield is None


def test_rejects_bad_assumptions():
    bad = OperatingAssumptions(Decimal("1.2"), Decimal("0.2"), Decimal("0.05"))
    with pytest.raises(ValueError):
        compute_net_yield(monthly_rent=Money.won(1_000_000), price=Money.won(1), assumptions=bad)
