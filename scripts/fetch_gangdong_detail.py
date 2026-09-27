# -*- coding: utf-8 -*-
"""강동구 파일럿용 법정동별 대표 아파트 + 최근 실거래가 데이터 생성.

데이터 원천
- 국토교통부 아파트 매매 실거래가 상세자료
  https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev
- 국토교통부 공동주택 단지 목록제공 서비스
  https://apis.data.go.kr/1613000/AptListService3/getSidoAptList3
- 국토교통부 공동주택 기본 정보제공 서비스 V4
  https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4

공공데이터포털 인증키 하나를 사용하지만 각 서비스는 별도의 활용신청이 필요하다.
K-APT 권한이 없으면 세대수 등 부가정보 없이 실거래가 기준으로 대표단지를 선정한다.
실거래가 권한이 없으면 기존 파일을 덮어쓰지 않고 종료한다.

사용법:
  DATA_GO_KR_API_KEY=... python scripts/fetch_gangdong_detail.py
  python scripts/fetch_gangdong_detail.py --key ... --months 24
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_JSON = DATA_DIR / "gangdong_detail.json"
OUT_JS = DATA_DIR / "gangdong_detail.js"

LAWD_CD = "11740"
SIDO_CODE = "11"
DONG_CODES = {
    "11740101": "명일동",
    "11740102": "고덕동",
    "11740103": "상일동",
    "11740105": "길동",
    "11740106": "둔촌동",
    "11740107": "암사동",
    "11740108": "성내동",
    "11740109": "천호동",
    "11740110": "강일동",
}
DONG_NAMES = list(DONG_CODES.values())

TRADE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
KAPT_LIST_URL = "https://apis.data.go.kr/1613000/AptListService3/getSidoAptList3"
KAPT_BASIC_URL = "https://apis.data.go.kr/1613000/AptBasisInfoServiceV4/getAphusBassInfoV4"


class ApiError(RuntimeError):
    pass


def load_key(cli_key):
    for v in (cli_key, os.environ.get("DATA_GO_KR_API_KEY"), os.environ.get("MOLIT_API_KEY"),
              os.environ.get("CHEONGYAK_API_KEY")):
        if v and v.strip():
            return urllib.parse.unquote(v.strip())
    env = ROOT / ".env"
    if env.exists():
        vals = {}
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
        for k in ("DATA_GO_KR_API_KEY", "MOLIT_API_KEY", "CHEONGYAK_API_KEY"):
            if vals.get(k):
                return urllib.parse.unquote(vals[k])
    sys.exit("[오류] 공공데이터포털 인증키가 없습니다. DATA_GO_KR_API_KEY를 설정하세요.")


def request_bytes(base, params, retries=2):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(base + "?" + q, headers={"User-Agent": "apt-baro-map/1.0"})
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            last = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    if isinstance(last, urllib.error.HTTPError):
        try:
            detail = last.read().decode("utf-8", "replace")[:500]
        except Exception:
            detail = ""
        raise ApiError(f"HTTP {last.code}: {detail}")
    raise ApiError(f"연결 실패: {getattr(last, 'reason', last)}")


def xml_items(blob):
    text = blob.decode("utf-8", "replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise ApiError("XML 파싱 실패: " + text[:300])
    code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
    msg = root.findtext(".//resultMsg") or root.findtext(".//returnAuthMsg")
    if code and str(code).strip() not in ("00", "000"):
        raise ApiError(f"API {code}: {msg or '오류'}")
    out = []
    for node in root.findall(".//item"):
        row = {}
        for child in list(node):
            tag = child.tag.rsplit("}", 1)[-1]
            row[tag] = (child.text or "").strip()
        out.append(row)
    total = root.findtext(".//totalCount")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(out)
    return out, total


def response_items(blob):
    stripped = blob.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        data = json.loads(blob.decode("utf-8"))
        resp = data.get("response", data) if isinstance(data, dict) else data
        if isinstance(resp, dict):
            header = resp.get("header") or {}
            code = header.get("resultCode") or resp.get("returnReasonCode")
            msg = header.get("resultMsg") or resp.get("returnAuthMsg")
            if code is not None and str(code).strip() not in ("00", "000"):
                raise ApiError(f"API {code}: {msg or '오류'}")
            body = resp.get("body") or resp
            items = body.get("items") if isinstance(body, dict) else None
            if isinstance(items, dict):
                items = items.get("item", [])
            if items is None and isinstance(body, dict):
                items = body.get("item", [])
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                items = []
            try:
                total = int(body.get("totalCount", len(items)))
            except (TypeError, ValueError):
                total = len(items)
            return items, total
    return xml_items(blob)


def month_keys(n):
    today = dt.date.today()
    y, m = today.year, today.month
    keys = []
    for _ in range(n):
        keys.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            y -= 1
            m = 12
    return list(reversed(keys))


def safe_int(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def safe_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def pick(row, *keys):
    lower = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
        v = lower.get(k.lower())
        if v not in (None, ""):
            return v
    return None


def norm_name(v):
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", str(v or "")).lower()
    for token in ("아파트", "apt"):
        s = s.replace(token, "")
    return s


def trade_date(row):
    try:
        y = int(pick(row, "dealYear"))
        m = int(pick(row, "dealMonth"))
        d = int(pick(row, "dealDay"))
        return dt.date(y, m, d)
    except Exception:
        return None


def fetch_trades(key, months):
    all_rows = []
    for ym in month_keys(months):
        blob = request_bytes(TRADE_URL, {
            "serviceKey": key, "LAWD_CD": LAWD_CD, "DEAL_YMD": ym,
            "pageNo": 1, "numOfRows": 9999,
        })
        rows, total = response_items(blob)
        if total > len(rows):
            # 보통 강동구 한 달은 9999건 미만이지만, 안전하게 페이지를 더 읽는다.
            page = 2
            while len(rows) < total:
                more, _ = response_items(request_bytes(TRADE_URL, {
                    "serviceKey": key, "LAWD_CD": LAWD_CD, "DEAL_YMD": ym,
                    "pageNo": page, "numOfRows": 9999,
                }))
                if not more:
                    break
                rows.extend(more)
                page += 1
        kept = 0
        for r in rows:
            dong = str(pick(r, "umdNm") or "").strip()
            if dong not in DONG_NAMES:
                continue
            # 취소된 거래는 현재 실거래 목록/대표성 집계에서 제외한다.
            if str(pick(r, "cdealType") or "").strip() in ("O", "Y", "1"):
                continue
            if str(pick(r, "cdealDay") or "").strip():
                continue
            d = trade_date(r)
            if not d:
                continue
            amt = safe_int(pick(r, "dealAmount"))
            area = safe_float(pick(r, "excluUseAr"))
            if amt is None or area is None:
                continue
            all_rows.append({
                "apt_seq": str(pick(r, "aptSeq") or "").strip(),
                "name": str(pick(r, "aptNm") or "").strip(),
                "dong": dong,
                "dong_code": str(pick(r, "umdCd") or "").strip(),
                "jibun": str(pick(r, "jibun") or "").strip(),
                "road": str(pick(r, "roadNm") or "").strip(),
                "date": d.isoformat(),
                "area": round(area, 2),
                "amount": amt,  # 만원
                "floor": safe_int(pick(r, "floor")),
                "build_year": safe_int(pick(r, "buildYear")),
                "registration_date": str(pick(r, "rgstDate") or "").strip() or None,
            })
            kept += 1
        print(f"  실거래 {ym}: {kept}건")
    return all_rows


def fetch_kapt_list(key):
    rows = []
    page = 1
    while True:
        blob = request_bytes(KAPT_LIST_URL, {
            "serviceKey": key, "sidoCode": SIDO_CODE,
            "pageNo": page, "numOfRows": 1000, "_type": "json",
        })
        chunk, total = response_items(blob)
        rows.extend(chunk)
        if not chunk or len(rows) >= total:
            break
        page += 1
        if page > 20:
            break
    out = []
    for r in rows:
        code = str(pick(r, "bjdCode") or "")
        if code.startswith(LAWD_CD):
            out.append(r)
    print(f"  K-APT 서울 {len(rows)}단지 중 강동구 {len(out)}단지")
    return out


def fetch_kapt_basic(key, kapt_code):
    blob = request_bytes(KAPT_BASIC_URL, {
        "serviceKey": key, "kaptCode": kapt_code, "_type": "json",
    })
    rows, _ = response_items(blob)
    return rows[0] if rows else {}


def fmt_approval(v):
    s = re.sub(r"\D", "", str(v or ""))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else (s or None)


def percentile(value, values):
    vals = sorted(v for v in values if v is not None)
    if value is None or not vals:
        return None
    if len(vals) == 1:
        return 1.0
    below = sum(v < value for v in vals)
    equal = sum(v == value for v in vals)
    return (below + (equal - 1) / 2) / (len(vals) - 1)


def match_kapt(dong, apt_name, candidates):
    nn = norm_name(apt_name)
    same = [x for x in candidates if x.get("_dong") == dong]
    exact = [x for x in same if norm_name(pick(x, "kaptName")) == nn]
    if exact:
        return exact[0]
    fuzzy = []
    for x in same:
        kn = norm_name(pick(x, "kaptName"))
        if nn and kn and (nn in kn or kn in nn) and abs(len(nn) - len(kn)) <= 6:
            fuzzy.append(x)
    return fuzzy[0] if len(fuzzy) == 1 else None


def build_payload(trades, kapt_list, key, months):
    grouped = defaultdict(list)
    for t in trades:
        ident = t["apt_seq"] or f'{t["dong"]}|{norm_name(t["name"])}|{t["jibun"]}'
        grouped[ident].append(t)

    # K-APT 목록에 법정동명을 붙인다.
    for k in kapt_list:
        bjd = str(pick(k, "bjdCode") or "")
        k["_dong"] = DONG_CODES.get(bjd[:8])

    # 거래 단지와 K-APT를 먼저 매칭하고, 실제 거래가 있는 강동구 단지만 기본정보 조회.
    kapt_basic_cache = {}
    complexes = []
    cutoff12 = dt.date.today() - dt.timedelta(days=365)
    for ident, rows in grouped.items():
        rows.sort(key=lambda x: x["date"], reverse=True)
        sample = rows[0]
        match = match_kapt(sample["dong"], sample["name"], kapt_list)
        basic = {}
        kapt_code = str(pick(match or {}, "kaptCode") or "")
        if kapt_code:
            if kapt_code not in kapt_basic_cache:
                try:
                    kapt_basic_cache[kapt_code] = fetch_kapt_basic(key, kapt_code)
                    time.sleep(0.03)
                except ApiError as e:
                    print(f"    [경고] K-APT 기본정보 {kapt_code}: {e}")
                    kapt_basic_cache[kapt_code] = {}
            basic = kapt_basic_cache[kapt_code]

        latest = dt.date.fromisoformat(rows[0]["date"])
        count12 = sum(dt.date.fromisoformat(x["date"]) >= cutoff12 for x in rows)
        households = safe_int(pick(basic, "kaptdaCnt", "hoCnt"))
        complexes.append({
            "_id": ident,
            "apt_seq": sample["apt_seq"] or None,
            "kapt_code": kapt_code or None,
            "name": sample["name"],
            "dong": sample["dong"],
            "jibun": sample["jibun"] or None,
            "road_address": str(pick(basic, "doroJuso") or sample["road"] or "").strip() or None,
            "address": str(pick(basic, "kaptAddr") or "").strip() or None,
            "households": households,
            "dong_count": safe_int(pick(basic, "kaptDongCnt")),
            "approval_date": fmt_approval(pick(basic, "kaptUsedate")),
            "heating": str(pick(basic, "codeHeatNm") or "").strip() or None,
            "contractor": str(pick(basic, "kaptBcompany") or "").strip() or None,
            "build_year": sample["build_year"],
            "trade_count_12m": count12,
            "latest_trade_date": latest.isoformat(),
            "recent_trades": rows[:30],
            "areas": sorted({round(x["area"], 1) for x in rows}),
        })

    by_dong = defaultdict(list)
    for c in complexes:
        by_dong[c["dong"]].append(c)

    dongs = {}
    today = dt.date.today()
    for dong in DONG_NAMES:
        cs = by_dong.get(dong, [])
        hh_vals = [c["households"] for c in cs if c["households"] is not None]
        tr_vals = [c["trade_count_12m"] for c in cs]
        for c in cs:
            scores = []
            p_hh = percentile(c["households"], hh_vals)
            if p_hh is not None:
                scores.append((0.45, p_hh))
            scores.append((0.35, percentile(c["trade_count_12m"], tr_vals) or 0))
            days = max(0, (today - dt.date.fromisoformat(c["latest_trade_date"])).days)
            scores.append((0.20, max(0.0, 1.0 - days / 365.0)))
            denom = sum(w for w, _ in scores) or 1
            c["representative_score"] = round(sum(w * v for w, v in scores) / denom, 4)
        cs.sort(key=lambda c: (
            c["representative_score"],
            c["trade_count_12m"],
            c["households"] or 0,
        ), reverse=True)
        top = cs[:5]
        for c in top:
            c.pop("_id", None)
        dongs[dong] = {
            "representative": top[0]["apt_seq"] if top and top[0].get("apt_seq") else (top[0]["name"] if top else None),
            "apartments": top,
            "candidate_count": len(cs),
        }

    return {
        "source": {
            "trades": "국토교통부 아파트 매매 실거래가 상세 자료",
            "complexes": "국토교통부 공동주택 기본 정보제공 서비스(K-APT)",
        },
        "generated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "region": "강동구",
        "lawd_cd": LAWD_CD,
        "months": months,
        "ranking": {
            "households": 0.45,
            "trade_count_12m": 0.35,
            "recency": 0.20,
            "note": "K-APT 세대수 미매칭 단지는 사용 가능한 지표 가중치를 재정규화함",
        },
        "stats": {
            "trade_rows": len(trades),
            "trade_complexes": len(grouped),
            "kapt_complexes": len(kapt_list),
            "kapt_matched": sum(c.get("kapt_code") is not None for c in complexes),
        },
        "dongs": dongs,
    }


def write_payload(payload):
    DATA_DIR.mkdir(exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT_JSON.write_text(text + "\n", encoding="utf-8")
    OUT_JS.write_text("window.GANGDONG_DETAIL = " + text + ";\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key")
    ap.add_argument("--months", type=int, default=24)
    args = ap.parse_args()
    key = load_key(args.key)

    print(f"[강동구 상세] 최근 {args.months}개월 실거래 수집")
    try:
        trades = fetch_trades(key, args.months)
    except ApiError as e:
        print(f"::warning::실거래가 API를 사용할 수 없어 강동구 상세 데이터 갱신을 건너뜁니다 — {e}")
        return 0
    if not trades:
        print("::warning::실거래가가 0건이라 기존 강동구 상세 데이터를 유지합니다.")
        return 0

    kapt_list = []
    try:
        kapt_list = fetch_kapt_list(key)
    except ApiError as e:
        print(f"::warning::K-APT 단지목록 API 권한/응답 문제. 실거래가만으로 계속합니다 — {e}")

    payload = build_payload(trades, kapt_list, key, args.months)
    write_payload(payload)
    print("[완료] 강동구 상세:",
          f"실거래 {payload['stats']['trade_rows']}건 · 거래단지 {payload['stats']['trade_complexes']}곳 · "
          f"K-APT 매칭 {payload['stats']['kapt_matched']}곳")
    for dong, info in payload["dongs"].items():
        top = info["apartments"][0]["name"] if info["apartments"] else "없음"
        print(f"  {dong}: 대표 {top} · 후보 {info['candidate_count']}곳")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
