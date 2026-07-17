"""세움터/건축HUB 세부 대장 커넥터 테스트 (mock http_get, 네트워크 없음)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from valuescope import Money
from valuescope.connectors import building_ledgers as bl


def _payload(item: dict, total: int = 1) -> str:
    return json.dumps({
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {"items": {"item": item}, "totalCount": total,
                     "numOfRows": 100, "pageNo": 1},
        }
    })


EXPOS = {
    "newPlatPlc": "강원특별자치도 원주시 로아노크로 30-3 (무실동)",
    "platPlc": "강원특별자치도 원주시 무실동 438번지",
    "bldNm": "봉화산 포레스트힐", "dongNm": "", "hoNm": "405호",
    "flrGbCdNm": "지상", "flrNo": "4", "mgmBldrgstPk": "11341100387560",
    "crtnDay": "20221112",
}
FLOOR = {
    "flrGbCdNm": "지하", "flrNo": "1", "flrNoNm": "지1층",
    "strctCdNm": "철근콘크리트구조", "mainPurpsCdNm": "자치단체청사",
    "etcPurps": "지하주차장", "area": "10467.81", "mainAtchGbCdNm": "부속건축물",
    "mgmBldrgstPk": "1134126174", "crtnDay": "20221112",
}
SEPTIC = {"modeCdNm": "부패탱크방법", "capaPsper": "5100",
          "mgmBldrgstPk": "1134126177", "crtnDay": "20221112"}
HSPRC = {"newPlatPlc": "강원특별자치도 원주시 시청로 64 (무실동)", "bldNm": "요진보네르카운티",
         "hsprc": "151000000", "stdDay": "20120101",
         "mgmBldrgstPk": "11341103259", "crtnDay": "20221112"}
ZONE = {"jijiguGbCdNm": "용도지역코드", "jijiguCdNm": "자연녹지지역",
        "reprYn": "1", "etcJijigu": "", "mgmBldrgstPk": "1134126174", "crtnDay": "20221112"}


def test_expos_unit_parses_ho_and_source():
    units = bl.fetch_expos_units("51130", "11500", service_key="K", http_get=lambda u: _payload(EXPOS))
    u = units[0]
    assert u.ho == "405호"
    assert u.floor_kind == "지상"
    assert u.floor_no == 4
    assert u.bld_name == "봉화산 포레스트힐"
    assert u.address.startswith("강원특별자치도 원주시 로아노크로")  # 도로명 우선
    assert u.mgm_pk == "11341100387560"        # 원본 식별자
    assert u.source_day == "20221112"          # 기준일
    assert u.confidence == "A"                 # 공식 대장


def test_floor_outline_area_is_decimal():
    floors = bl.fetch_floor_outlines("51130", "11500", service_key="K", http_get=lambda u: _payload(FLOOR))
    f = floors[0]
    assert f.area_m2 == Decimal("10467.81")
    assert f.main_purpose == "자치단체청사"
    assert f.etc_purpose == "지하주차장"
    assert f.attached == "부속건축물"
    assert f.floor_name == "지1층"


def test_septic_capacity_int():
    s = bl.fetch_septic("51130", "11500", service_key="K", http_get=lambda u: _payload(SEPTIC))[0]
    assert s.mode == "부패탱크방법"
    assert s.capacity_persons == 5100


def test_housing_price_is_money():
    h = bl.fetch_housing_prices("51130", "11500", service_key="K", http_get=lambda u: _payload(HSPRC))[0]
    assert h.price == Money.won(151_000_000)
    assert h.std_day == "20120101"
    assert h.bld_name == "요진보네르카운티"


def test_zone_representative_flag():
    z = bl.fetch_zones("51130", "11500", service_key="K", http_get=lambda u: _payload(ZONE))[0]
    assert z.zone_name == "자연녹지지역"
    assert z.is_representative is True


def test_missing_values_stay_none():
    sparse = {"hoNm": "", "flrNo": "", "mgmBldrgstPk": "X", "crtnDay": ""}
    u = bl.parse_expos(sparse)
    assert u.floor_no is None
    assert u.ho == ""
    h = bl.parse_housing_price({"hsprc": "", "mgmBldrgstPk": "X"})
    assert h.price is None


def test_empty_items_returns_empty():
    empty = json.dumps({"response": {"header": {"resultCode": "00"},
                                     "body": {"items": "", "totalCount": 0}}})
    assert bl.fetch_zones("51130", "11500", service_key="K", http_get=lambda u: empty) == []


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    with pytest.raises(bl.BuildingLedgerError):
        bl.fetch_zones("51130", "11500", http_get=lambda u: _payload(ZONE))
