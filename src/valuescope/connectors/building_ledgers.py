"""세움터/건축HUB 세부 대장 커넥터.

표제부(building_registry) 옆에 붙는 세부 건축물대장들:

- 전유부(getBrExposInfo)      — 집합건물 호실 대장 → 운영대행 호별 관리
- 층별개요(getBrFlrOulnInfo)  — 층별 용도·면적 → 시설물 대장
- 오수정화(getBrWclfInfo)     — 정화조 → 유지관리 점검
- 공시가(getBrHsprcInfo)      — 공동주택가격 → 세금·담보가치 검증
- 지역지구(getBrJijiguInfo)   — 용도지역 → 용적률·재건축 여지

모두 공식 건축물대장이므로 신뢰등급 A. 원천 시스템은 세움터(eais.go.kr)이며
data.go.kr 건축HUB(BldRgstHubService)로 개방된다.

원칙(CLAUDE.md #3): 외부 데이터에 출처·기준일·원본식별자·신뢰등급을 저장한다.
service_key 미지정 시 환경변수 DATA_GO_KR_SERVICE_KEY 를 사용한다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from ..domain.money import Money
from .building_registry import (
    BLD_BASE,
    _default_http_get,
    _items_from_response,
    build_title_url,
)

CONFIDENCE = "A"  # 공식 건축물대장
SOURCE = "건축HUB(세움터) BldRgstHubService"


class BuildingLedgerError(RuntimeError):
    """건축HUB 세부 대장 API 오류."""


def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _int(v) -> Optional[int]:
    d = _dec(v)
    return int(d) if d is not None else None


# --- 데이터 타입 ------------------------------------------------------------
@dataclass(frozen=True)
class ExposUnit:
    """전유부 — 집합건물 호실 대장 한 줄."""
    address: str
    bld_name: str
    dong: str
    ho: str
    floor_kind: str            # 지상/지하
    floor_no: Optional[int]
    mgm_pk: str                # 원본 식별자
    source_day: str            # 기준일(crtnDay)
    confidence: str = CONFIDENCE


@dataclass(frozen=True)
class FloorOutline:
    """층별개요 — 시설물 층별 용도·면적."""
    floor_kind: str
    floor_no: Optional[int]
    floor_name: str
    structure: str
    main_purpose: str
    etc_purpose: str
    area_m2: Optional[Decimal]
    attached: str              # 주건축물/부속건축물
    mgm_pk: str
    source_day: str
    confidence: str = CONFIDENCE


@dataclass(frozen=True)
class SepticFacility:
    """오수정화시설 — 정화조 대장."""
    mode: str
    capacity_persons: Optional[int]  # 처리대상 인용(명)
    mgm_pk: str
    source_day: str
    confidence: str = CONFIDENCE


@dataclass(frozen=True)
class HousingPrice:
    """공동주택/개별 공시가격."""
    address: str
    bld_name: str
    price: Optional[Money]     # 공시가격(원)
    std_day: str               # 공시 기준일(stdDay)
    mgm_pk: str
    source_day: str
    confidence: str = CONFIDENCE


@dataclass(frozen=True)
class ZoneDistrict:
    """지역지구구역 — 용도지역/지구."""
    zone_kind: str
    zone_name: str
    is_representative: bool
    etc: str
    mgm_pk: str
    source_day: str
    confidence: str = CONFIDENCE


# --- 파서 -------------------------------------------------------------------
def parse_expos(it: dict) -> ExposUnit:
    return ExposUnit(
        address=_s(it.get("newPlatPlc")) or _s(it.get("platPlc")),
        bld_name=_s(it.get("bldNm")),
        dong=_s(it.get("dongNm")),
        ho=_s(it.get("hoNm")),
        floor_kind=_s(it.get("flrGbCdNm")),
        floor_no=_int(it.get("flrNo")),
        mgm_pk=_s(it.get("mgmBldrgstPk")),
        source_day=_s(it.get("crtnDay")),
    )


def parse_floor(it: dict) -> FloorOutline:
    return FloorOutline(
        floor_kind=_s(it.get("flrGbCdNm")),
        floor_no=_int(it.get("flrNo")),
        floor_name=_s(it.get("flrNoNm")),
        structure=_s(it.get("strctCdNm")),
        main_purpose=_s(it.get("mainPurpsCdNm")),
        etc_purpose=_s(it.get("etcPurps")),
        area_m2=_dec(it.get("area")),
        attached=_s(it.get("mainAtchGbCdNm")),
        mgm_pk=_s(it.get("mgmBldrgstPk")),
        source_day=_s(it.get("crtnDay")),
    )


def parse_septic(it: dict) -> SepticFacility:
    return SepticFacility(
        mode=_s(it.get("modeCdNm")),
        capacity_persons=_int(it.get("capaPsper")),
        mgm_pk=_s(it.get("mgmBldrgstPk")),
        source_day=_s(it.get("crtnDay")),
    )


def parse_housing_price(it: dict) -> HousingPrice:
    won = _dec(it.get("hsprc"))
    return HousingPrice(
        address=_s(it.get("newPlatPlc")) or _s(it.get("platPlc")),
        bld_name=_s(it.get("bldNm")),
        price=Money.won(won) if won is not None else None,
        std_day=_s(it.get("stdDay")),
        mgm_pk=_s(it.get("mgmBldrgstPk")),
        source_day=_s(it.get("crtnDay")),
    )


def parse_zone(it: dict) -> ZoneDistrict:
    return ZoneDistrict(
        zone_kind=_s(it.get("jijiguGbCdNm")),
        zone_name=_s(it.get("jijiguCdNm")),
        is_representative=_s(it.get("reprYn")) == "1",
        etc=_s(it.get("etcJijigu")),
        mgm_pk=_s(it.get("mgmBldrgstPk")),
        source_day=_s(it.get("crtnDay")),
    )


# --- 공통 조회 --------------------------------------------------------------
def _fetch_items(
    endpoint: str,
    sigungu_cd: str,
    bjdong_cd: str,
    bun: str | int = "",
    ji: str | int = "",
    *,
    service_key: Optional[str] = None,
    http_get: Callable[[str], str] = _default_http_get,
    num_of_rows: int = 100,
    max_pages: int = 50,
    base_url: str = BLD_BASE,
) -> list[dict]:
    key = service_key or os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if not key:
        raise BuildingLedgerError("DATA_GO_KR_SERVICE_KEY 미설정")
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        url = build_title_url(
            key, sigungu_cd, bjdong_cd, bun, ji,
            num_of_rows=num_of_rows, page_no=page, endpoint=endpoint, base_url=base_url,
        )
        payload = json.loads(http_get(url))
        items = _items_from_response(payload)
        if not items:
            break
        out += items
        body = payload.get("response", payload).get("body", {}) or {}
        total = int(body.get("totalCount") or 0)
        if page * num_of_rows >= total:
            break
    return out


# --- 공개 조회 함수 ---------------------------------------------------------
def fetch_expos_units(sigungu_cd, bjdong_cd, bun="", ji="", **kw) -> list[ExposUnit]:
    return [parse_expos(x) for x in _fetch_items("getBrExposInfo", sigungu_cd, bjdong_cd, bun, ji, **kw)]


def fetch_floor_outlines(sigungu_cd, bjdong_cd, bun="", ji="", **kw) -> list[FloorOutline]:
    return [parse_floor(x) for x in _fetch_items("getBrFlrOulnInfo", sigungu_cd, bjdong_cd, bun, ji, **kw)]


def fetch_septic(sigungu_cd, bjdong_cd, bun="", ji="", **kw) -> list[SepticFacility]:
    return [parse_septic(x) for x in _fetch_items("getBrWclfInfo", sigungu_cd, bjdong_cd, bun, ji, **kw)]


def fetch_housing_prices(sigungu_cd, bjdong_cd, bun="", ji="", **kw) -> list[HousingPrice]:
    return [parse_housing_price(x) for x in _fetch_items("getBrHsprcInfo", sigungu_cd, bjdong_cd, bun, ji, **kw)]


def fetch_zones(sigungu_cd, bjdong_cd, bun="", ji="", **kw) -> list[ZoneDistrict]:
    return [parse_zone(x) for x in _fetch_items("getBrJijiguInfo", sigungu_cd, bjdong_cd, bun, ji, **kw)]


__all__ = [
    "ExposUnit", "FloorOutline", "SepticFacility", "HousingPrice", "ZoneDistrict",
    "parse_expos", "parse_floor", "parse_septic", "parse_housing_price", "parse_zone",
    "fetch_expos_units", "fetch_floor_outlines", "fetch_septic",
    "fetch_housing_prices", "fetch_zones",
    "BuildingLedgerError", "CONFIDENCE", "SOURCE",
]
