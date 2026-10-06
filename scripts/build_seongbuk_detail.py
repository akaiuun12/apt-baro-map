"""성북구 행정동별 대표 단지 데이터 생성.

입력
- data/sources/seongbuk_trades_20261006.json : 국토교통부 실거래가 공개시스템(rt.molit.go.kr) 성북구 아파트 매매 CSV
                (계약일 2025-10-07 ~ 2026-10-06, 해제건 제외) 에서 후보 단지별 건수·최근 20건 추출본
- 아래 CANDIDATES : 단지 좌표(카카오맵 검색), 기본정보(디아파트 K-APT 연동 정보·나무위키 공동주택 목록·아파트지인)
행정동 배정: 단지 좌표를 행정동 경계(vuski/admdongkor ver20260701, 원본 해상도)에 point-in-polygon.
대표 단지: 세대수 45% + 최근 12개월 거래량 35% + 최근 거래 시점 20% (행정동 내 최댓값 대비 정규화).
          전용 40㎡ 미만 위주 단지는 제외. 길음2동은 사용자 지정(롯데캐슬클라시아) 유지.
"""
import json, datetime, sys

# 사용법: python scripts/build_seongbuk_detail.py /tmp/adm.geojson   (vuski 원본 행정동 경계, build_dong_geo.py 참고)
import os
ROOT = os.path.join(os.path.dirname(__file__), "..")
ADM = sys.argv[1] if len(sys.argv) > 1 else "/tmp/adm.geojson"
AS_OF = datetime.date(2026, 10, 6)
trades = json.load(open(os.path.join(ROOT, "data/sources/seongbuk_trades_20261006.json"), encoding="utf-8"))
adm = json.load(open(ADM, encoding="utf-8"))
F = [f for f in adm["features"] if f["properties"]["sggnm"] == "성북구"]
ORDER = [f["properties"]["adm_nm"].split()[-1] for f in sorted(F, key=lambda f: f["properties"]["adm_cd2"])]

def inring(x, y, r):
    c = False
    for i in range(len(r)):
        x1, y1 = r[i - 1]; x2, y2 = r[i]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c

def which(lat, lon):
    for f in F:
        for poly in f["geometry"]["coordinates"]:
            if inring(lon, lat, poly[0]) and not any(inring(lon, lat, h) for h in poly[1:]):
                return f["properties"]["adm_nm"].split()[-1]
    return None

# key: (법정동|번지) -> name, lat, lon, households, dong_count, approval, heating, road(override), src
C = {
 "동소문동4가|279": ("송산", 37.59220217, 127.01037744, 345, None, None, None, "나무위키"),
 "삼선동2가|425": ("삼선푸르지오", 37.58349197, 127.01338211, 864, 22, "2008-03-27", "개별난방", "K-APT(디아파트)"),
 "삼선동3가|116": ("삼선SK뷰", 37.5874178, 127.01152484, 430, None, None, None, "나무위키"),
 "동소문동7가|23": ("동소문한신휴플러스2차", 37.5951255, 127.01413719, 409, None, None, None, "나무위키"),
 "동소문동7가|120": ("브라운스톤동선", 37.59632836, 127.01382036, 194, 4, "2010-11-26", "개별난방", "K-APT(디아파트)"),
 "돈암동|15-1": ("돈암삼성", 37.59903074, 127.02331372, 1278, 7, "1999-04-30", "개별난방", "K-APT(디아파트)"),
 "돈암동|643": ("길음역금호어울림센터힐", 37.60064992, 127.02282275, 490, None, None, None, "나무위키"),
 "돈암동|633": ("돈암동부센트레빌", 37.6023241, 127.02644935, 540, 9, "2003-09-18", "개별난방", "K-APT(디아파트)"),
 "돈암동|609-1": ("동소문한신·한진", 37.59488264, 127.01016833, 4515, None, "1998-07-01", "중앙난방", "나무위키·K-APT(디아파트)"),
 "돈암동|636": ("브라운스톤돈암", 37.59787123, 127.01779189, 1074, 16, "2004-12-18", "개별난방", "K-APT(디아파트)"),
 "돈암동|644": ("돈암코오롱하늘채", 37.59943241, 127.01257983, 629, 10, "2016-12-29", "개별난방", "K-APT(디아파트)"),
 "안암동1가|361": ("래미안안암", 37.58930715, 127.02374999, 528, None, None, None, "나무위키"),
 "보문동6가|458": ("보문파크뷰자이", 37.5804613, 127.0181421, 1186, 17, "2017-01-18", "개별난방", "K-APT(디아파트)"),
 "보문동3가|230": ("e편한세상보문", 37.58294388, 127.01570744, 440, 7, "2013-12-24", "개별난방", "K-APT(디아파트)"),
 "보문동3가|2": ("보문아이파크", 37.58561969, 127.01671113, 431, None, None, None, "나무위키"),
 "정릉동|1015": ("길음뉴타운경남아너스빌", 37.60420891, 127.01698708, 860, None, None, None, "나무위키"),
 "정릉동|1020": ("정릉우성", 37.60101777, 127.01581769, 823, None, None, None, "나무위키"),
 "정릉동|435": ("정릉중앙하이츠빌2단지", 37.6037754, 127.0103915, 745, 9, "2005-11-16", "개별난방", "K-APT(디아파트)"),
 "정릉동|210": ("정릉푸른마을동아", 37.60749428, 127.01427883, 529, 7, "2003-10-04", "개별난방", "K-APT(디아파트)"),
 "정릉동|494": ("정릉중앙하이츠빌1단지", 37.60278439, 127.00946275, 433, 7, "2004-04-30", "개별난방", "K-APT(디아파트)"),
 "정릉동|809": ("정릉중앙하이츠", 37.61956117, 127.00208418, 261, 4, "1999-05-14", "개별난방", "K-APT(디아파트)"),
 "정릉동|1019": ("정릉성원상떼빌", 37.60650376, 127.00838508, 271, None, None, None, "아파트지인"),
 "정릉동|239": ("정릉풍림아이원", 37.61858429, 127.00730358, 1971, 28, "2005-12-28", "개별난방", "K-APT(디아파트)"),
 "정릉동|1028": ("정릉e편한세상1차", 37.61519636, 127.01020281, 739, None, None, None, "나무위키"),
 "정릉동|1021": ("정릉대우", 37.61802225, 127.00342523, 791, 7, "2001-06-21", "개별난방", "K-APT(디아파트)"),
 "길음동|1280": ("길음뉴타운2단지푸르지오", 37.61178635, 127.01614616, 1634, None, "2005-04-20", "개별난방", "나무위키·K-APT(디아파트)"),
 "길음동|1281": ("길음뉴타운4단지e편한세상", 37.61269411, 127.01907299, 1605, None, None, None, "나무위키"),
 "길음동|1284": ("길음뉴타운8단지래미안", 37.6076631, 127.01840125, 1497, None, None, None, "나무위키"),
 "길음동|1288": ("래미안길음센터피스", 37.61162932, 127.02733945, 2352, 24, "2019-02-28", "개별난방", "K-APT(디아파트)"),
 "길음동|1278": ("길음동부센트레빌", 37.61052356, 127.02435813, 1377, None, None, None, "나무위키"),
 "종암동|80": ("종암삼성래미안(래미안크리시엘)", 37.60098614, 127.03015416, 1168, 17, "2004-09-24", "개별난방", "K-APT(디아파트)"),
 "종암동|104-1": ("종암SK", 37.60118225, 127.03753313, 1318, None, "1999-04-07", "중앙난방", "나무위키·K-APT(디아파트)"),
 "종암동|133": ("래미안세레니티", 37.5992452, 127.03105032, 955, 14, "2009-10-29", "개별난방", "K-APT(디아파트)"),
 "하월곡동|222": ("월곡두산위브", 37.60737728, 127.03807532, 2197, 30, "2003-04-30", "개별난방", "K-APT(디아파트)"),
 "하월곡동|225": ("래미안월곡", 37.61044103, 127.03687183, 1372, 26, "2006-07-19", "개별난방", "K-APT(디아파트)"),
 "하월곡동|228": ("월곡꿈의숲푸르지오", 37.61077191, 127.03899217, 714, 15, "2010-04-29", "개별난방", "K-APT(디아파트)"),
 "상월곡동|101": ("성북동아에코빌", 37.60774246, 127.04496579, 1253, None, None, None, "나무위키"),
 "하월곡동|226": ("월곡래미안루나밸리", 37.5990832, 127.04210242, 787, 11, "2007-10-23", "개별난방", "K-APT(디아파트)"),
 "장위동|323": ("꿈의숲아이파크", 37.61887549, 127.04846686, 1711, None, None, None, "나무위키·아파트지인"),
 "장위동|312": ("장위우방", 37.61022853, 127.05502898, 147, None, None, None, "아파트지인"),
 "장위동|320": ("래미안장위퍼스트하이", 37.61984283, 127.05135702, 1562, 16, "2019-09-27", "개별난방", "K-APT(디아파트)"),
 "장위동|322": ("래미안장위포레카운티", 37.61801141, 127.05274217, 939, 10, "2019-06-19", "개별난방", "K-APT(디아파트)"),
 "장위동|317": ("꿈의숲대명루첸", 37.62008854, 127.0476872, 611, 9, "2008-12-26", "개별난방", "K-APT(디아파트)"),
 "석관동|10": ("석관두산", 37.61269453, 127.0687783, 1998, 25, "1998-04-18", "개별난방", "K-APT(디아파트)"),
 "석관동|410": ("래미안아트리치", 37.60627685, 127.06385619, 1091, 14, "2019-02-28", "개별난방", "K-APT(디아파트)"),
 "석관동|405": ("석관코오롱", None, None, 453, 6, "1999-06-12", "개별난방", "K-APT(디아파트)"),
 "길음동|1289": ("롯데캐슬클라시아", 37.6085003, 127.026429, 2029, 19, "2022-01-31", "개별난방 / 도시가스", "롯데건설·공개 단지정보"),
}
FORCED = {"길음2동": "길음동|1289"}  # 사용자 지정 대표 단지
NOTES = {
 "장위3동": "장위자이레디언트(2,840세대)는 집계 기간 중 아파트 매매 신고가 없어 후보에서 제외",
}

def d8(s):
    return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))

apts = {}
for key, (name, lat, lon, hh, dc, appr, heat, src) in C.items():
    t = trades[key]
    dong_legal, jibun = key.split("|")
    admin = which(lat, lon) if lat else ("석관동" if dong_legal == "석관동" else None)
    rows = [r.split(",") for r in t["r"].split(";")]
    rec = [{"date": f"{r[0][:4]}-{r[0][4:6]}-{r[0][6:]}", "area": float(r[1]), "amount": int(r[2]), "floor": int(r[3])} for r in rows]
    areas = sorted(x["area"] for x in rec)
    build_year = int(t["nm"].split("/")[-1])
    apts[key] = {
        "name": name,
        "legal_dong": dong_legal,
        "admin_dong": admin,
        "dong": admin,
        "road_address": "서울특별시 성북구 " + t["rd"] if t["rd"].strip() else "",
        "jibun": jibun,
        "lat": lat, "lon": lon,
        "households": hh,
        "dong_count": dc,
        "approval_date": appr,
        "build_year": build_year,
        "heating": heat,
        "trade_count_12m": t["n"],
        "latest_trade_date": rec[0]["date"],
        "recent_trades": rec,
        "info_source": src,
        "_median_area": areas[len(areas) // 2],
    }

# 클라시아 기존 정보 보존
cl = apts["길음동|1289"]
cl.update({"kapt_code": "A10023926", "road_address": "서울특별시 성북구 숭인로8길 80",
           "floor_range": "지하 6층 ~ 지상 37층", "completion_month": "2022-01"})

dongs = {n: {"candidate_count": 0, "apartments": []} for n in ORDER}
for key, a in apts.items():
    assert a["admin_dong"] in dongs, (key, a["admin_dong"])
    dongs[a["admin_dong"]]["apartments"].append((key, a))

for dn, info in dongs.items():
    lst = [(k, a) for k, a in info["apartments"] if a["_median_area"] >= 40]
    if not lst:
        continue
    mh = max(a["households"] or 0 for _, a in lst) or 1
    mt = max(a["trade_count_12m"] for _, a in lst) or 1
    for k, a in lst:
        days = (AS_OF - datetime.date.fromisoformat(a["latest_trade_date"])).days
        rec = max(0.0, 1 - days / 365)
        s = 0.45 * (a["households"] or 0) / mh + 0.35 * a["trade_count_12m"] / mt + 0.20 * rec
        a["representative_score"] = round(s, 3)
    lst.sort(key=lambda x: -x[1]["representative_score"])
    if dn in FORCED:
        lst.sort(key=lambda x: 0 if x[0] == FORCED[dn] else 1)
    out = []
    for i, (k, a) in enumerate(lst[:3]):
        a = {kk: vv for kk, vv in a.items() if not kk.startswith("_")}
        hh = f"{a['households']:,}세대" if a["households"] else "세대수 미확인"
        reason = f"{hh} · 최근 1년 매매 {a['trade_count_12m']}건"
        if i == 0:
            reason = ("대표 단지(지정) · " if dn in FORCED else "대표 단지 · ") + reason
        if i == 0 and dn in NOTES:
            reason += " · " + NOTES[dn]
        a["representative_reason"] = reason
        a["data_as_of"] = "2026-10-06"
        out.append(a)
    info["apartments"] = out
    info["candidate_count"] = len(lst)

payload = {
    "gu": "성북구",
    "level": "행정동",
    "generated": AS_OF.isoformat(),
    "source_note": "실거래: 국토교통부 실거래가 공개시스템(매매, 계약일 2025.10.07~2026.10.06, 해제건 제외) · 단지정보: K-APT(디아파트 경유)·나무위키·아파트지인 · 행정동 배정: 단지 좌표 기준",
    "transaction_as_of": "2026-10-06",
    "ranking": {"households": 0.45, "trade_count_12m": 0.35, "recency": 0.20,
                "note": "행정동 내 최댓값 대비 정규화, 전용 40㎡ 미만 위주 단지 제외, 길음2동은 지정 단지"},
    "stats": {
        "apartment_count": sum(len(v["apartments"]) for v in dongs.values()),
        "trade_rows": sum(len(a["recent_trades"]) for v in dongs.values() for a in v["apartments"]),
    },
    "dongs": dongs,
}
json.dump(payload, open(os.path.join(ROOT, "data/seongbuk_detail.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(os.path.join(ROOT, "data/seongbuk_detail.js"), "w", encoding="utf-8").write(
    "// 성북구 행정동별 대표 단지·실거래 데이터 — scripts/build_seongbuk_detail.py 생성\nwindow.SEONGBUK_DETAIL = "
    + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n")
for dn, v in dongs.items():
    print(dn, " / ".join(f"{a['name']}({a.get('representative_score')},{a['trade_count_12m']})" for a in v["apartments"]))
