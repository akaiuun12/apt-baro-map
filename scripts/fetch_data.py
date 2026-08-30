# -*- coding: utf-8 -*-
"""한국부동산원 R-ONE 오픈API에서 주간 아파트 매매가격지수(서울 자치구)를 받아
data/latest.js / data/latest.json 으로 저장한다.

- 시점 식별자(WRTTIME_IDTFR_ID)는 YYYYWW(연도+주차) 형식. 예: 202635 = 2026-08-24 주
- 첫 실행 시 전체 이력(2012~)을 받아 data/history.json 에 캐시하고,
  이후 실행은 마지막 주 이후의 새 데이터만 증분으로 받는다.

사용법:
    python scripts/fetch_data.py                # RONE_API_KEY 환경변수 또는 .env 사용
    python scripts/fetch_data.py --key <인증키>
    python scripts/fetch_data.py --list         # 주간(WK) 통계표 후보 목록만 출력
    python scripts/fetch_data.py --statbl-id T244183132827305   # 통계표 ID 직접 지정
    python scripts/fetch_data.py --full         # 캐시 무시하고 전체 이력 다시 수신

인증키 발급: https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do
"""
import argparse
import datetime
import sys
if hasattr(sys.stdout, "reconfigure"):  # Windows cp949 콘솔에서 특수문자로 죽지 않게
    sys.stdout.reconfigure(errors="replace")
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.reb.or.kr/r-one/openapi"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_PATH = DATA_DIR / "config.json"
HISTORY_PATH = DATA_DIR / "history.json"

SEOUL_GUS = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구",
    "강북구", "도봉구", "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구",
    "구로구", "금천구", "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구", "강동구",
]

PAGE = 1000


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


def load_key(cli_key):
    if cli_key:
        return cli_key.strip()
    import os
    if os.environ.get("RONE_API_KEY"):
        return os.environ["RONE_API_KEY"].strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("RONE_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(
        "[오류] 인증키가 없습니다. .env 파일에 RONE_API_KEY=발급받은키 를 넣거나 "
        "--key 옵션을 사용하세요.\n"
        "발급: https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do"
    )


def api_get(path, **params):
    params.setdefault("Type", "json")
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "apt-baro-map/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    if "RESULT" in data:  # 최상위 RESULT는 오류/정보 응답
        raise ApiError(data["RESULT"].get("CODE", "?"), data["RESULT"].get("MESSAGE", ""))
    return data


def rows_of(data, service):
    """{service: [{head:...}, {row:[...]}]} 구조에서 (row 목록, 전체 건수)를 꺼낸다."""
    block = data.get(service)
    if not block:
        return [], 0
    total = 0
    rows = []
    for part in block:
        if "head" in part:
            for h in part["head"]:
                if isinstance(h, dict) and "list_total_count" in h:
                    total = int(h["list_total_count"])
        if "row" in part:
            rows = part["row"]
    return rows, total


def fetch_all(path, service, key, max_pages=250, label="", **params):
    all_rows = []
    p_index = 1
    total = None
    while True:
        rows, total = rows_of(api_get(path, KEY=key, pIndex=p_index, pSize=PAGE, **params), service)
        all_rows.extend(rows)
        if label and total and total > PAGE:
            print(f"\r  {label}: {min(len(all_rows), total)}/{total}행", end="", flush=True)
        if not rows or len(all_rows) >= total or p_index >= max_pages:
            break
        p_index += 1
    if label and total and total > PAGE:
        print()
    return all_rows


def find_weekly_table(key, list_only=False):
    """주간(WK) 주기 통계표 중 아파트 매매가격 관련 표를 찾는다."""
    tables = fetch_all("SttsApiTbl.do", "SttsApiTbl", key)
    weekly = [t for t in tables if "WK" in str(t.get("DTACYCLE_CD", "")).upper()
              or "WEEK" in str(t.get("DTACYCLE_CD", "")).upper()]
    if list_only or not weekly:
        pool = weekly or tables
        print(f"통계표 {len(tables)}개 중 주간 주기 {len(weekly)}개:")
        for t in pool:
            print(f"  {t.get('STATBL_ID')}  [{t.get('DTACYCLE_CD')}]  {t.get('STATBL_NM')}")
        if list_only:
            sys.exit(0)
        sys.exit("[오류] 주간 주기 통계표를 찾지 못했습니다. --list로 확인 후 --statbl-id로 지정하세요.")

    def score(t):
        name = str(t.get("STATBL_NM", ""))
        s = 0
        if "매매" in name:
            s += 4
        if "가격지수" in name or "지수" in name:
            s += 2
        if "규모" in name or "연령" in name or "수급" in name:
            s -= 3
        if "전세" in name or "월세" in name:
            s -= 5
        return s

    weekly.sort(key=score, reverse=True)
    best = weekly[0]
    print(f"[선택된 통계표] {best.get('STATBL_ID')}  {best.get('STATBL_NM')}")
    return best["STATBL_ID"], best.get("STATBL_NM", ""), best.get("DTACYCLE_CD", "WK")


def load_history(statbl_id):
    if HISTORY_PATH.exists():
        h = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if h.get("statblId") == statbl_id:
            return h
    return {"statblId": statbl_id, "weekDesc": {}, "itemName": "", "seoul": {}, "regions": {}}


def merge_rows(hist, rows):
    """API row들을 history 구조에 병합한다. 반환: 새로 들어온 주 수"""
    # 항목이 여러 개면 변동률 우선, 없으면 지수
    items = {str(r.get("ITM_NM", "")) for r in rows}
    item = next((i for i in items if "변동" in i), None) or (next(iter(items)) if items else "")
    hist["itemName"] = item

    new_weeks = set()
    for r in rows:
        if str(r.get("ITM_NM", "")) != item:
            continue
        cls_nm = str(r.get("CLS_NM", "")).strip()
        full = str(r.get("CLS_FULLNM", cls_nm))
        wk = str(r.get("WRTTIME_IDTFR_ID", ""))
        desc = str(r.get("WRTTIME_DESC", wk)).strip()
        try:
            val = float(r.get("DTA_VAL"))
        except (TypeError, ValueError):
            continue
        gu = next((g for g in SEOUL_GUS if cls_nm == g), None)
        if gu and full.startswith("서울"):
            if wk not in hist["weekDesc"]:
                new_weeks.add(wk)
            hist["weekDesc"][wk] = desc
            hist["regions"].setdefault(gu, {})[wk] = val
        elif cls_nm in ("서울", "서울특별시"):
            if wk not in hist["weekDesc"]:
                new_weeks.add(wk)
            hist["weekDesc"][wk] = desc
            hist["seoul"][wk] = val
    return len(new_weeks)


def build_payload(hist, statbl_id, statbl_nm, since=None):
    week_ids = sorted(hist["weekDesc"].keys())
    if since:  # 변동률 계산을 위해 시작점 한 주 앞까지 포함
        keep = [w for w in week_ids if hist["weekDesc"][w] >= since]
        if keep:
            i = week_ids.index(keep[0])
            week_ids = week_ids[max(0, i - 1):]
    if not week_ids:
        sys.exit("[오류] 저장할 주가 없습니다.")

    item = hist.get("itemName", "지수")
    is_index = "변동" not in item

    def pct_series(mapping):
        out = []
        for i, w in enumerate(week_ids):
            if not is_index:
                out.append(round(mapping[w], 2) if w in mapping else None)
                continue
            pw = week_ids[i - 1] if i > 0 else None
            if pw and mapping.get(pw) and mapping.get(w) is not None:
                out.append(round((mapping[w] - mapping[pw]) / mapping[pw] * 100, 2))
            else:
                out.append(None)
        return out

    def raw_series(mapping):
        return [round(mapping[w], 2) if w in mapping else None for w in week_ids]

    payload = {
        "source": "한국부동산원 주간아파트가격동향 (R-ONE 오픈API)",
        "isSample": False,
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "statblId": statbl_id,
        "statblNm": statbl_nm,
        "itemName": item + (" → 주간 변동률(계산)" if is_index else ""),
        "unit": "%",
        "weekIds": week_ids,
        "weeks": [hist["weekDesc"][w] for w in week_ids],
        "seoul": pct_series(hist["seoul"]),
        "regions": {g: pct_series(m) for g, m in sorted(hist["regions"].items())},
    }
    if is_index:  # 지수 원값도 함께 저장 (시계열 차트용)
        payload["seoulIndex"] = raw_series(hist["seoul"])
        payload["regionsIndex"] = {g: raw_series(m) for g, m in sorted(hist["regions"].items())}
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key")
    ap.add_argument("--statbl-id")
    ap.add_argument("--list", action="store_true", help="주간 통계표 후보 목록 출력")
    ap.add_argument("--full", action="store_true", help="캐시 무시하고 전체 이력 다시 수신")
    ap.add_argument("--since", default=None, help="화면에 담을 시작일 (YYYY-MM-DD, 기본: 전체)")
    args = ap.parse_args()

    key = load_key(args.key)

    config = {}
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    try:
        if args.list:
            find_weekly_table(key, list_only=True)

        statbl_id = args.statbl_id or config.get("statblId")
        statbl_nm = config.get("statblNm", "")
        cycle = config.get("dtacycleCd", "WK")
        if not statbl_id:
            statbl_id, statbl_nm, cycle = find_weekly_table(key)
        CONFIG_PATH.write_text(
            json.dumps({"statblId": statbl_id, "statblNm": statbl_nm, "dtacycleCd": cycle},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        hist = load_history(statbl_id)
        if args.full:
            hist = {"statblId": statbl_id, "weekDesc": {}, "itemName": "", "seoul": {}, "regions": {}}

        # 연도별로 나눠 받고 연도마다 저장 -> 중단돼도 다음 실행에서 이어받는다.
        # 시점 식별자는 YYYYWW(연도+주차) 형식.
        have_weeks = sorted(hist["weekDesc"].keys())
        this_year = datetime.date.today().year
        start_year = int(have_weeks[-1][:4]) if have_weeks else 2012
        if have_weeks:
            print(f"[증분 수신] 저장된 마지막 주 {have_weeks[-1]} 이후를 확인합니다...")
        else:
            print(f"[전체 수신] {start_year}~{this_year}년 이력을 연도별로 받습니다 (수 분 걸릴 수 있음)...")

        added = 0
        for y in range(start_year, this_year + 1):
            start = have_weeks[-1] if (have_weeks and y == start_year) else f"{y}01"
            try:
                rows = fetch_all("SttsApiTblData.do", "SttsApiTblData", key, label=f"{y}년",
                                 STATBL_ID=statbl_id, DTACYCLE_CD=cycle,
                                 START_WRTTIME=start, END_WRTTIME=f"{y}53")
            except ApiError as e:
                if e.code == "INFO-200":  # 그 해 데이터 없음
                    continue
                raise
            added += merge_rows(hist, rows)
            HISTORY_PATH.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
            print(f"  {y}년 완료 (누적 {len(hist['weekDesc'])}주)", flush=True)
    except ApiError as e:
        sys.exit(f"[API 오류] {e}\n--list 로 통계표를 확인하고 --statbl-id 로 지정해 보세요.")
    if not hist["weekDesc"]:
        sys.exit("[오류] 서울 자치구 데이터를 찾지 못했습니다. --list 로 통계표를 확인하세요.")

    HISTORY_PATH.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")

    payload = build_payload(hist, statbl_id, statbl_nm, since=args.since)

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (DATA_DIR / "latest.js").write_text(
        "window.APT_DATA = " + json.dumps(payload, ensure_ascii=False) + ";", encoding="utf-8")

    missing = [g for g in SEOUL_GUS if g not in hist["regions"]]
    wk = payload["weeks"]
    print(f"[완료] {len(hist['regions'])}개 자치구 · {wk[0]} ~ {wk[-1]} ({len(wk)}주) → data/latest.js"
          + (f" (새로 {added}주 추가)" if have_weeks else ""))
    if missing:
        print(f"  자료 없는 구(빗금 표시): {', '.join(missing)}")
    print("  index.html 을 브라우저로 열어 확인하세요.")


if __name__ == "__main__":
    main()
