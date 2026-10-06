// 자치구 → 행정동 지도 → 대표 단지 → 실거래가 탐색 UI (서울 25개 구)
(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  // 서울 25개 자치구 행정동 경계: data/dong_geo/{시군구코드}.js 를 클릭 시점에 지연 로드한다.
  const GU_CODES = {
    "종로구":"11110","중구":"11140","용산구":"11170","성동구":"11200","광진구":"11215",
    "동대문구":"11230","중랑구":"11260","성북구":"11290","강북구":"11305","도봉구":"11320",
    "노원구":"11350","은평구":"11380","서대문구":"11410","마포구":"11440","양천구":"11470",
    "강서구":"11500","구로구":"11530","금천구":"11545","영등포구":"11560","동작구":"11590",
    "관악구":"11620","서초구":"11650","강남구":"11680","송파구":"11710","강동구":"11740",
  };
  // 행정동 단위 대표 단지 데이터가 있는 자치구. level 이 "행정동" 인 데이터만 지도와 연결한다.
  const DETAIL_SOURCES = {
    "성북구": () => window.SEONGBUK_DETAIL,
    "강동구": () => window.GANGDONG_DETAIL,
  };
  const SUPPORTED = new Set(Object.keys(GU_CODES));
  const NAME_PROP = "ADM_KOR_NM";
  const LEVEL = "행정동";
  let currentGu = null;
  let loadToken = 0;
  const geoPromises = {};
  const GEO = () => window.DONG_GEO?.[currentGu];
  const DATA = () => {
    const d = DETAIL_SOURCES[currentGu]?.();
    return d && d.level === LEVEL ? d : null;
  };

  function loadGeo(gu) {
    if (window.DONG_GEO?.[gu]) return Promise.resolve(window.DONG_GEO[gu]);
    if (!geoPromises[gu]) {
      geoPromises[gu] = new Promise((resolve, reject) => {
        const sc = document.createElement("script");
        sc.src = `data/dong_geo/${GU_CODES[gu]}.js`;
        sc.async = true;
        sc.onload = () => resolve(window.DONG_GEO?.[gu]);
        sc.onerror = () => { delete geoPromises[gu]; reject(new Error("geo load failed")); };
        document.head.appendChild(sc);
      });
    }
    return geoPromises[gu];
  }

  const style = document.createElement("style");
  style.textContent = `
    #district-explorer { display:none; }
    #district-explorer.open { display:block; }
    .de-head { display:flex; gap:12px; align-items:center; justify-content:space-between; margin-bottom:10px; }
    .de-breadcrumb { font-size:13px; color:var(--muted); }
    .de-breadcrumb b { color:var(--ink); font-size:15px; }
    .de-head-actions { display:flex; gap:6px; align-items:center; }
    .de-pill { padding:4px 9px; border-radius:999px; background:#f0efec; color:var(--ink-2); font-size:10.5px; font-weight:700; }
    .de-close { width:34px; height:34px; border:1px solid var(--border); border-radius:9px; background:var(--surface); font:inherit; font-size:19px; cursor:pointer; color:var(--muted); }
    .de-close:hover { color:var(--ink); background:#f2f1ec; }

    .de-grid { display:grid; grid-template-columns:minmax(0,1fr) minmax(330px,390px); gap:16px; align-items:start; }
    .de-map-wrap { min-width:0; }
    #dong-map { width:100%; height:auto; display:block; border-radius:12px; background:#f7f7f4; }
    .dong-shape { fill:#ebeae5; stroke:#fff; stroke-width:2; cursor:pointer; transition:fill .12s ease, filter .12s ease; }
    .dong-shape:hover, .dong-shape:focus-visible { fill:#dddcd5; outline:none; filter:brightness(.98); }
    .dong-shape.has-data { fill:#e3e9f1; }
    .dong-shape.has-data:hover, .dong-shape.has-data:focus-visible { fill:#d3dcea; }
    .dong-shape.selected { fill:#d6e5f8; stroke:#184f95; stroke-width:2.4; }
    .dong-label { pointer-events:none; text-anchor:middle; }
    .dong-label .name { font-size:var(--dong-label-size,13px); font-weight:800; fill:#0b0b0b; }
    .dong-label .apt { font-size:9.5px; font-weight:600; fill:#66645f; }
    .de-map-note { margin:6px 2px 0; font-size:10.8px; color:var(--muted); line-height:1.45; }

    .de-side { min-width:0; border-left:1px solid var(--hairline); padding-left:16px; }
    .de-empty { min-height:280px; display:flex; flex-direction:column; justify-content:center; color:var(--muted); font-size:12.5px; line-height:1.65; }
    .de-empty b { color:var(--ink-2); font-size:14px; margin-bottom:3px; }
    .de-dong-title { display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin-bottom:8px; }
    .de-dong-title h3 { margin:0; font-size:19px; letter-spacing:-.02em; }
    .de-dong-title span { color:var(--muted); font-size:10.5px; }
    .de-apt-list { display:flex; gap:6px; overflow-x:auto; padding:1px 0 8px; scrollbar-width:thin; }
    .de-apt-btn { flex:0 0 auto; max-width:210px; border:1px solid var(--border); background:var(--surface); border-radius:9px; padding:7px 9px; text-align:left; cursor:pointer; font:inherit; color:var(--ink-2); }
    .de-apt-btn b { display:block; font-size:11.5px; color:var(--ink); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .de-apt-btn span { display:block; font-size:9.5px; color:var(--muted); margin-top:2px; }
    .de-apt-btn.selected { border-color:#184f95; box-shadow:0 0 0 1px #184f95 inset; background:#f5f9ff; }

    .de-apt-name { font-size:18px; font-weight:850; letter-spacing:-.02em; margin:6px 0 2px; }
    .de-apt-sub { font-size:11px; color:var(--muted); line-height:1.5; margin-bottom:9px; }
    .de-kpis { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px; margin-bottom:10px; }
    .de-kpi { border:1px solid var(--hairline); border-radius:9px; padding:7px 8px; background:#fafaf8; }
    .de-kpi .k { font-size:9.5px; color:var(--muted); margin-bottom:2px; }
    .de-kpi .v { font-size:12.5px; color:var(--ink); font-weight:750; }
    .de-ranking { font-size:10px; color:var(--muted); margin:0 0 10px; }

    .de-section-title { display:flex; align-items:center; justify-content:space-between; gap:8px; margin:12px 0 6px; }
    .de-section-title b { font-size:12px; }
    .de-section-title span { font-size:9.5px; color:var(--muted); }
    .de-area-filter { display:flex; gap:4px; flex-wrap:wrap; margin-bottom:7px; }
    .de-area-filter button { border:1px solid var(--border); border-radius:999px; background:var(--surface); padding:4px 8px; font:inherit; font-size:10px; color:var(--ink-2); cursor:pointer; }
    .de-area-filter button[aria-pressed="true"] { background:var(--ink); color:#fff; border-color:var(--ink); }
    .de-trades { overflow:auto; max-height:260px; border-top:1px solid var(--hairline); }
    .de-trades table { width:100%; border-collapse:collapse; font-size:10.8px; white-space:nowrap; }
    .de-trades th { position:sticky; top:0; background:var(--surface); z-index:1; padding:6px 5px; text-align:right; color:var(--muted); font-size:9.5px; border-bottom:1px solid var(--hairline); }
    .de-trades th:first-child, .de-trades td:first-child { text-align:left; }
    .de-trades td { padding:6px 5px; text-align:right; border-bottom:1px solid #efeee9; color:var(--ink-2); }
    .de-trades td.price { font-weight:800; color:var(--up-strong); }
    .de-no-data { padding:16px 0; color:var(--muted); font-size:12px; line-height:1.6; }
    .de-source { margin-top:8px; padding-top:7px; border-top:1px solid var(--hairline); color:var(--muted); font-size:9.5px; line-height:1.45; }

    @media (max-width:1023px) {
      .de-grid { grid-template-columns:1fr; gap:10px; }
      .de-side { border-left:0; border-top:1px solid var(--hairline); padding:12px 0 0; }
      .de-empty { min-height:90px; }
    }
    @media (max-width:599px) {
      .de-head { margin-bottom:7px; }
      .de-breadcrumb { font-size:11px; }
      .de-breadcrumb b { font-size:14px; }
      .de-grid { gap:8px; }
      .de-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); }
      .de-trades { max-height:220px; }
    }
  `;
  document.head.appendChild(style);

  const mapCard = document.getElementById("map-layout")?.closest(".card");
  if (!mapCard) return;

  const explorer = document.createElement("section");
  explorer.id = "district-explorer";
  explorer.className = "card";
  explorer.innerHTML = `
    <div class="de-head">
      <div class="de-breadcrumb"><span>서울</span> <span>›</span> <b id="de-gu"></b></div>
      <div class="de-head-actions"><span class="de-pill" id="de-level">행정동</span><button class="de-close" type="button" aria-label="세부 지도 닫기">×</button></div>
    </div>
    <div class="de-grid">
      <div class="de-map-wrap">
        <svg id="dong-map" role="img" aria-label="자치구 행정동 지도"></svg>
        <p class="de-map-note" id="de-map-note">동을 선택하면 대표 단지와 최근 실거래가를 확인할 수 있습니다.</p>
      </div>
      <aside class="de-side" id="de-side" aria-live="polite"></aside>
    </div>
  `;
  mapCard.insertAdjacentElement("afterend", explorer);

  const closeBtn = explorer.querySelector(".de-close");
  const side = explorer.querySelector("#de-side");
  const svg = explorer.querySelector("#dong-map");
  let selectedDong = null;
  let selectedApartment = null;

  closeBtn.addEventListener("click", () => close());

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));
  }

  function formatPrice(manwon) {
    const n = Number(manwon);
    if (!Number.isFinite(n)) return "–";
    const eok = Math.floor(n / 10000);
    const rest = Math.round(n % 10000);
    if (!eok) return rest.toLocaleString("ko-KR") + "만";
    return eok + "억" + (rest ? " " + rest.toLocaleString("ko-KR") + "만" : "");
  }

  function formatDate(s) {
    return s ? String(s).replaceAll("-", ".") : "–";
  }

  function shortName(s, n=12) {
    s = String(s || "");
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  function centroid(ring) {
    let x = 0, y = 0, a = 0;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const p = ring[j], q = ring[i];
      const f = p[0] * q[1] - q[0] * p[1];
      x += (p[0] + q[0]) * f;
      y += (p[1] + q[1]) * f;
      a += f;
    }
    if (Math.abs(a) < 1e-12) {
      const sx = ring.reduce((t,p)=>t+p[0],0)/ring.length;
      const sy = ring.reduce((t,p)=>t+p[1],0)/ring.length;
      return [sx,sy];
    }
    a *= 0.5;
    return [x/(6*a), y/(6*a)];
  }

  function polygons(geom) {
    if (!geom) return [];
    if (geom.type === "Polygon") return [geom.coordinates];
    if (geom.type === "MultiPolygon") return geom.coordinates;
    return [];
  }

  function ringArea(ring) {
    let a = 0;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) a += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
    return Math.abs(a / 2);
  }

  function drawDongMap(message) {
    const geo = GEO();
    if (!geo?.features?.length) {
      svg.setAttribute("viewBox", "0 0 800 420");
      svg.innerHTML = `<text x="400" y="210" text-anchor="middle" fill="#898781" font-size="16">${esc(message || "행정동 경계 데이터 없음")}</text>`;
      return;
    }

    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    geo.features.forEach(f => polygons(f.geometry).forEach(poly => poly.forEach(ring => ring.forEach(([x,y]) => {
      minX=Math.min(minX,x); maxX=Math.max(maxX,x); minY=Math.min(minY,y); maxY=Math.max(maxY,y);
    }))));
    const mid=(minY+maxY)/2, cos=Math.cos(mid*Math.PI/180);
    const W=820, PAD=24;
    const k=(W-PAD*2)/((maxX-minX)*cos);
    const H=Math.ceil((maxY-minY)*k+PAD*2);
    const px=x=>PAD+(x-minX)*cos*k;
    const py=y=>PAD+(maxY-y)*k;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML="";
    // 동 개수가 많은 구(송파 27개 등)는 라벨을 조금 줄인다.
    const n = geo.features.length;
    svg.style.setProperty("--dong-label-size", n > 22 ? "11px" : n > 17 ? "12px" : "13px");

    const data = DATA()?.dongs || {};
    const labels = [];
    geo.features.forEach(f => {
      const name=f.properties[NAME_PROP];
      const polys=polygons(f.geometry);
      const d=polys.map(poly => poly.map(ring => "M"+ring.map(([x,y])=>`${px(x).toFixed(1)},${py(y).toFixed(1)}`).join("L")+"Z").join("")).join("");
      const info=data[name]||{};
      const apt=(info.apartments||[])[0]?.name || "";
      const path=document.createElementNS(NS,"path");
      path.setAttribute("d",d);
      path.setAttribute("fill-rule","evenodd");
      path.setAttribute("class","dong-shape"+(apt?" has-data":"")+(selectedDong===name?" selected":""));
      path.setAttribute("tabindex","0");
      path.setAttribute("role","button");
      path.setAttribute("aria-label", name+(apt?" 대표 단지 "+apt:"")+" 보기");
      path.dataset.dong=name;
      path.addEventListener("click",()=>selectDong(name));
      path.addEventListener("keydown",e=>{ if(e.key==="Enter"||e.key===" "){e.preventDefault();selectDong(name);} });
      svg.appendChild(path);

      // 라벨은 가장 큰 외곽 링의 무게중심에 둔다 (다중 폴리곤 대응).
      let best=null, bestA=-1;
      polys.forEach(poly => { const ar=ringArea(poly[0]); if (ar>bestA) { bestA=ar; best=poly[0]; } });
      const [cx,cy]=centroid(best);
      // 폴리곤 폭이 좁으면 단지명 보조 라벨을 생략해 겹침을 줄인다 (선택 시 우측 패널에서 확인).
      const xs=best.map(p=>px(p[0])), wPx=Math.max(...xs)-Math.min(...xs);
      const aptLabel=shortName(apt,9);
      const showApt=apt && wPx >= aptLabel.length*9.6+6;
      const g=document.createElementNS(NS,"g");
      g.setAttribute("class","dong-label");
      g.setAttribute("transform",`translate(${px(cx).toFixed(1)},${py(cy).toFixed(1)})`);
      g.innerHTML=`<text class="name" x="0" y="${showApt?-2:4}">${esc(name.replace(/동$/,""))}</text>`+
        (showApt?`<text class="apt" x="0" y="13">${esc(aptLabel)}</text>`:"");
      labels.push(g);
    });
    labels.forEach(g => svg.appendChild(g));
  }

  function selectDong(name) {
    selectedDong=name;
    const info=DATA()?.dongs?.[name] || {apartments:[]};
    selectedApartment=(info.apartments||[])[0] || null;
    drawDongMap();
    renderSide();
  }

  function renderSide() {
    if (!selectedDong) {
      const hasData = (DATA()?.stats?.trade_rows || 0) > 0;
      side.innerHTML = `<div class="de-empty"><b>${LEVEL}을 선택하세요</b>${
        hasData
          ? "지도에서 행정동을 누르면 대표 단지와 최근 매매 실거래가를 확인할 수 있습니다. 색이 칠해진 동에 대표 단지 데이터가 있습니다."
          : `${esc(currentGu || "")}는 행정동 경계 지도만 먼저 제공합니다. 대표 단지·실거래가 데이터는 순차적으로 추가됩니다.`
      }</div>`;
      return;
    }

    const info=DATA()?.dongs?.[selectedDong] || {apartments:[]};
    const apts=info.apartments||[];
    if (!apts.length) {
      side.innerHTML=`<div class="de-dong-title"><h3>${esc(selectedDong)}</h3><span>${LEVEL}</span></div>
        <div class="de-no-data">이 동의 대표 단지 데이터가 아직 등록되지 않았습니다.</div>`;
      return;
    }
    if (!selectedApartment || !apts.some(a => aptKey(a)===aptKey(selectedApartment))) selectedApartment=apts[0];

    side.innerHTML=`<div class="de-dong-title"><h3>${esc(selectedDong)}</h3><span>${LEVEL} · 후보 ${Number(info.candidate_count||0).toLocaleString("ko-KR")}곳</span></div>
      <div class="de-apt-list">${apts.map((a,i)=>`
        <button type="button" class="de-apt-btn ${aptKey(a)===aptKey(selectedApartment)?"selected":""}" data-apt="${esc(aptKey(a))}">
          <b>${i===0?"★ ":""}${esc(a.name)}</b>
          <span>12개월 ${a.trade_count_12m||0}건${a.households?" · "+Number(a.households).toLocaleString("ko-KR")+"세대":""}</span>
        </button>`).join("")}</div>
      <div id="de-apt-detail"></div>`;

    side.querySelectorAll(".de-apt-btn").forEach(btn => btn.addEventListener("click",()=>{
      selectedApartment=apts.find(a=>aptKey(a)===btn.dataset.apt) || apts[0];
      renderSide();
    }));
    renderApartment(side.querySelector("#de-apt-detail"), selectedApartment);
  }

  function aptKey(a) {
    return String(a?.apt_seq || a?.kapt_code || a?.name || "");
  }

  function renderApartment(el, apt) {
    const trades=Array.isArray(apt.recent_trades)?apt.recent_trades:[];
    const areaGroups=[...new Set(trades.map(t=>Math.round(Number(t.area)||0)).filter(Boolean))].sort((a,b)=>a-b);
    el.innerHTML=`
      <div class="de-apt-name">${esc(apt.name)}</div>
      <div class="de-apt-sub">${esc(apt.road_address || apt.address || "")}${apt.legal_dong ? "<br>"+esc("지번 "+apt.legal_dong+" "+(apt.jibun||"")+" · 행정동 "+(apt.admin_dong||apt.dong||"")) : ""}</div>
      <div class="de-kpis">
        <div class="de-kpi"><div class="k">세대수</div><div class="v">${apt.households?Number(apt.households).toLocaleString("ko-KR")+"세대":"–"}</div></div>
        <div class="de-kpi"><div class="k">동</div><div class="v">${apt.dong_count?apt.dong_count+"개동":"–"}</div></div>
        ${apt.floor_range
          ? `<div class="de-kpi"><div class="k">층</div><div class="v">${esc(apt.floor_range)}</div></div>`
          : `<div class="de-kpi"><div class="k">최근 1년 매매</div><div class="v">${Number(apt.trade_count_12m||0).toLocaleString("ko-KR")}건</div></div>`}
        <div class="de-kpi"><div class="k">준공년월</div><div class="v">${esc(apt.completion_month ? apt.completion_month.replace("-", ".") : (apt.approval_date ? formatDate(apt.approval_date).slice(0,7) : (apt.build_year ? apt.build_year+"년" : "–")))}</div></div>
        <div class="de-kpi"><div class="k">사용승인</div><div class="v">${esc(apt.approval_date ? formatDate(apt.approval_date) : "–")}</div></div>
        <div class="de-kpi"><div class="k">난방</div><div class="v">${esc(apt.heating || "–")}</div></div>
      </div>
      <p class="de-ranking">${esc(apt.representative_reason || ("대표성 점수 "+Math.round((apt.representative_score||0)*100)+" · 최근 12개월 거래 "+(apt.trade_count_12m||0)+"건"))} · 최근 거래 ${esc(formatDate(apt.latest_trade_date))}</p>
      <div class="de-section-title"><b>평형별 최근 실거래가</b><span>매매 신고 실거래</span></div>
      <div class="de-area-filter">
        <button type="button" data-area="all" aria-pressed="true">전체</button>
        ${areaGroups.slice(0,8).map(x=>`<button type="button" data-area="${x}" aria-pressed="false">전용 약 ${x}㎡</button>`).join("")}
      </div>
      <div class="de-trades"></div>
      <div class="de-source">${apt.info_source ? "단지정보 출처: "+esc(apt.info_source)+"<br>" : ""}${esc(DATA()?.source_note || "")}${DATA()?.transaction_as_of ? " · 거래 데이터 "+esc(DATA().transaction_as_of)+" 기준" : ""}</div>`;

    const tradesBox=el.querySelector(".de-trades");
    function renderTrades(area) {
      const rows=area==="all"?trades:trades.filter(t=>Math.round(Number(t.area)||0)===Number(area));
      tradesBox.innerHTML=rows.length?`<table><thead><tr><th>계약일</th><th>전용</th><th>가격</th><th>층</th></tr></thead><tbody>
        ${rows.slice(0,20).map(t=>`<tr><td>${esc(formatDate(t.date))}</td><td>${Number(t.area).toFixed(1)}㎡</td><td class="price">${formatPrice(t.amount)}</td><td>${t.floor??"–"}</td></tr>`).join("")}
        </tbody></table>`:'<div class="de-no-data">선택 면적의 최근 거래가 없습니다.</div>';
    }
    renderTrades("all");
    el.querySelectorAll(".de-area-filter button").forEach(btn=>btn.addEventListener("click",()=>{
      el.querySelectorAll(".de-area-filter button").forEach(x=>x.setAttribute("aria-pressed",String(x===btn)));
      renderTrades(btn.dataset.area);
    }));
  }

  function openDistrict(gu) {
    if (!SUPPORTED.has(gu)) {
      close(false);
      return false;
    }
    currentGu=gu;
    const token=++loadToken;
    const hasData=!!DATA();
    explorer.classList.add("open");
    explorer.querySelector("#de-gu").textContent=gu;
    explorer.querySelector("#de-level").textContent=LEVEL+(hasData?" · 대표 단지":" 지도");
    explorer.querySelector("#dong-map").setAttribute("aria-label", gu+" "+LEVEL+" 지도");
    explorer.querySelector("#de-map-note").textContent= hasData
      ? LEVEL+"을 선택하면 대표 단지와 최근 매매 실거래가를 확인할 수 있습니다."
      : gu+" "+LEVEL+" 경계 지도입니다. 대표 단지 데이터는 순차적으로 추가됩니다.";
    selectedDong=null;
    selectedApartment=null;
    renderSide();
    if (GEO()) {
      drawDongMap();
    } else {
      drawDongMap("행정동 경계 불러오는 중…");
      loadGeo(gu).then(() => {
        if (token===loadToken && currentGu===gu) drawDongMap();
      }).catch(() => {
        if (token===loadToken) drawDongMap("행정동 경계를 불러오지 못했습니다");
      });
    }
    return true;
  }

  function close(scroll=false) {
    explorer.classList.remove("open");
    selectedDong=null;
    selectedApartment=null;
    if (scroll && mapCard) mapCard.scrollIntoView({behavior:"smooth",block:"start"});
  }

  window.AptDetail = { openDistrict, close };
})();
