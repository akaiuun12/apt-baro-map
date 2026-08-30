/**
 * Google Analytics 4 로더 — 5개 사이트 공통 규격.
 *
 * 규칙
 *  - 측정 ID(window.GA_MEASUREMENT_ID)가 없거나 형식이 틀리면 GA를 아예 불러오지 않습니다.
 *  - file: / localhost 접속은 집계에서 제외합니다 (로컬 확인이 통계를 오염시키지 않도록).
 *  - 이벤트는 window.gaEvent(name, params), SPA 페이지 전환은 window.gaPageView(path).
 *    GA가 꺼져 있어도 두 함수는 항상 존재하므로 호출부에 분기가 필요 없습니다.
 *
 * 이 파일은 사이트마다 같은 내용을 유지합니다. 고칠 일이 생기면 5개 리포에 함께 반영하세요.
 */
(function () {
  "use strict";

  var id = window.GA_MEASUREMENT_ID;
  var enabled =
    /^G-[A-Z0-9]{6,}$/.test(id || "") &&
    location.protocol !== "file:" &&
    !/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);

  window.gaEvent = function (name, params) {
    if (window.gtag) window.gtag("event", name, params || {});
  };

  window.gaPageView = function (path) {
    if (!window.gtag) return;
    window.gtag("event", "page_view", {
      page_path: path || location.pathname + location.search,
      page_location: location.href,
      page_title: document.title,
    });
  };

  if (!enabled) return;

  window.dataLayer = window.dataLayer || [];
  window.gtag = function () {
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", id);

  var s = document.createElement("script");
  s.async = true;
  s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id);
  document.head.appendChild(s);
})();
