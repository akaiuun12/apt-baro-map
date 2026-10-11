# -*- coding: utf-8 -*-
"""자치구 행정동별 대표 단지 + 최근 실거래가 데이터 생성 (구 무관, 행정동 단위).

성북구는 좌표·세대수를 손으로 채운 표(scripts/build_seongbuk_detail.py)로 만들었고,
강동구용 스크립트는 법정동 단위라 행정동 지도에 연결되지 않는다.
이 스크립트는 공개 API만으로 임의의 자치구를 행정동 단위로 생성한다.

파이프라인
  1) 국토교통부 아파트 매매 실거래가 상세자료 → 단지별 거래 집계 (법정동·지번·단지명)
  2) K-APT 단지목록/기본정보 → 세대수·동수·사용승인일·난방·도로명주소
  3) 지오코딩 → 단지 좌표
  4) data/dong_geo/{시군구코드}.js 경계에 point-in-polygon → 행정동 배정
  5) 세대수 45% + 최근 12개월 거래량 35% + 최근 거래시점 20% 로 동별 상위 3곳 선정

좌표 캐시
  data/sources/apt_coords.json 에 "시군구코드|법정동|지번" → [위도, 경도] 로 저장한다.
  한 번 받은 좌표는 다시 지오코딩하지 않으며, 값을 직접 고쳐 넣어 고정할 수도 있다.

사용법
  python scripts/fetch_district_detail.py --probe                 # 쓰기 없이 API 가용성만 점검
  python scripts/fetch_district_detail.py 마포구 은평구 서대문구
  python scripts/fetch_district_detail.py --all --months 12

인증키 (환경변수 또는 .env)
  DATA_GO_KR_API_KEY  실거래가 · K-APT      (없으면 CHEONGYAK_API_KEY 재사용)
  VWORLD_API_KEY      VWorld 지오코더       (선택)
  JUSO_API_KEY        도로명주소 좌표제공   (선택)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 요청·파싱·정규화 헬퍼는 강동구 스크립트와 공유한다 (import 시 부수효과 없음).
from fetch_gangdong_detail import (  # noqa: E402
    ApiError, KAPT_BASIC_URL, KAPT_LIST_URL, TRADE_URL, fmt_approval, load_key,
    match_kapt, month_keys, norm_name, pick, request_bytes, response_items,
    safe_float, safe_int, trade_date,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
GEO_DIR = DATA_DIR / "dong_geo"
COORD_CACHE = DATA_DIR / "sources" / "apt_coords.json"

SIDO_CODE = "11"
# 자치구 → (시군구코드, 출력 파일 slug, window 전역변수명)
DISTRICTS = {
    "종로구": ("11110", "jongno"), "중구": ("11140", "junggu"), "용산구": ("11170", "yongsan"),
    "성동구": ("11200", "seongdong"), "광진구": ("11215", "gwangjin"), "동대문구": ("11230", "dongdaemun"),
    "중랑구": ("11260", "jungnang"), "성북구": ("11290", "seongbuk"), "강북구": ("11305", "gangbuk"),
    "도봉구": ("11320", "dobong"), "노원구": ("11350", "nowon"), "은평구": ("11380", "eunpyeong"),
    "서대문구": ("11410", "seodaemun"), "마포구": ("11440", "mapo"), "양천구": ("11470", "yangcheon"),
    "강서구": ("11500", "gangseo"), "구로구": ("11530", "guro"), "금천구": ("11545", "geumcheon"),
    "영등포구": ("11560", "yeongdeungpo"), "동작구": ("11590", "dongjak"), "관악구": ("11620", "gwanak"),
    "서초구": ("11650", "seocho"), "강남구": ("11680", "gangnam"), "송파구": ("11710", "songpa"),
    "강동구": ("11740", "gangdong"),
}

MIN_MEDIAN_AREA = 40.0   # 전용 40㎡ 미만 위주 단지는 대표 단지에서 제외
TOP_N = 3
RECENT_TRADES = 20
W_HOUSEHOLDS, W_TRADES, W_RECENCY = 0.45, 0.35, 0.20


# ---------- 행정동 경계 ----------

def load_dong_geo(gu_code):
    """data/dong_geo/{코드}.js 에서 FeatureCollection 을 꺼낸다."""
    path = GEO_DIR / f"{gu_code}.js"
    if not path.exists():
        raise ApiError(f"행정동 경계 파일이 없습니다: {path}")
    txt = path.read_text(encoding="utf-8")
    # 파일 앞머리에 `window.DONG_GEO = window.DONG_GEO || {};` 가 있으므로
    # 자치구 키에 대입하는 구문에서부터 잘라 낸다.
    m = re.search(r'window\.DONG_GEO\[[^\]]+\]\s*=\s*', txt)
    if not m:
        raise ApiError(f"행정동 경계 형식을 알 수 없습니다: {path}")
    body = txt[m.end():].rstrip()
    return json.loads(body[:body.rindex("}") + 1])


def rings_of(feature):
    """Polygon / MultiPolygon 을 [[외곽, 구멍...], ...] 로 펼친다."""
    g = feature["geometry"]
    return g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]


def in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i - 1][0], ring[i - 1][1]
        x2, y2 = ring[i][0], ring[i][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def dong_at(features, lat, lon):
    for f in features:
        for poly in rings_of(f):
            if in_ring(lon, lat, poly[0]) and not any(in_ring(lon, lat, h) for h in poly[1:]):
                return f["properties"]["ADM_KOR_NM"]
    return None


# ---------- 지오코딩 ----------

def _coord_cache():
    if COORD_CACHE.exists():
        try:
            return json.loads(COORD_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_cache(cache):
    COORD_CACHE.parent.mkdir(parents=True, exist_ok=True)
    COORD_CACHE.write_text(
        json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")


def geocode_vworld(address, key):
    """VWorld 지오코더. 지번 주소 우선, 실패 시 도로명으로 재시도."""
    for kind in ("PARCEL", "ROAD"):
        blob = request_bytes("https://api.vworld.kr/req/address", {
            "service": "address", "request": "getcoord", "version": "2.0",
            "crs": "EPSG:4326", "type": kind, "address": address, "key": key, "format": "json",
        }, retries=1)
        try:
            data = json.loads(blob.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        resp = data.get("response") or {}
        if resp.get("status") != "OK":
            continue
        pt = (resp.get("result") or {}).get("point") or {}
        lat, lon = safe_float(pt.get("y")), safe_float(pt.get("x"))
        if lat and lon:
            return lat, lon
    return None


def geocode_juso(address, key):
    """행정안전부 도로명주소 좌표제공 API (도로명주소 입력 필요)."""
    blob = request_bytes("https://business.juso.go.kr/addrlink/addrCoordApi.do", {
        "confmKey": key, "currentPage": 1, "countPerPage": 1,
        "keyword": address, "resultType": "json",
    }, retries=1)
    try:
        data = json.loads(blob.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    results = (data.get("results") or {})
    if (results.get("common") or {}).get("errorCode") not in ("0", 0):
        return None
    for row in results.get("juso") or []:
        lat, lon = safe_float(row.get("entY")), safe_float(row.get("entX"))
        if lat and lon:
            return lat, lon
    return None


def make_geocoder(verbose=True):
    """사용 가능한 지오코더를 순서대로 담은 (이름, 함수) 목록을 만든다."""
    backends = []
    vw = os.environ.get("VWORLD_API_KEY", "").strip()
    js = os.environ.get("JUSO_API_KEY", "").strip()
    if vw:
        backends.append(("VWorld", lambda a: geocode_vworld(a, vw)))
    if js:
        backends.append(("도로명주소", lambda a: geocode_juso(a, js)))
    if verbose:
        print("  지오코더:", ", ".join(n for n, _ in backends) or "없음 (좌표 캐시만 사용)")
    return backends


# ---------- 수집 ----------

def fetch_trades(key, lawd_cd, months, dong_names):
    rows_out = []
    for ym in month_keys(months):
        page, rows = 1, []
        while True:
            chunk, total = response_items(request_bytes(TRADE_URL, {
                "serviceKey": key, "LAWD_CD": lawd_cd, "DEAL_YMD": ym,
                "pageNo": page, "numOfRows": 1000,
            }))
            rows.extend(chunk)
            if not chunk or len(rows) >= total or page > 20:
                break
            page += 1
        kept = 0
        for r in rows:
            # 해제(취소)된 거래는 집계에서 제외한다.
            if str(pick(r, "cdealType") or "").strip() in ("O", "Y", "1"):
                continue
            if str(pick(r, "cdealDay") or "").strip():
                continue
            d = trade_date(r)
            amt, area = safe_int(pick(r, "dealAmount")), safe_float(pick(r, "excluUseAr"))
            if not d or amt is None or area is None:
                continue
            rows_out.append({
                "apt_seq": str(pick(r, "aptSeq") or "").strip(),
                "name": str(pick(r, "aptNm") or "").strip(),
                "dong": str(pick(r, "umdNm") or "").strip(),
                "jibun": str(pick(r, "jibun") or "").strip(),
                "road": str(pick(r, "roadNm") or "").strip(),
                "date": d.isoformat(),
                "area": round(area, 2),
                "amount": amt,
                "floor": safe_int(pick(r, "floor")),
                "build_year": safe_int(pick(r, "buildYear")),
            })
            kept += 1
        print(f"    {ym}: {kept}건")
    return rows_out


def fetch_kapt_list(key, lawd_cd):
    rows, page = [], 1
    while True:
        chunk, total = response_items(request_bytes(KAPT_LIST_URL, {
            "serviceKey": key, "sidoCode": SIDO_CODE,
            "pageNo": page, "numOfRows": 1000, "_type": "json",
        }))
        rows.extend(chunk)
        if not chunk or len(rows) >= total or page > 20:
            break
        page += 1
    return [r for r in rows if str(pick(r, "bjdCode") or "").startswith(lawd_cd)]


# ---------- 조립 ----------

def group_complexes(trades):
    """실거래 행을 단지 단위로 묶는다."""
    grouped = defaultdict(list)
    for t in trades:
        ident = t["apt_seq"] or f'{t["dong"]}|{norm_name(t["name"])}|{t["jibun"]}'
        grouped[ident].append(t)
    return grouped


def resolve_coords(complexes, gu, gu_code, backends, cache, limit=None):
    """단지별 좌표를 캐시 → 지오코딩 순으로 채운다. 새로 받은 건수를 돌려준다."""
    fetched = 0
    for c in complexes:
        ck = f'{gu_code}|{c["legal_dong"]}|{c["jibun"]}'
        hit = cache.get(ck)
        if isinstance(hit, list) and len(hit) == 2:
            c["lat"], c["lon"] = hit
            continue
        if limit is not None and fetched >= limit:
            continue
        queries = [f'서울특별시 {gu} {c["legal_dong"]} {c["jibun"]}'.strip()]
        if c.get("road_address"):
            queries.append(c["road_address"])
        for name, fn in backends:
            for q in queries:
                try:
                    got = fn(q)
                except (ApiError, Exception) as e:  # 지오코딩 실패가 전체를 멈추지 않게 한다
                    print(f"    [경고] {name} 지오코딩 실패 {q}: {e}")
                    got = None
                if got:
                    c["lat"], c["lon"] = got
                    cache[ck] = [round(got[0], 8), round(got[1], 8)]
                    fetched += 1
                    break
            if c.get("lat"):
                break
    return fetched


def build_complexes(grouped, key, kapt_list, as_of):
    """단지별 요약 + K-APT 기본정보."""
    for k in kapt_list:
        k["_dong"] = str(pick(k, "bjdongName", "as3") or "").strip()
    basic_cache, out = {}, []
    for rows in grouped.values():
        rows.sort(key=lambda r: r["date"], reverse=True)
        s = rows[0]
        match = match_kapt(s["dong"], s["name"], kapt_list)
        kapt_code = str(pick(match or {}, "kaptCode") or "")
        basic = {}
        if kapt_code:
            if kapt_code not in basic_cache:
                try:
                    items, _ = response_items(request_bytes(KAPT_BASIC_URL, {
                        "serviceKey": key, "kaptCode": kapt_code, "_type": "json"}))
                    basic_cache[kapt_code] = items[0] if items else {}
                except ApiError as e:
                    print(f"    [경고] K-APT 기본정보 {kapt_code}: {e}")
                    basic_cache[kapt_code] = {}
            basic = basic_cache[kapt_code]
        areas = sorted(r["area"] for r in rows)
        out.append({
            "name": s["name"],
            "legal_dong": s["dong"],
            "jibun": s["jibun"],
            "kapt_code": kapt_code or None,
            "road_address": str(pick(basic, "doroJuso") or "").strip() or None,
            "lat": None, "lon": None,
            "households": safe_int(pick(basic, "kaptdaCnt", "hoCnt")),
            "dong_count": safe_int(pick(basic, "kaptDongCnt")),
            "approval_date": fmt_approval(pick(basic, "kaptUsedate")),
            "build_year": s["build_year"],
            "heating": str(pick(basic, "codeHeatNm") or "").strip() or None,
            "trade_count_12m": sum(
                1 for r in rows
                if (as_of - dt.date.fromisoformat(r["date"])).days <= 365),
            "latest_trade_date": rows[0]["date"],
            "recent_trades": [
                {"date": r["date"], "area": r["area"], "amount": r["amount"], "floor": r["floor"]}
                for r in rows[:RECENT_TRADES]],
            "_median_area": areas[len(areas) // 2],
            "_trade_rows": len(rows),
        })
    return out


def rank_into_dongs(complexes, dong_order, as_of):
    dongs = {n: {"candidate_count": 0, "apartments": []} for n in dong_order}
    for c in complexes:
        if c.get("admin_dong") in dongs:
            dongs[c["admin_dong"]]["apartments"].append(c)
    for name, info in dongs.items():
        pool = [c for c in info["apartments"] if c["_median_area"] >= MIN_MEDIAN_AREA]
        info["candidate_count"] = len(pool)
        if not pool:
            info["apartments"] = []
            continue
        max_h = max(c["households"] or 0 for c in pool)
        max_t = max(c["trade_count_12m"] for c in pool) or 1
        # K-APT 권한이 없으면 세대수가 비어 있다. 그때는 남은 두 신호로 가중치를 다시 나눈다.
        w_h = W_HOUSEHOLDS if max_h else 0.0
        scale = 1.0 if w_h else 1 / (W_TRADES + W_RECENCY)
        for c in pool:
            days = max(0, (as_of - dt.date.fromisoformat(c["latest_trade_date"])).days)
            c["representative_score"] = round(
                w_h * (c["households"] or 0) / (max_h or 1)
                + scale * W_TRADES * c["trade_count_12m"] / max_t
                + scale * W_RECENCY * max(0.0, 1 - days / 365), 3)
        pool.sort(key=lambda c: -c["representative_score"])
        picked = []
        for i, c in enumerate(pool[:TOP_N]):
            c = {k: v for k, v in c.items() if not k.startswith("_")}
            hh = f'{c["households"]:,}세대' if c["households"] else "세대수 미확인"
            c["representative_reason"] = (
                ("대표 단지 · " if i == 0 else "") + f'{hh} · 최근 1년 매매 {c["trade_count_12m"]}건')
            c["data_as_of"] = as_of.isoformat()
            c["admin_dong"] = name
            c["dong"] = name
            picked.append(c)
        info["apartments"] = picked
    return dongs


def ranking_note(dongs):
    """세대수를 하나도 못 받았으면 가중치 표기를 실제 사용분에 맞춘다."""
    has_hh = any(a.get("households") for v in dongs.values() for a in v["apartments"])
    base = f"행정동 내 최댓값 대비 정규화, 전용 {MIN_MEDIAN_AREA:.0f}㎡ 미만 위주 단지 제외"
    if has_hh:
        return {"households": W_HOUSEHOLDS, "trade_count_12m": W_TRADES,
                "recency": W_RECENCY, "note": base}
    total = W_TRADES + W_RECENCY
    return {"households": 0, "trade_count_12m": round(W_TRADES / total, 2),
            "recency": round(W_RECENCY / total, 2),
            "note": base + " · K-APT 세대수를 받지 못해 거래량·최근성만 사용"}


def write_payload(gu, slug, payload):
    var = slug.upper() + "_DETAIL"
    (DATA_DIR / f"{slug}_detail.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA_DIR / f"{slug}_detail.js").write_text(
        f"// {gu} 행정동별 대표 단지·실거래 데이터 — scripts/fetch_district_detail.py 생성\n"
        f"window.{var} = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")


def build_district(gu, key, months, backends, cache, as_of, geocode_limit):
    gu_code, slug = DISTRICTS[gu]
    print(f"[{gu}] 시군구코드 {gu_code}")
    geo = load_dong_geo(gu_code)
    features = geo["features"]
    dong_order = [f["properties"]["ADM_KOR_NM"] for f in features]

    trades = fetch_trades(key, gu_code, months, dong_order)
    if not trades:
        print(f"  [건너뜀] 실거래 0건 — 기존 파일을 유지합니다.")
        return None
    grouped = group_complexes(trades)
    print(f"  실거래 {len(trades)}건 · 단지 {len(grouped)}곳")

    try:
        kapt_list = fetch_kapt_list(key, gu_code)
        print(f"  K-APT {len(kapt_list)}단지")
    except ApiError as e:
        kapt_list = []
        print(f"  [경고] K-APT 단지목록 사용 불가, 실거래만으로 진행 — {e}")

    complexes = build_complexes(grouped, key, kapt_list, as_of)
    got = resolve_coords(complexes, gu, gu_code, backends, cache, geocode_limit)
    print(f"  좌표: 신규 {got}곳 · 보유 {sum(1 for c in complexes if c['lat'])}/{len(complexes)}곳")

    unplaced = 0
    for c in complexes:
        c["admin_dong"] = dong_at(features, c["lat"], c["lon"]) if c["lat"] else None
        if not c["admin_dong"]:
            unplaced += 1
    placed = len(complexes) - unplaced
    print(f"  행정동 배정: {placed}/{len(complexes)}곳" + (f" · 미배정 {unplaced}곳" if unplaced else ""))
    if not placed:
        print(f"  [건너뜀] 행정동에 배정된 단지가 없어 기존 파일을 유지합니다.")
        return None

    dongs = rank_into_dongs(complexes, dong_order, as_of)
    payload = {
        "gu": gu,
        "level": "행정동",
        "generated": as_of.isoformat(),
        "source_note": ("실거래: 국토교통부 아파트 매매 실거래가 상세자료(해제건 제외) · "
                        "단지정보: K-APT · 행정동 배정: 단지 좌표 point-in-polygon"),
        "transaction_as_of": as_of.isoformat(),
        "ranking": ranking_note(dongs),
        "stats": {
            "apartment_count": sum(len(v["apartments"]) for v in dongs.values()),
            "trade_rows": len(trades),
            "complexes": len(complexes),
            "geocoded": placed,
            "months": months,
        },
        "dongs": dongs,
    }
    write_payload(gu, slug, payload)
    for n, v in dongs.items():
        print(f"    {n}: " + (" / ".join(a["name"] for a in v["apartments"]) or "없음"))
    return payload


def probe(key, backends):
    """쓰기 없이 각 API 가용성과 응답 필드를 확인한다."""
    print("=== API 점검 ===")
    ym = month_keys(2)[-1]
    try:
        items, total = response_items(request_bytes(TRADE_URL, {
            "serviceKey": key, "LAWD_CD": "11440", "DEAL_YMD": ym,
            "pageNo": 1, "numOfRows": 5}))
        print(f"[OK] 실거래가 (마포 {ym}): {total}건")
        if items:
            print("     필드:", ", ".join(sorted(items[0])))
    except ApiError as e:
        print(f"[실패] 실거래가: {e}")

    kapt_code = None
    try:
        items, total = response_items(request_bytes(KAPT_LIST_URL, {
            "serviceKey": key, "sidoCode": SIDO_CODE, "pageNo": 1,
            "numOfRows": 5, "_type": "json"}))
        print(f"[OK] K-APT 단지목록: 서울 {total}단지")
        if items:
            print("     필드:", ", ".join(sorted(items[0])))
            kapt_code = str(pick(items[0], "kaptCode") or "") or None
    except ApiError as e:
        print(f"[실패] K-APT 단지목록: {e}")

    if kapt_code:
        try:
            items, _ = response_items(request_bytes(KAPT_BASIC_URL, {
                "serviceKey": key, "kaptCode": kapt_code, "_type": "json"}))
            row = items[0] if items else {}
            print(f"[OK] K-APT 기본정보 ({kapt_code}): 필드 {len(row)}개")
            print("     필드:", ", ".join(sorted(row)))
            coord = [k for k in row if re.search(r"(lat|lon|lng|x$|y$|coord|위도|경도)", k, re.I)]
            print("     좌표 후보 필드:", ", ".join(coord) or "없음 → 지오코딩 필요")
        except ApiError as e:
            print(f"[실패] K-APT 기본정보: {e}")

    sample = "서울특별시 마포구 상암동 1601"
    if not backends:
        print("[없음] 지오코더 키가 설정되지 않았습니다 (VWORLD_API_KEY / JUSO_API_KEY).")
    for name, fn in backends:
        try:
            got = fn(sample)
            print(f"[{'OK' if got else '실패'}] {name} 지오코딩 '{sample}' → {got}")
        except Exception as e:
            print(f"[실패] {name} 지오코딩: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("districts", nargs="*", help="자치구 이름 (예: 마포구 은평구 서대문구)")
    ap.add_argument("--all", action="store_true", help="서울 25개 구 전부")
    ap.add_argument("--months", type=int, default=12, help="실거래 조회 개월 수 (기본 12)")
    ap.add_argument("--probe", action="store_true", help="쓰기 없이 API 가용성만 점검")
    ap.add_argument("--geocode-limit", type=int, default=None, help="이번 실행에서 새로 지오코딩할 최대 단지 수")
    ap.add_argument("--key")
    args = ap.parse_args()

    key = load_key(args.key)
    backends = make_geocoder()
    if args.probe:
        probe(key, backends)
        return 0

    targets = list(DISTRICTS) if args.all else args.districts
    unknown = [g for g in targets if g not in DISTRICTS]
    if unknown:
        sys.exit(f"[오류] 알 수 없는 자치구: {', '.join(unknown)}")
    if not targets:
        sys.exit("[오류] 자치구를 지정하거나 --all 을 쓰세요. 점검만 하려면 --probe.")

    cache = _coord_cache()
    as_of = dt.date.today()
    made = []
    for gu in targets:
        try:
            if build_district(gu, key, args.months, backends, cache, as_of, args.geocode_limit):
                made.append(gu)
        except ApiError as e:
            print(f"::warning::{gu} 상세 데이터 생성 실패 — {e}")
        finally:
            _save_cache(cache)
    print(f"[완료] {len(made)}/{len(targets)}개 구 생성: {', '.join(made) or '없음'}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
