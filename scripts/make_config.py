# -*- coding: utf-8 -*-
"""`.env` 의 값을 읽어 브라우저가 읽는 `config.js` 를 생성한다.

config.js 를 직접 편집해도 되지만, 설정을 .env 한 곳에 모아두고 싶을 때 사용한다.

    # .env
    GA_MEASUREMENT_ID=G-XXXXXXXXXX

    python scripts/make_config.py

주의: 생성된 config.js 는 GitHub Pages 로 서빙되어야 하므로 커밋 대상이다.
GA4 측정 ID 는 브라우저에 노출되는 공개 식별자라 비밀값이 아니다.
API 인증키(RONE_API_KEY)는 서버 사이드 전용이라 config.js 에 절대 쓰지 않는다.
"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # Windows cp949 콘솔 대비
    sys.stdout.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
CONFIG_PATH = ROOT / "config.js"

TEMPLATE = '''// 사이트 설정 - scripts/make_config.py 가 .env 를 읽어 생성했습니다.
// 직접 편집해도 되지만, 다시 생성하면 덮어씁니다.
//
// GA4 측정 ID: Google Analytics > 관리 > 데이터 스트림에서 확인 (G- 로 시작)
// 비워두면 Google Analytics 를 아예 불러오지 않습니다.
//
// 참고: 측정 ID 는 브라우저에 그대로 노출되는 공개 식별자라 비밀값이 아닙니다.
// GitHub Pages 로 서빙되려면 이 파일이 리포지토리에 포함되어야 하므로 커밋 대상입니다.
window.GA_MEASUREMENT_ID = "{ga_id}";
'''


def read_env():
    if not ENV_PATH.exists():
        return {}
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    env = read_env()
    ga_id = env.get("GA_MEASUREMENT_ID", "")

    if ga_id and not re.fullmatch(r"G-[A-Z0-9]{6,}", ga_id):
        sys.exit(
            f"[오류] GA_MEASUREMENT_ID 형식이 올바르지 않습니다: {ga_id!r}\n"
            "  G- 로 시작하는 GA4 측정 ID 여야 합니다 (예: G-ABC123DEF4).\n"
            "  UA- 로 시작하는 구 유니버설 애널리틱스 ID 는 지원되지 않습니다."
        )

    CONFIG_PATH.write_text(TEMPLATE.format(ga_id=ga_id), encoding="utf-8")

    if ga_id:
        print(f"[완료] config.js 생성 - GA 활성화 ({ga_id})")
        print("  커밋 후 푸시하면 배포 사이트에 반영됩니다:")
        print('  git add config.js && git commit -m "GA 측정 ID 설정" && git push')
    else:
        print("[완료] config.js 생성 - GA 비활성 (.env 에 GA_MEASUREMENT_ID 가 없음)")
        print("  .env 에 GA_MEASUREMENT_ID=G-XXXXXXXXXX 를 추가한 뒤 다시 실행하세요.")


if __name__ == "__main__":
    main()
