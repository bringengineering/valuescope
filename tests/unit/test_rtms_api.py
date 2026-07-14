"""RTMS 실거래가 API 커넥터 테스트 (mock http_get, 실제 네트워크 없이)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from valuescope import Money
from valuescope.connectors import rtms_api as r

RENT_XML = """<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
<body><items>
<item><sggCd>51130</sggCd><umdNm>무실동</umdNm><totalFloorAr>67</totalFloorAr>
<dealYear>2025</dealYear><dealMonth>6</dealMonth><dealDay>5</dealDay>
<deposit>4,000</deposit><monthlyRent>40</monthlyRent><buildYear>2016</buildYear></item>
<item><sggCd>51130</sggCd><umdNm>단계동</umdNm><totalFloorAr>50</totalFloorAr>
<dealYear>2025</dealYear><dealMonth>6</dealMonth><dealDay>7</dealDay>
<deposit>27,000</deposit><monthlyRent>0</monthlyRent><buildYear>2011</buildYear></item>
</items><totalCount>2</totalCount><numOfRows>1000</numOfRows><pageNo>1</pageNo></body></response>"""

TRADE_XML = """<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
<body><items>
<item><sggCd>51130</sggCd><umdNm>무실동</umdNm><totalFloorAr>120</totalFloorAr>
<dealYear>2025</dealYear><dealMonth>6</dealMonth><dealDay>3</dealDay>
<dealAmount>35,000</dealAmount><buildYear>2018</buildYear></item>
</items><totalCount>1</totalCount><numOfRows>1000</numOfRows><pageNo>1</pageNo></body></response>"""

ERR_XML = """<response><header><resultCode>30</resultCode>
<resultMsg>SERVICE KEY IS NOT REGISTERED ERROR</resultMsg></header></response>"""


def test_rent_parses_deposit_and_monthly():
    txns = r.fetch_sh_rent("51130", "202506", service_key="K", http_get=lambda u: RENT_XML)
    musil = [t for t in txns if t.sigungu == "무실동"][0]
    assert musil.rent_type == "월세"
    assert musil.deposit_krw() == Money.won(40_000_000)
    assert musil.monthly_rent_krw() == Money.won(400_000)
    assert musil.area_m2 == Decimal("67")
    assert musil.house_type == "단독다가구"


def test_rent_detects_jeonse():
    txns = r.fetch_sh_rent("51130", "202506", service_key="K", http_get=lambda u: RENT_XML)
    jeonse = [t for t in txns if t.sigungu == "단계동"][0]
    assert jeonse.rent_type == "전세"
    assert jeonse.deposit_krw() == Money.won(270_000_000)


def test_trade_parses_amount():
    txns = r.fetch_sh_trade("51130", "202506", service_key="K", http_get=lambda u: TRADE_XML)
    assert txns[0].kind == "sale"
    assert txns[0].price_krw() == Money.won(350_000_000)
    assert txns[0].area_m2 == Decimal("120")


def test_url_contains_params():
    seen = {}
    def fake(url):
        seen["url"] = url
        return RENT_XML
    r.fetch_sh_rent("51130", "202506", service_key="MYKEY", http_get=fake)
    assert "LAWD_CD=51130" in seen["url"]
    assert "DEAL_YMD=202506" in seen["url"]
    assert "serviceKey=MYKEY" in seen["url"]


def test_error_result_code_raises():
    with pytest.raises(r.RtmsError):
        r.fetch_sh_rent("51130", "202506", service_key="K", http_get=lambda u: ERR_XML)


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    with pytest.raises(r.RtmsError):
        r.fetch_sh_rent("51130", "202506", http_get=lambda u: RENT_XML)


def test_empty_items_returns_empty():
    empty = "<response><header><resultCode>00</resultCode></header><body><items></items></body></response>"
    assert r.fetch_sh_rent("51130", "202506", service_key="K", http_get=lambda u: empty) == []
