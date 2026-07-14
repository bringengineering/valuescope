"""국토교통부 실거래가 공개시스템(rt.molit.go.kr) 엑셀 파싱.

API가 아닌 **수동 다운로드 엑셀**을 표준 거래 레코드로 변환한다. 매매/전월세를
모두 지원하며, 열 순서가 바뀌어도 헤더명으로 매핑한다. 표준 라이브러리만 사용
(xlsx = zip + xml).

금액 원본 단위는 '만원'이며 Decimal로 보관한다(float 금지). 원 단위가 필요하면
``*_krw`` 헬퍼로 Money를 얻는다.
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Union

from ..domain.money import Money

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


# --- low-level xlsx reading ------------------------------------------------
def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group()
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _cell_text(c: ET.Element, shared: List[str]) -> str:
    if c.get("t") == "inlineStr":
        return "".join(x.text or "" for x in c.iter(_NS + "t"))
    v = c.find(_NS + "v")
    if v is None:
        return ""
    if c.get("t") == "s" and shared:
        return shared[int(v.text)]
    return v.text or ""


def read_xlsx_rows(data: Union[str, bytes]) -> List[List[str]]:
    """Return the first worksheet as a list of rows (each a list of cell strings)."""
    zf = zipfile.ZipFile(data if isinstance(data, str) else _bytes_io(data))
    shared: List[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        for si in ET.fromstring(zf.read("xl/sharedStrings.xml")):
            shared.append("".join(t.text or "" for t in si.iter(_NS + "t")))
    sheet_name = sorted(
        n for n in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)
    )[0]
    rows: List[List[str]] = []
    for r in ET.fromstring(zf.read(sheet_name)).find(_NS + "sheetData"):
        cells = {}
        for c in r:
            ref = c.get("r")
            if ref:
                cells[_col_index(ref)] = _cell_text(c, shared).strip()
        width = max(cells) + 1 if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def _bytes_io(b: bytes):
    import io

    return io.BytesIO(b)


# --- parsing to transactions ----------------------------------------------
def _dec(s: str) -> Optional[Decimal]:
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class Transaction:
    kind: str                       # "sale" | "rent"
    sigungu: Optional[str]          # 시군구 (지번 주소 문자열)
    jibun: Optional[str]            # 번지
    building_name: Optional[str]    # 단지명/건물명
    area_m2: Optional[Decimal]      # 전용면적
    contract_ym: Optional[str]      # 계약년월 (YYYYMM 또는 YYYY-MM)
    contract_day: Optional[str]
    floor: Optional[str]
    build_year: Optional[str]
    road_name: Optional[str]
    house_type: Optional[str]       # 주택유형 (아파트/단독다가구/연립다세대 …)
    price_manwon: Optional[Decimal] = None      # 매매 거래금액(만원)
    rent_type: Optional[str] = None             # 전세/월세
    deposit_manwon: Optional[Decimal] = None    # 전월세 보증금(만원)
    monthly_rent_manwon: Optional[Decimal] = None  # 월세금(만원)
    source: str = "국토교통부 실거래가 공개시스템(엑셀)"
    confidence: str = "B"

    def price_krw(self) -> Optional[Money]:
        return Money(self.price_manwon * 10000, "KRW") if self.price_manwon is not None else None

    def deposit_krw(self) -> Optional[Money]:
        return Money(self.deposit_manwon * 10000, "KRW") if self.deposit_manwon is not None else None

    def monthly_rent_krw(self) -> Optional[Money]:
        return Money(self.monthly_rent_manwon * 10000, "KRW") if self.monthly_rent_manwon is not None else None


@dataclass(frozen=True)
class ParsedTransactions:
    kind: str                       # "sale" | "rent"
    transactions: tuple[Transaction, ...]
    header: tuple[str, ...] = field(default_factory=tuple)

    def by_dong(self, dong: str) -> List[Transaction]:
        return [t for t in self.transactions if t.sigungu and dong in t.sigungu]


def _header_index(rows: List[List[str]]) -> int:
    for i, r in enumerate(rows):
        if r and r[0] == "NO" and any("시군구" in (c or "") for c in r):
            return i
    raise ValueError("실거래가 엑셀 헤더('NO … 시군구 …')를 찾지 못했습니다.")


def _find(header: List[str], *needles: str) -> Optional[int]:
    for i, h in enumerate(header):
        if any(n in (h or "") for n in needles):
            return i
    return None


def parse_transactions(rows: List[List[str]]) -> ParsedTransactions:
    hi = _header_index(rows)
    header = rows[hi]
    kind = "sale" if _find(header, "거래금액") is not None else "rent"

    ci = {
        "sigungu": _find(header, "시군구"),
        "jibun": _find(header, "번지"),
        "name": _find(header, "단지명", "건물명"),
        "area": _find(header, "전용면적"),
        "ym": _find(header, "계약년월"),
        "day": _find(header, "계약일"),
        "floor": _find(header, "층"),
        "year": _find(header, "건축년도"),
        "road": _find(header, "도로명"),
        "htype": _find(header, "주택유형"),
        "price": _find(header, "거래금액"),
        "rtype": _find(header, "전월세구분"),
        "deposit": _find(header, "보증금"),
        "monthly": _find(header, "월세금"),
    }

    def g(row, key):
        idx = ci[key]
        return row[idx] if idx is not None and idx < len(row) else ""

    txns: List[Transaction] = []
    for row in rows[hi + 1:]:
        if not any((c or "").strip() for c in row):
            continue
        if not (g(row, "sigungu") or "").strip():
            continue
        txns.append(
            Transaction(
                kind=kind,
                sigungu=(g(row, "sigungu") or "").strip() or None,
                jibun=(g(row, "jibun") or "").strip() or None,
                building_name=(g(row, "name") or "").strip() or None,
                area_m2=_dec(g(row, "area")),
                contract_ym=(g(row, "ym") or "").strip() or None,
                contract_day=(g(row, "day") or "").strip() or None,
                floor=(g(row, "floor") or "").strip() or None,
                build_year=(g(row, "year") or "").strip() or None,
                road_name=(g(row, "road") or "").strip() or None,
                house_type=(g(row, "htype") or "").strip() or None,
                price_manwon=_dec(g(row, "price")),
                rent_type=(g(row, "rtype") or "").strip() or None,
                deposit_manwon=_dec(g(row, "deposit")),
                monthly_rent_manwon=_dec(g(row, "monthly")),
            )
        )
    return ParsedTransactions(kind=kind, transactions=tuple(txns), header=tuple(header))


def parse_excel(data: Union[str, bytes]) -> ParsedTransactions:
    """엑셀(경로 또는 bytes) → ParsedTransactions."""
    return parse_transactions(read_xlsx_rows(data))


__all__ = ["Transaction", "ParsedTransactions", "parse_excel", "parse_transactions", "read_xlsx_rows"]
