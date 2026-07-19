"""동별 체크포인트(scratch/wonju/<bjdong>.json)를 지도용 wonju.js로 병합."""

from __future__ import annotations

import glob
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from valuescope import Money  # noqa: E402
from valuescope.calculators.net_yield import compute_net_yield  # noqa: E402


def _age(approval):
    s = str(approval or "")[:4]
    if s.isdigit() and 1950 < int(s) < 2026:
        return 2026 - int(s)
    return None


def _net_yield_pct(em_manwon, val_eok, approval):
    """실현 수익률(%) — 공실·운영비·노후 자본지출 반영."""
    if not (em_manwon and val_eok):
        return None, None
    res = compute_net_yield(
        monthly_rent=Money.won(int(round(em_manwon * 1e4))),
        price=Money.won(int(round(val_eok * 1e8))),
        age_years=_age(approval),
    )
    ny = round(float(res.realizable_yield) * 100, 1) if res.realizable_yield is not None else None
    return ny, res.assumptions.label

SCRATCH = Path(os.environ.get("WONJU_SCRATCH", "/tmp/wonju"))
SKIP = {"dong_codes.json", "geocache.json", "city_band.json"}


def _band(meds):
    meds = sorted(meds)
    if not meds:
        return None
    q = lambda f: meds[min(len(meds) - 1, int(len(meds) * f))]  # noqa: E731
    return {"n": len(meds), "p25": round(q(0.25)), "med": round(statistics.median(meds)), "p75": round(q(0.75))}


# 추정 가치산정은 다가구 시세(원/㎡) 기반 → 소형~중형 주거·근생에만 유효.
# 대형/아파트급은 지도에는 남기되 왜곡된 추정치를 노출하지 않는다.
APT_AREA = 1000.0     # 공동주택 이 이상 = 아파트급 → 제외
VALUE_MAX_AREA = 2500.0  # 이 초과 건물은 추정 시장가치·수익률 미표시(대형/비주거)
DROP_AREA = 20000.0   # 초대형(단지·몰) → 제외


def _clean(recs):
    out = []
    for b in recs:
        a = b.get("area") or 0
        if a > DROP_AREA:
            continue
        if b.get("use") == "공동주택" and a > APT_AREA:  # 아파트 제외
            continue
        if a > VALUE_MAX_AREA:  # 대형: 다가구 시세로 가치산정 부적절 → 추정 제거
            b = {**b, "val": None, "yld": None, "em": None, "dep": None, "oversized": True}
        else:
            ny, age_label = _net_yield_pct(b.get("em"), b.get("val"), b.get("approval"))
            b = {**b, "nyld": ny, "age_label": age_label}  # 실현 수익률 + 연식구간
        out.append(b)
    return out


def main():
    buildings, bands, dong_list = [], {}, []
    for f in sorted(glob.glob(str(SCRATCH / "*.json"))):
        if os.path.basename(f) in SKIP:
            continue
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        bands[d["dong"]] = d["band"]
        cleaned = _clean(d["buildings"])
        dong_list.append({"name": d["dong"], "count": len(cleaned)})
        buildings += cleaned

    cbf = SCRATCH / "city_band.json"
    if cbf.exists():
        city_band = json.loads(cbf.read_text(encoding="utf-8"))
    else:  # 폴백: 동별 대형 시세 중앙값을 풀링
        large = [b["sale_large_per_m2"]["med"] for b in bands.values() if b.get("sale_large_per_m2")]
        alln = [b["sale_all_per_m2"]["med"] for b in bands.values() if b.get("sale_all_per_m2")]
        city_band = {
            "n_rent": sum(b.get("n_rent", 0) for b in bands.values()),
            "n_sale": sum(b.get("n_sale", 0) for b in bands.values()),
            "wolse_per_m2": statistics.median([b["wolse_per_m2"] for b in bands.values() if b.get("wolse_per_m2")] or [0]),
            "sale_large_per_m2": _band(large),
            "sale_all_per_m2": _band(alln),
        }

    payload = {
        "city": "강원특별자치도 원주시",
        "center": {"lat": 37.342, "lng": 127.92},
        "count": len(buildings),
        "bands": bands,
        "city_band": city_band,
        "dong_list": dong_list,
        "confidence": "C~D",
        "note": "추정 임대료·시장가치는 동별 실거래 중앙값 기반 가정(신뢰도 C~D). 아파트·창고 등 제외. 확정 감정가 아님.",
        "buildings": buildings,
    }
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else SCRATCH / "wonju.js"
    out.write_text("window.WONJU = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"병합: 동 {len(dong_list)}개 · 건물 {len(buildings):,}건 → {out}")


if __name__ == "__main__":
    main()
