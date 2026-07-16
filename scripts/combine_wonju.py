"""동별 체크포인트(scratch/wonju/<bjdong>.json)를 지도용 wonju.js로 병합."""

from __future__ import annotations

import glob
import json
import os
import statistics
import sys
from pathlib import Path

SCRATCH = Path(os.environ.get("WONJU_SCRATCH", "/tmp/wonju"))
SKIP = {"dong_codes.json", "geocache.json", "city_band.json"}


def _band(meds):
    meds = sorted(meds)
    if not meds:
        return None
    q = lambda f: meds[min(len(meds) - 1, int(len(meds) * f))]  # noqa: E731
    return {"n": len(meds), "p25": round(q(0.25)), "med": round(statistics.median(meds)), "p75": round(q(0.75))}


def main():
    buildings, bands, dong_list = [], {}, []
    for f in sorted(glob.glob(str(SCRATCH / "*.json"))):
        if os.path.basename(f) in SKIP:
            continue
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        bands[d["dong"]] = d["band"]
        dong_list.append({"name": d["dong"], "count": d["geocoded"]})
        buildings += d["buildings"]

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
