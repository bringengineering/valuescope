"""원주 전역 파일럿 배치 — 아파트 제외 전 유형 건물 지도 데이터 생성.

동지역 18개 법정동 × (건축물대장 → 아파트·비수익 유형 제외 → 지오코딩)
+ 동별 실거래(전월세·매매) 시세 → 추정 임대료·시장가치·수익률.

재개 가능: 동별 체크포인트(scratch/wonju/<bjdong>.json) + 지오코딩 캐시.
키는 환경변수: DATA_GO_KR_SERVICE_KEY, NCP_APIGW_KEY_ID, NCP_APIGW_KEY.

주의: 추정치는 지역 실거래 중앙값 기반 가정(신뢰도 C~D)이며 확정 감정가가 아니다.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from valuescope.connectors import building_registry as br  # noqa: E402
from valuescope.connectors import rtms_api as rtms  # noqa: E402

SIGUNGU = "51130"  # 원주시
LARGE_M2 = 330.0
# 수익형 대상에서 제외할 주용도(순수 비수익·인프라). 나머지는 모두 포함.
EXCLUDE_USE = {
    "창고시설", "자동차관련시설", "위험물저장및처리시설", "동물및식물관련시설",
    "운수시설", "공장", "교육연구시설", "종교시설", "발전시설", "묘지관련시설",
    "군사시설", "방송통신시설", "관광휴게시설", "분뇨.쓰레기처리시설",
}
RENT_MONTHS = ["202506", "202505", "202504", "202503", "202502", "202501",
               "202412", "202411", "202410", "202409", "202408", "202407"]
SALE_MONTHS = [f"{y}{m:02d}" for y in (2025, 2024, 2023)
               for m in range(1, 13) if not (y == 2025 and m > 6)][:24]

SCRATCH = Path(os.environ.get("WONJU_SCRATCH", "/tmp/wonju"))
SCRATCH.mkdir(parents=True, exist_ok=True)
GEOCACHE = SCRATCH / "geocache.json"
GEO_WORKERS = int(os.environ.get("WONJU_GEO_WORKERS", "10"))


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _get(url, tries=5):
    for i in range(tries):
        try:
            return json.loads(br._default_http_get(url))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.0 * (i + 1))


# --- 건축물대장: 동 전건(아파트·비수익 제외) --------------------------------
def keep(b) -> bool:
    u = b.main_use or ""
    if u in EXCLUDE_USE or "아파트" in u:
        return False
    if u == "공동주택" and (b.floors_above or 0) >= 5:  # 아파트 추정 → 제외
        return False
    return True


def fetch_dong_buildings(key, bjdong):
    out, total = [], 0
    for page in range(1, 60):
        payload = _get(br.build_title_url(key, SIGUNGU, bjdong, num_of_rows=100, page_no=page))
        body = payload.get("response", payload).get("body", {})
        total = int(body.get("totalCount") or 0)
        items = br._items_from_response(payload)
        if not items:
            break
        for it in items:
            b = br.parse_title_item(it)
            if keep(b):
                out.append(b)
        if page * 100 >= total:
            break
    return out, total


# --- 지오코딩 (NCP, 캐시) ---------------------------------------------------
def _geocode_one(addr):
    url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode?query=" + urllib.parse.quote(addr)
    req = urllib.request.Request(url, headers={
        "X-NCP-APIGW-API-KEY-ID": os.environ["NCP_APIGW_KEY_ID"],
        "X-NCP-APIGW-API-KEY": os.environ["NCP_APIGW_KEY"],
        "Accept": "application/json",
    })
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                g = json.loads(resp.read().decode())
            addrs = g.get("addresses") or []
            if addrs:
                return [float(addrs[0]["y"]), float(addrs[0]["x"])]
            return None
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def load_geocache():
    if GEOCACHE.exists():
        return json.loads(GEOCACHE.read_text(encoding="utf-8"))
    return {}


def geocode_many(addrs, cache):
    todo = [a for a in addrs if a and a not in cache]
    if todo:
        with ThreadPoolExecutor(max_workers=GEO_WORKERS) as ex:
            results = list(ex.map(_geocode_one, todo))
        for a, r in zip(todo, results):
            cache[a] = r
        GEOCACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


# --- 동별 실거래 시세 밴드 --------------------------------------------------
def _band(xs):
    xs = sorted(xs)
    if not xs:
        return None
    q = lambda f: xs[min(len(xs) - 1, int(len(xs) * f))]  # noqa: E731
    return {"n": len(xs), "p25": round(q(0.25)), "med": round(statistics.median(xs)), "p75": round(q(0.75))}


def all_transactions():
    """원주 전체 전월세·매매를 동명 버킷으로."""
    rent_by, sale_by = {}, {}
    for ym in RENT_MONTHS:
        try:
            for t in rtms.fetch_sh_rent(SIGUNGU, ym):
                rent_by.setdefault(t.sigungu, []).append(t)
        except Exception as e:
            log("전월세 오류", ym, e)
    for ym in SALE_MONTHS:
        try:
            for t in rtms.fetch_sh_trade(SIGUNGU, ym):
                sale_by.setdefault(t.sigungu, []).append(t)
        except Exception as e:
            log("매매 오류", ym, e)
    return rent_by, sale_by


def dong_bands(rents, sales):
    wol = [t for t in rents if t.rent_type == "월세" and t.monthly_rent_manwon and t.area_m2]
    gel = [t for t in sales if t.area_m2 and t.price_manwon]
    large = [float(t.price_manwon) / float(t.area_m2) for t in gel if float(t.area_m2) >= LARGE_M2]
    return {
        "n_rent": len(rents), "n_sale": len(gel),
        "wolse_per_m2": (statistics.median([float(t.monthly_rent_manwon) / float(t.area_m2) for t in wol]) if wol else None),
        "wolse_deposit_per_m2": (statistics.median([float(t.deposit_manwon) / float(t.area_m2) for t in wol if t.deposit_manwon]) if wol else None),
        "sale_large_per_m2": _band(large),
        "sale_all_per_m2": _band([float(t.price_manwon) / float(t.area_m2) for t in gel]),
    }


def main():
    key = os.environ["DATA_GO_KR_SERVICE_KEY"]
    dongs = json.loads((SCRATCH / "dong_codes.json").read_text(encoding="utf-8"))
    log(f"대상 법정동 {len(dongs)}개")

    rent_by, sale_by = all_transactions()
    # 원주 전체 폴백 밴드
    all_rent = [t for lst in rent_by.values() for t in lst]
    all_sale = [t for lst in sale_by.values() for t in lst]
    city_band = dong_bands(all_rent, all_sale)
    (SCRATCH / "city_band.json").write_text(json.dumps(city_band, ensure_ascii=False), encoding="utf-8")
    log(f"원주 전체 전월세 {city_band['n_rent']}·매매 {city_band['n_sale']} | 월세 {city_band['wolse_per_m2']}만/㎡")

    cache = load_geocache()
    for d in dongs:
        bj = d["bjdong"]
        cp = SCRATCH / f"{bj}.json"
        if cp.exists():
            log(f"  {bj} 완료(스킵)")
            continue
        # 동명 추출: 샘플주소에서
        dong_name = d["sample"].split("시 ")[-1].split()[0] if "시 " in d["sample"] else ""
        band = dong_bands(rent_by.get(dong_name, []), sale_by.get(dong_name, []))
        # 시세 폴백
        wpm2 = band["wolse_per_m2"] or city_band["wolse_per_m2"] or 0
        dpm2 = band["wolse_deposit_per_m2"] or city_band["wolse_deposit_per_m2"] or 0
        large_med = (band["sale_large_per_m2"] or city_band["sale_large_per_m2"] or {}).get("med")
        all_med = (band["sale_all_per_m2"] or city_band["sale_all_per_m2"] or {}).get("med")

        buildings, total = fetch_dong_buildings(key, bj)
        addrs = [b.address_road or b.address_jibun for b in buildings]
        geocode_many([a for a in addrs if a], cache)

        recs = []
        for i, b in enumerate(buildings):
            addr = b.address_road or b.address_jibun
            latlng = cache.get(addr) if addr else None
            if not latlng:
                continue
            area = float(b.total_floor_area_m2) if b.total_floor_area_m2 else None
            em = round(wpm2 * area) if (area and wpm2) else None
            dep = round(dpm2 * area) if (area and dpm2) else None
            srate = (large_med if (area and area >= LARGE_M2) else all_med)
            val = round(area * srate) if (area and srate) else None
            recs.append({
                "id": f"{bj}-{i}",
                "name": b.building_name or "",
                "address": addr,
                "dong": dong_name,
                "lat": latlng[0], "lng": latlng[1],
                "use": b.main_use,
                "area": round(area, 1) if area else None,
                "floors": b.floors_above,
                "approval": b.approval_date,
                "em": em, "dep": dep,
                "val": round(val / 1e4, 1) if val else None,  # 억
                "yld": (round(em * 12 / val * 100, 1) if (em and val) else None),
            })
        cp.write_text(json.dumps({
            "bjdong": bj, "dong": dong_name, "total": total,
            "kept": len(buildings), "geocoded": len(recs),
            "band": band, "buildings": recs,
        }, ensure_ascii=False), encoding="utf-8")
        log(f"  {bj} {dong_name}: 전체 {total} → 대상 {len(buildings)} → 지오코딩 {len(recs)}")

    log("동별 배치 완료. combine 단계로 병합하세요.")


if __name__ == "__main__":
    main()
