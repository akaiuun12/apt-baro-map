# -*- coding: utf-8 -*-
"""청약홈(한국부동산원) 오픈API에서 서울 자치구별 청약 예정/접수중 정보를 받아
data/cheongyak.js / data/cheongyak.json 으로 저장한다.

- 공공데이터포털 "한국부동산원_청약홈 분양정보 조회 서비스" (odcloud)
  https://www.data.go.kr/data/15098547/openapi.do
- 수집 대상: APT 분양정보 + APT 무순위/잔여세대
- 공급위치 주소(HSSPLY_ADRES)에서 서울 자치구를 뽑아 구별로 묶는다.
- 접수 종료일이 오늘 이후인 건만 남긴다(예정 / 접수중).

사용법:
    python scripts/fetch_cheongyak.py            # CHEONGYAK_API_KEY 환경변수 또는 .env
    python scripts/fetch_cheongyak.py --key <인증키>
    python scripts/fetch_cheongyak.py --days 120 # 오늘부터 N일 이내 접수 건만 (기본 90)

인증키 발급: 공공데이터포털에서 위 서비스 활용신청 후 발급되는 '일반 인증키(Decoding)'.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

BASE = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_JSON = DATA_DIR / "cheongyak.json"
OUT_JS = DATA_DIR / "cheongyak.js"

# 오퍼레이션 → 화면에 쓸 유형 이름.
# 서비스 명세가 바뀌면 이 표만 고치면 된다.
OPERATIONS = [
    ("getAPTLttotPblancDetail", "APT"),
    ("getRemndrLttotPblancDetail", "무순위·잔여세대"),
]

SEOUL_GUS = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구",
    "강북구", "도봉구", "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구",
    "구로구", "금천구", "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구", "강동구",
]

# 접수일 후보 필드. 오퍼레이션마다 이름이 달라 둘 다 담아 두고,
#   APT      : 특별공급 + 일반 1·2순위(해당지역/기타경기/기타지역)로 쪼개져 있다
#   무순위   : SUBSCRPT_RCEPT_* (청약접수) / GNRL_RCEPT_* (일반접수)
# 존재하는 것 중 가장 이른 날짜를 시작, 가장 늦은 날짜를 종료로 본다.
# 계약기간(CNTRCT_CNCLS_*)은 접수일이 아니므로 넣지 않는다.
BEGIN_FIELDS = [
    "RCEPT_BGNDE", "SPSPLY_RCEPT_BGNDE", "SUBSCRPT_RCEPT_BGNDE", "GNRL_RCEPT_BGNDE",
    "GNRL_RNK1_CRSPAREA_RCPTDE", "GNRL_RNK1_ETC_GG_RCPTDE", "GNRL_RNK1_ETC_AREA_RCPTDE",
    "GNRL_RNK2_CRSPAREA_RCPTDE", "GNRL_RNK2_ETC_GG_RCPTDE", "GNRL_RNK2_ETC_AREA_RCPTDE",
]
END_FIELDS = [
    "RCEPT_ENDDE", "SPSPLY_RCEPT_ENDDE", "SUBSCRPT_RCEPT_ENDDE", "GNRL_RCEPT_ENDDE",
    "GNRL_RNK1_CRSPAREA_ENDDE", "GNRL_RNK1_ETC_GG_ENDDE", "GNRL_RNK1_ETC_AREA_ENDDE",
    "GNRL_RNK2_CRSPAREA_ENDDE", "GNRL_RNK2_ETC_GG_ENDDE", "GNRL_RNK2_ETC_AREA_ENDDE",
]

PAGE = 1000


class ApiError(Exception):
    pass


def load_key(cli_key):
    if cli_key:
        return cli_key.strip()
    if os.environ.get("CHEONGYAK_API_KEY"):
        return os.environ["CHEONGYAK_API_KEY"].strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("CHEONGYAK_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(
        "[오류] 청약홈 인증키가 없습니다. .env 에 CHEONGYAK_API_KEY=발급받은키 를 넣거나 "
        "--key 옵션을 사용하세요.\n"
        "발급: https://www.data.go.kr/data/15098547/openapi.do (일반 인증키 Decoding)"
    )


def api_get(op, key, page, extra):
    params = {"page": page, "perPage": PAGE, "serviceKey": key}
    params.update(extra)
    url = f"{BASE}/{op}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "apt-baro-map/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ApiError(f"{op} HTTP {e.code} — {detail}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"{op} 연결 실패 — {e.reason}") from None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ApiError(f"{op} 응답이 JSON이 아닙니다 — {body[:300]}") from None


def fetch_op(op, key):
    """한 오퍼레이션의 서울 공급 건을 모두 받는다."""
    rows, page = [], 1
    # 서울만 서버에서 걸러 받는다. 필터가 통하지 않는 서비스면 전체를 받아 아래에서 거른다.
    extra = {"cond[SUBSCRPT_AREA_CODE_NM::EQ]": "서울"}
    while True:
        data = api_get(op, key, page, extra)
        chunk = data.get("data") or []
        rows.extend(chunk)
        total = data.get("totalCount") or data.get("matchCount") or 0
        if not chunk or len(rows) >= total or page > 50:
            break
        page += 1
    return rows


def pick_dates(row, fields):
    out = [str(row.get(f)).strip() for f in fields if row.get(f)]
    return sorted(d for d in out if len(d) == 10 and d[4] == "-")


def gu_of(row):
    addr = " ".join(str(row.get(f, "")) for f in ("HSSPLY_ADRES", "SUBSCRPT_AREA_CODE_NM", "HOUSE_NM"))
    if "서울" not in addr:
        return None
    for g in SEOUL_GUS:
        if g in addr:
            return g
    return None


def normalize(row, kind, today, horizon, undated):
    gu = gu_of(row)
    if not gu:
        return None, None
    begins, ends = pick_dates(row, BEGIN_FIELDS), pick_dates(row, END_FIELDS)
    begin = begins[0] if begins else None
    end = ends[-1] if ends else begin
    if not end:
        # 접수일 필드를 하나도 못 찾았다 = 서비스 명세가 바뀌었을 수 있다.
        # 조용히 버리면 "0건"으로만 보이므로, 첫 사례의 키 목록을 남긴다.
        undated.append(row)
        return None, None
    if end < today:                     # 이미 끝난 건은 제외
        return None, None
    if begin and begin > horizon:       # 너무 먼 미래는 제외
        return None, None

    def s(field):
        v = row.get(field)
        v = "" if v is None else str(v).strip()
        return v or None

    try:
        households = int(float(row.get("TOT_SUPLY_HSHLDCO")))
    except (TypeError, ValueError):
        households = None

    return gu, {
        "name": s("HOUSE_NM") or "(단지명 없음)",
        "kind": kind,
        "detail": s("HOUSE_DTL_SECD_NM") or s("HOUSE_SECD_NM"),
        "addr": s("HSSPLY_ADRES"),
        "households": households,
        "notice": s("RCRIT_PBLANC_DE"),
        "begin": begin,
        "end": end,
        "award": s("PRZWNER_PRESNATN_DE"),
        "url": s("PBLANC_URL") or s("HMPG_ADRES"),
        "status": "접수중" if begin and begin <= today <= end else "예정",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key")
    ap.add_argument("--days", type=int, default=90, help="오늘부터 N일 이내 접수 건만 (기본 90)")
    args = ap.parse_args()

    key = load_key(args.key)
    today = datetime.date.today()
    horizon = (today + datetime.timedelta(days=args.days)).isoformat()
    today_s = today.isoformat()

    regions, total = {}, 0
    for op, kind in OPERATIONS:
        rows = fetch_op(op, key)
        kept, undated = 0, []
        for r in rows:
            gu, item = normalize(r, kind, today_s, horizon, undated)
            if item:
                regions.setdefault(gu, []).append(item)
                kept += 1
        total += kept
        print(f"  {kind}: 서울 {len(rows)}건 중 {kept}건 (예정·접수중)"
              + (f" · 접수일 없음 {len(undated)}건" if undated else ""))
        if undated:
            print(f"    [확인 필요] {op} 응답에서 접수일 필드를 찾지 못했습니다. "
                  f"BEGIN_FIELDS / END_FIELDS 를 아래 키와 맞춰 주세요:")
            print("    " + ", ".join(sorted(undated[0].keys())))

    for lst in regions.values():
        lst.sort(key=lambda x: (x["begin"] or "9999", x["name"]))

    payload = {
        "source": "한국부동산원 청약홈 (공공데이터포털 오픈API)",
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "asOf": today_s,
        "horizon": horizon,
        "kinds": [k for _, k in OPERATIONS],
        "regions": dict(sorted(regions.items())),
    }
    DATA_DIR.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_JS.write_text("window.CHEONGYAK = " + json.dumps(payload, ensure_ascii=False) + ";\n",
                      encoding="utf-8")
    print(f"[완료] {len(regions)}개 자치구 · {total}건 → data/cheongyak.js")


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        sys.exit(f"[API 오류] {e}")
