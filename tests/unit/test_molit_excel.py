"""국토부 실거래가 엑셀 커넥터 테스트 (합성 행 기반, 실제 파일 불필요)."""

from __future__ import annotations

from decimal import Decimal

from valuescope import Money
from valuescope.connectors.molit_excel import parse_transactions

SALE_ROWS = [
    ["□ 안내문구"],
    ["NO", "시군구", "번지", "본번", "부번", "단지명", "전용면적(㎡)", "계약년월",
     "계약일", "거래금액(만원)", "동", "층", "건축년도", "도로명", "주택유형"],
    ["1", "강원특별자치도 원주시 무실동", "1180", "1180", "0", "무실주공4단지", "84.52",
     "202507", "5", "22,100", "401", "10", "1998", "무실로 1", "아파트"],
    ["2", "강원특별자치도 원주시 단계동", "500", "500", "0", "단계다가구", "60.0",
     "202507", "7", "38,500", "", "3", "2015", "단계로 2", "단독다가구"],
]

RENT_ROWS = [
    ["□ 안내문구"],
    ["NO", "시군구", "번지", "본번", "부번", "단지명", "전월세구분", "전용면적(㎡)",
     "계약년월", "계약일", "보증금(만원)", "월세금(만원)", "층", "건축년도", "도로명", "주택유형"],
    ["1", "강원특별자치도 원주시 무실동", "1200", "1200", "0", "무실빌라", "월세", "30.0",
     "202507", "3", "1,000", "45", "2", "2010", "무실로 3", "연립다세대"],
    ["2", "강원특별자치도 원주시 무실동", "1201", "1201", "0", "무실빌라", "전세", "40.0",
     "202507", "9", "27,000", "0", "3", "2010", "무실로 3", "연립다세대"],
]


def test_detects_sale_kind():
    p = parse_transactions(SALE_ROWS)
    assert p.kind == "sale"
    assert len(p.transactions) == 2


def test_sale_price_and_area():
    t = parse_transactions(SALE_ROWS).transactions[0]
    assert t.building_name == "무실주공4단지"
    assert t.area_m2 == Decimal("84.52")
    assert t.price_manwon == Decimal("22100")
    assert t.price_krw() == Money.won(221_000_000)  # 만원 → 원


def test_detects_rent_kind():
    p = parse_transactions(RENT_ROWS)
    assert p.kind == "rent"
    assert len(p.transactions) == 2


def test_rent_monthly_and_jeonse():
    txns = parse_transactions(RENT_ROWS).transactions
    wolse, jeonse = txns[0], txns[1]
    assert wolse.rent_type == "월세"
    assert wolse.deposit_krw() == Money.won(10_000_000)
    assert wolse.monthly_rent_krw() == Money.won(450_000)
    assert jeonse.rent_type == "전세"
    assert jeonse.deposit_krw() == Money.won(270_000_000)
    assert jeonse.monthly_rent_manwon == Decimal("0")


def test_by_dong_filter():
    p = parse_transactions(SALE_ROWS)
    assert len(p.by_dong("무실동")) == 1
    assert len(p.by_dong("단계동")) == 1


def test_house_type_captured():
    txns = parse_transactions(SALE_ROWS).transactions
    assert txns[0].house_type == "아파트"
    assert txns[1].house_type == "단독다가구"


def test_column_order_independence():
    # 열 순서를 바꿔도 헤더명으로 매핑되어야 한다
    rows = [
        ["NO", "거래금액(만원)", "시군구", "전용면적(㎡)", "단지명"],
        ["1", "50,000", "강원 원주시 무실동", "59.9", "테스트"],
    ]
    t = parse_transactions(rows).transactions[0]
    assert t.price_manwon == Decimal("50000")
    assert t.building_name == "테스트"
    assert t.area_m2 == Decimal("59.9")


def test_skips_blank_and_non_data_rows():
    p = parse_transactions(SALE_ROWS)
    # 안내문구/빈행은 거래로 잡히지 않음
    assert all(t.sigungu for t in p.transactions)
