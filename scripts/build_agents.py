"""원주 공인중개사 전수 수집 → 지도 동그라미 레이어(agents.js).

소상공인시장진흥공단 상가(상권)정보 API에서 원주시 부동산 업종을 걷어
상호명·주소·경위도를 추출한다. (data.go.kr에서 해당 API 활용신청 필요)

출력: window.WONJU_AGENTS = [{id,name,addr,dong,lat,lng}, ...]
키: DATA_GO_KR_SERVICE_KEY 환경변수.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"
SIGNGU = "51130"  # 원주시
OUT = Path(os.environ.get("AGENTS_OUT", "docs/data/agents.js"))
NAME_PAT = re.compile(r"공인중개사|부동산중개|부동산\s*$|중개사무소")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _get(url, tries=4):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "vs/1.0"})
    for i in range(tries):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.0 * (i + 1))


def fetch_stores(key):
    """원주시 부동산(L) 업종 전 점포. 페이지네이션."""
    out = []
    for page in range(1, 60):
        q = {"serviceKey": key, "type": "json", "numOfRows": "1000", "pageNo": str(page),
             "divId": "signguCd", "key": SIGNGU, "indsLclsCd": "L"}
        url = BASE + "/storeListInUpjong?" + urllib.parse.urlencode(q, safe="%")
        j = _get(url)
        body = j.get("body", j.get("response", {}).get("body", {})) or {}
        items = body.get("items") or []
        if not items:
            break
        out += items
        total = int(body.get("totalCount") or 0)
        log(f"  page {page}: +{len(items)} (total {total})")
        if page * 1000 >= total:
            break
    return out


def main():
    key = os.environ["DATA_GO_KR_SERVICE_KEY"]
    stores = fetch_stores(key)
    log(f"부동산 업종 점포 {len(stores)}건")
    agents = []
    seen = set()
    for s in stores:
        name = (s.get("bizesNm") or "").strip()
        # 중개업만: 상호 패턴 또는 소분류명에 '중개'
        scls = (s.get("indsSclsNm") or "") + (s.get("indsMclsNm") or "")
        if not (NAME_PAT.search(name) or "중개" in scls):
            continue
        try:
            lat, lng = float(s.get("lat")), float(s.get("lon"))
        except (TypeError, ValueError):
            continue
        sid = s.get("bizesId") or f"{lat:.6f},{lng:.6f},{name}"
        if sid in seen:
            continue
        seen.add(sid)
        addr = (s.get("rdnmAdr") or s.get("lnoAdr") or "").strip()
        m = re.search(r"(\S+동)\b", (s.get("lnoAdr") or ""))
        agents.append({"id": f"b{sid}", "name": name, "addr": addr,
                       "dong": m.group(1) if m else "", "lat": round(lat, 6), "lng": round(lng, 6)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.WONJU_AGENTS = " + json.dumps(agents, ensure_ascii=False) + ";\n", encoding="utf-8")
    log(f"중개사 {len(agents)}곳 → {OUT}")


if __name__ == "__main__":
    main()
