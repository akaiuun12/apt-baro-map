/**
 * 사이트 설정 — 이 리포에서 GA4 측정 ID를 관리하는 유일한 파일입니다.
 *
 * 측정 ID는 Google Analytics > 관리 > 데이터 스트림에서 확인합니다 (G- 로 시작).
 * 사이트마다 별도의 GA4 속성을 쓰므로 다른 리포의 ID를 그대로 넣지 마세요.
 * 비워두면 GA를 아예 불러오지 않습니다.
 *
 * 측정 ID는 모든 방문자의 브라우저에 노출되는 공개 식별자라 비밀값이 아니며,
 * 정적 파일로 그대로 서빙돼야 하므로 커밋 대상입니다.
 */
window.GA_MEASUREMENT_ID = "G-JG6V34C6BE"; // 예: "G-XXXXXXXXXX"

/**
 * 최신 주차와 사이트 갱신 시각을 헤더/푸터에 명확히 표시한다.
 * data/latest.js 의 weeks 값은 해당 주의 월요일 기준일이며, weekIds 는 YYYYWW 형식이다.
 * GitHub Actions(ubuntu-latest)에서 생성된 timezone 없는 generated 값은 UTC로 기록되므로
 * 화면에서는 KST로 변환해 보여준다.
 */
window.addEventListener("DOMContentLoaded", () => {
  const D = window.APT_DATA;
  if (!D || !Array.isArray(D.weeks) || !D.weeks.length) return;
  const n = D.weeks.length;
  const weekStart = D.weeks[n - 1];
  const weekId = Array.isArray(D.weekIds) ? String(D.weekIds[n - 1] || "") : "";

  const startDate = new Date(`${weekStart}T00:00:00Z`);
  const endDate = new Date(startDate);
  endDate.setUTCDate(endDate.getUTCDate() + 6);
  const weekEnd = Number.isNaN(endDate.getTime())
    ? "–"
    : endDate.toISOString().slice(0, 10);

  const weekYear = /^\d{6}$/.test(weekId) ? weekId.slice(0, 4) : weekStart.slice(0, 4);
  const weekNo = /^\d{6}$/.test(weekId) ? String(parseInt(weekId.slice(4), 10)) : "";
  const weekLabel = weekNo ? `${weekYear}년 ${weekNo}주차` : `${weekStart} 주`;

  function generatedKst(raw) {
    if (!raw) return "–";
    // 이미 시간대가 붙은 값은 그대로 사용한다.
    if (/(?:\bKST\b|\bUTC\b|Z|[+-]\d{2}:?\d{2})$/i.test(raw)) return raw;

    // 현재 자동 갱신은 GitHub Actions UTC 환경에서 timezone 없이 저장한다.
    const dt = new Date(raw.replace(" ", "T") + ":00Z");
    if (Number.isNaN(dt.getTime())) return raw;

    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Seoul",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).formatToParts(dt).map(p => [p.type, p.value])
    );
    return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} KST`;
  }

  const updated = generatedKst(D.generated);
  const subtitle = document.getElementById("subtitle");
  if (subtitle) {
    subtitle.innerHTML =
      `<b>주차</b> ${weekLabel} · <b>주차구간</b> ${weekStart} ~ ${weekEnd} · <b>사이트 갱신</b> ${updated}` +
      `<br><b>출처</b> ${D.source}`;
  }

  const footer = document.getElementById("footer");
  if (footer) {
    footer.textContent = "한국부동산원 R-ONE · 청약홈 · 매매가격 변동률은 전주 대비 기준";
  }
});
