"""무실동 파일럿 배치 — 단독/다가구 건물 지도 데이터 생성.

건축물대장(무실동 전건) → 단독/다가구 필터 → 네이버 지오코딩(좌표)
+ 전월세 실거래로 추정 임대료 → 지도용 JSON(window.MUYSIL_BUILDINGS).

키는 모두 환경변수에서 읽는다(코드/저장소에 넣지 않음):
  DATA_GO_KR_SERVICE_KEY, NCP_APIGW_KEY_ID, NCP_APIGW_KEY

주의: 추정 임대료는 지역 실거래 중앙값 기반 '가정(신뢰도 D)'이며 확정값이 아니다.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from valuescope.connectors import building_registry as br  # noqa: E402
from valuescope.connectors import rtms_api as rtms  # noqa: E402

SIGUNGU = "51130"      # 원주시
BJDONG = "11500"       # 무실동
DONG_NAME = "무실동"
RESID = {"단독주택", "다가구주택", "다중주택", "다세대주택", "연립주택"}
CAP = int(os.environ.get("MUYSIL_CAP", "300"))   # 파일럿 표본 상한(속도)
RENT_MONTHS = ["202506", "202505", "202504", "202503", "202502", "202501"]
SALE_MONTHS = [f"{y}{m:02d}" for y in (2025, 2024, 2023)
               for m in range(1, 13) if not (y == 2025 and m > 6)][:24]
LARGE_M2 = 330.0   # 대형 다가구 경계(연면적)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# --- 1) 건축물대장: 무실동 단독/다가구 전건 ---------------------------------
def fetch_muysil_buildings():
    key = os.environ["DATA_GO_KR_SERVICE_KEY"]
    out = []
    total = 0
    for page in range(1, 40):
        url = br.build_title_url(key, SIGUNGU, BJDONG, num_of_rows=100, page_no=page)
        payload = json.loads(br._default_http_get(url))
        body = payload.get("response", payload).get("body", {})
        total = int(body.get("totalCount") or 0)
        items = br._items_from_response(payload)
        if not items:
            break
        for it in items:
            b = br.parse_title_item(it)
            if b.main_use in RESID:
                out.append(b)
        if page * 100 >= total:
            break
    log(f"건축물대장 무실동 {total}건 중 주거계열 {len(out)}건")
    return out


# --- 2) 지오코딩 (NCP) ------------------------------------------------------
def geocode(addr: str):
    url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode?query=" + urllib.parse.quote(addr)
    req = urllib.request.Request(url, headers={
        "X-NCP-APIGW-API-KEY-ID": os.environ["NCP_APIGW_KEY_ID"],
        "X-NCP-APIGW-API-KEY": os.environ["NCP_APIGW_KEY"],
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            g = json.loads(resp.read().decode())
        addrs = g.get("addresses") or []
        if addrs:
            return float(addrs[0]["y"]), float(addrs[0]["x"])
    except Exception:
        return None
    return None


# --- 3) 전월세 실거래 → 무실동 단위면적 임대료 중앙값 ------------------------
def muysil_rent_rates():
    rents = []
    for ym in RENT_MONTHS:
        try:
            rents += [t for t in rtms.fetch_sh_rent(SIGUNGU, ym) if t.sigungu == DONG_NAME]
        except Exception as e:
            log("전월세 조회 오류", ym, e)
    wol = [t for t in rents if t.rent_type == "월세" and t.monthly_rent_manwon and t.area_m2]
    jeon = [t for t in rents if t.rent_type == "전세" and t.deposit_manwon and t.area_m2]
    def med(xs):
        return statistics.median(xs) if xs else None
    rate = {
        "n_rent": len(rents),
        "wolse_per_m2": med([float(t.monthly_rent_manwon) / float(t.area_m2) for t in wol]),
        "wolse_deposit_per_m2": med([float(t.deposit_manwon) / float(t.area_m2) for t in wol]),
        "jeonse_per_m2": med([float(t.deposit_manwon) / float(t.area_m2) for t in jeon]),
    }
    log(f"전월세 무실동 {len(rents)}건 (월세 {len(wol)}·전세 {len(jeon)}) | 월세 {rate['wolse_per_m2']}만/㎡")
    return rate


# --- 3b) 매매 실거래 → 무실동 시세 밴드(원/㎡, 규모별) ----------------------
def _band(xs):
    xs = sorted(xs)
    if not xs:
        return None
    q = lambda f: xs[min(len(xs) - 1, int(len(xs) * f))]  # noqa: E731
    return {"n": len(xs), "p25": round(q(0.25)),
            "med": round(statistics.median(xs)), "p75": round(q(0.75))}


def muysil_sale_band():
    sales = []
    for ym in SALE_MONTHS:
        try:
            sales += [t for t in rtms.fetch_sh_trade(SIGUNGU, ym) if t.sigungu == DONG_NAME]
        except Exception as e:
            log("매매 조회 오류", ym, e)
    gel = [t for t in sales if t.area_m2 and t.price_manwon]
    large = [float(t.price_manwon) / float(t.area_m2) for t in gel if float(t.area_m2) >= LARGE_M2]
    allp = [float(t.price_manwon) / float(t.area_m2) for t in gel]
    band = {
        "n_sale": len(gel), "months": len(SALE_MONTHS),
        "won_per_m2_large_manwon": _band(large),
        "won_per_m2_all_manwon": _band(allp),
        "price_manwon_all": _band([float(t.price_manwon) for t in gel]),
    }
    log(f"매매 무실동 {len(gel)}건 | 대형 시세 "
        f"{band['won_per_m2_large_manwon'] and band['won_per_m2_large_manwon']['med']}만/㎡")
    return band


def main():
    buildings = fetch_muysil_buildings()
    rate = muysil_rent_rates()
    sale_band = muysil_sale_band()
    wpm2 = rate["wolse_per_m2"] or 0
    dpm2 = rate["wolse_deposit_per_m2"] or 0
    large_med = (sale_band["won_per_m2_large_manwon"] or {}).get("med")
    all_med = (sale_band["won_per_m2_all_manwon"] or {}).get("med")

    records = []
    geo_ok = 0
    for i, b in enumerate(buildings[:CAP]):
        addr = b.address_road or b.address_jibun
        if not addr:
            continue
        latlng = geocode(addr)
        time.sleep(0.05)
        if not latlng:
            continue
        geo_ok += 1
        area = float(b.total_floor_area_m2) if b.total_floor_area_m2 else None
        est_monthly = round(wpm2 * area) if (area and wpm2) else None      # 만원
        est_deposit = round(dpm2 * area) if (area and dpm2) else None      # 만원
        # 추정 시장가치 = 연면적 × 규모별 실거래 시세(만원/㎡)
        sale_rate = (large_med if (area and area >= LARGE_M2) else all_med)
        est_value = round(area * sale_rate) if (area and sale_rate) else None  # 만원
        gross_yield = (round(est_monthly * 12 / est_value * 100, 1)
                       if (est_monthly and est_value) else None)               # %
        records.append({
            "id": f"muysil-{i}",
            "name": b.building_name or (addr.split()[-1] if addr else "건물"),
            "address": addr,
            "lat": latlng[0], "lng": latlng[1],
            "house_type": b.main_use,
            "total_floor_area": float(b.total_floor_area_m2) if b.total_floor_area_m2 else None,
            "floors_above": b.floors_above,
            "approval_date": b.approval_date,
            "est_monthly_rent_manwon": est_monthly,
            "est_deposit_manwon": est_deposit,
            "est_value_manwon": est_value,
            "est_value_eok": round(est_value / 1e4, 1) if est_value else None,
            "gross_yield_pct": gross_yield,
        })
        if geo_ok % 25 == 0:
            log(f"  지오코딩 {geo_ok}건…")

    # 추정 월세 4분위로 색상 tier
    vals = sorted(r["est_monthly_rent_manwon"] for r in records if r["est_monthly_rent_manwon"])
    def tier(v):
        if not vals or v is None:
            return 0
        q = [vals[int(len(vals) * f)] for f in (0.25, 0.5, 0.75)]
        return sum(v > t for t in q)  # 0..3
    for r in records:
        r["tier"] = tier(r["est_monthly_rent_manwon"])

    payload = {
        "dong": "강원특별자치도 원주시 무실동",
        "center": {"lat": 37.335, "lng": 127.918},
        "rate": rate,
        "sale_band": sale_band,
        "count": len(records),
        "confidence": "C",
        "note": ("추정 임대료·시장가치는 무실동 실거래 중앙값 기반 가정(신뢰도 C~D). "
                 f"매매 실거래 {sale_band['n_sale']}건(24개월)·전월세 {rate['n_rent']}건 기반. "
                 "지번 마스킹으로 개별 건물-실거래 직접 매칭 불가. 확정 감정가 아님."),
        "buildings": records,
    }
    out = Path(os.environ.get("MUYSIL_OUT", "/tmp/muysil_buildings.json"))
    out.write_text("window.MUYSIL_BUILDINGS = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    log(f"완료: {len(records)}건 (지오코딩 성공) → {out}")
    print(json.dumps({"count": len(records), "geo_ok": geo_ok, "rate": rate}, ensure_ascii=False))


if __name__ == "__main__":
    main()
