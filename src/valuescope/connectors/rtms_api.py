"""국토교통부 실거래가 RTMS Open API (data.go.kr) 커넥터.

단독/다가구 **매매**(RTMSDataSvcSHTrade)와 **전월세**(RTMSDataSvcSHRent)를
법정동코드 앞5자리(LAWD_CD)+계약년월(DEAL_YMD)로 조회한다. 응답은 XML.

- serviceKey는 환경변수 DATA_GO_KR_SERVICE_KEY 에서만 읽는다(하드코딩 금지).
- data.go.kr/프록시가 Accept/User-Agent 없는 요청에 빈 응답을 주므로 헤더 명시.
- 단독/다가구는 개인정보 보호로 지번 일부만 제공되어, 동(umdNm)·연면적 기준으로
  시세를 집계한다.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Callable, List, Optional

from .molit_excel import Transaction, _dec

BASE = "https://apis.data.go.kr/1613000"
TRADE_ENDPOINT = "/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade"  # 단독/다가구 매매
RENT_ENDPOINT = "/RTMSDataSvcSHRent/getRTMSDataSvcSHRent"     # 단독/다가구 전월세


class RtmsError(RuntimeError):
    """RTMS API 오류 응답."""


def _http_get(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/xml",
            "User-Agent": "BRING-ValueScope/0.1 (rtms-connector)",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - https only
        return resp.read().decode("utf-8")


def _build_url(endpoint: str, service_key: str, lawd_cd: str, deal_ymd: str, num_of_rows: int, page_no: int) -> str:
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": str(num_of_rows),
        "pageNo": str(page_no),
    }
    return f"{BASE}{endpoint}?" + urllib.parse.urlencode(params)


def _text(item: ET.Element, tag: str) -> Optional[str]:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _parse_items(xml_text: str) -> List[dict]:
    root = ET.fromstring(xml_text)
    # header 검사
    code = root.findtext(".//resultCode") or root.findtext(".//header/resultCode")
    if code not in (None, "00", "000"):
        msg = root.findtext(".//resultMsg") or f"resultCode={code}"
        raise RtmsError(msg)
    return [
        {child.tag: (child.text.strip() if child.text else "") for child in item}
        for item in root.findall(".//items/item")
    ]


def _to_transaction(d: dict, kind: str) -> Transaction:
    dong = d.get("umdNm")
    return Transaction(
        kind=kind,
        sigungu=dong,                       # 단독/다가구는 지번 일부만 → 동명 기준
        jibun=d.get("jibun") or None,
        building_name=d.get("bldNm") or None,
        area_m2=_dec(d.get("totalFloorAr")),
        contract_ym=(d.get("dealYear", "") + d.get("dealMonth", "").zfill(2)) or None,
        contract_day=d.get("dealDay") or None,
        floor=d.get("floor") or None,
        build_year=d.get("buildYear") or None,
        road_name=None,
        house_type="단독다가구",
        price_manwon=_dec(d.get("dealAmount")) if kind == "sale" else None,
        rent_type=("월세" if _dec(d.get("monthlyRent")) not in (None, Decimal(0)) else "전세") if kind == "rent" else None,
        deposit_manwon=_dec(d.get("deposit")) if kind == "rent" else None,
        monthly_rent_manwon=_dec(d.get("monthlyRent")) if kind == "rent" else None,
        source="국토교통부 실거래가 RTMS API (data.go.kr)",
    )


def _fetch(endpoint: str, kind: str, lawd_cd: str, deal_ymd: str, *,
           service_key: Optional[str], http_get: Callable[[str], str],
           num_of_rows: int, max_pages: int) -> List[Transaction]:
    key = service_key or os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if not key:
        raise RtmsError("serviceKey 미설정 — 환경변수 DATA_GO_KR_SERVICE_KEY 필요(저장소에 넣지 말 것).")
    out: List[Transaction] = []
    for page in range(1, max_pages + 1):
        url = _build_url(endpoint, key, lawd_cd, deal_ymd, num_of_rows, page)
        items = _parse_items(http_get(url))
        if not items:
            break
        out.extend(_to_transaction(d, kind) for d in items)
        if len(items) < num_of_rows:
            break
    return out


def fetch_sh_rent(lawd_cd: str, deal_ymd: str, *, service_key: Optional[str] = None,
                  http_get: Callable[[str], str] = _http_get,
                  num_of_rows: int = 1000, max_pages: int = 10) -> List[Transaction]:
    """단독/다가구 전월세 실거래가 (LAWD_CD 앞5자리, DEAL_YMD 6자리)."""
    return _fetch(RENT_ENDPOINT, "rent", lawd_cd, deal_ymd,
                  service_key=service_key, http_get=http_get, num_of_rows=num_of_rows, max_pages=max_pages)


def fetch_sh_trade(lawd_cd: str, deal_ymd: str, *, service_key: Optional[str] = None,
                   http_get: Callable[[str], str] = _http_get,
                   num_of_rows: int = 1000, max_pages: int = 10) -> List[Transaction]:
    """단독/다가구 매매 실거래가 (LAWD_CD 앞5자리, DEAL_YMD 6자리)."""
    return _fetch(TRADE_ENDPOINT, "sale", lawd_cd, deal_ymd,
                  service_key=service_key, http_get=http_get, num_of_rows=num_of_rows, max_pages=max_pages)


__all__ = ["fetch_sh_rent", "fetch_sh_trade", "RtmsError", "TRADE_ENDPOINT", "RENT_ENDPOINT"]
