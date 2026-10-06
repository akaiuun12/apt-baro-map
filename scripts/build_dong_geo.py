"""서울 25개 자치구 행정동 경계 → data/dong_geo/{시군구코드}.js

사용법 (mapshaper 필요: npm i -g mapshaper):
  curl -L -o /tmp/adm.geojson https://raw.githubusercontent.com/vuski/admdongkor/master/ver20260701/HangJeongDong_ver20260701.geojson
  mapshaper /tmp/adm.geojson -filter "sidonm=='서울특별시'" -simplify 35% keep-shapes -clean \
      -o /tmp/seoul_adm.json format=geojson precision=0.00001
  python scripts/build_dong_geo.py /tmp/seoul_adm.json

행정동 개편이 있으면 vuski/admdongkor 의 최신 버전으로 VERSION 을 바꿔 다시 실행한다.
"""
import json, os, sys

VERSION = "ver20260701"
src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/seoul_adm.json"
out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "dong_geo")
os.makedirs(out_dir, exist_ok=True)

d = json.load(open(src, encoding="utf-8"))
by = {}
for f in d["features"]:
    p = f["properties"]
    by.setdefault((p["sgg"], p["sggnm"]), []).append({
        "type": "Feature",
        "properties": {"ADM_KOR_NM": p["adm_nm"].split()[-1], "ADM_FULL_NM": p["adm_nm"], "ADM_CD2": p["adm_cd2"]},
        "geometry": f["geometry"],
    })
for (code, nm), fs in sorted(by.items()):
    fs.sort(key=lambda f: f["properties"]["ADM_CD2"])
    fc = {"type": "FeatureCollection", "gu": nm, "sgg": code, "level": "행정동",
          "source": f"vuski/admdongkor {VERSION} (행정동 경계) · mapshaper 35% 단순화", "features": fs}
    body = json.dumps(fc, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, f"{code}.js"), "w", encoding="utf-8") as fp:
        fp.write(f"// {nm} 행정동 경계 (WGS84) — vuski/admdongkor {VERSION}, mapshaper 35% 단순화\n"
                 f"window.DONG_GEO = window.DONG_GEO || {{}};\nwindow.DONG_GEO[{json.dumps(nm, ensure_ascii=False)}] = {body};\n")
    print(code, nm, len(fs))
