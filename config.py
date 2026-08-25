# -*- coding: utf-8 -*-
"""볼린저밴드 알림봇 설정값. 여기만 고치면 전체가 따라갑니다."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------- 비밀값 로딩
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key and val and not os.environ.get(key):
            os.environ[key] = val


_load_env_file(BASE_DIR / "secrets.env")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

REQUEST_TIMEOUT = 20

# ---------------------------------------------------------------- 감시 대상
INCLUDE_KOSPI200 = True
INCLUDE_SP500 = True
# 코인은 별도 개수 제한 없이 바이낸스 USDT 무기한선물 전체를 감시합니다.

UNIVERSE_CACHE_DAYS = 7           # 종목 리스트 캐시 유지 기간(일) — 지수 구성종목은 자주 안 바뀜

# ---------------------------------------------------------------- 볼린저밴드
BB_TIMEFRAME = "1W"               # 주봉
# 상단/하단 값 자체는 트레이딩뷰 스캐너가 이미 계산해서 줍니다(BB.upper|1W 등).
# 아래는 참고용 — 트레이딩뷰 기본값과 동일(20주 이평 ± 2표준편차).
BB_PERIOD = 20
BB_STD = 2
# 구간별·종류별 "근접" 판정 임계값(±%). 코인이 주식보다 변동성이 커서 항상 더
# 넓게 잡는다. 중단(기준선)은 상단/하단보다 좁게 잡는다 — 기준선은 주가가 항상
# 그 근처를 오가므로 넓게 두면 거의 모든 종목이 걸린다.
PROXIMITY_PCT = {
    "upper": {"stock": 1.0, "coin": 5.0},
    "mid":   {"stock": 0.5, "coin": 2.0},
    "lower": {"stock": 1.0, "coin": 5.0},
}

# 체크 주기(약 5분) 사이 가격이 이 % 이상 움직이면 급등/급락 알림. 코인·주식 공통.
SURGE_PCT = 10.0

# 최근 3일(거래일 기준 날짜 라벨 3일 전 대비) 등락률 배지 임계값.
# 이만큼 오르면 대시보드에 🔥, 이만큼(이하로) 내리면 🧊를 붙인다.
PCT_3D_FIRE = 10.0
PCT_3D_ICE = -5.0

# ---------------------------------------------------------------- 요청
TV_CHUNK_SIZE = 50                # 스캐너 요청 1번에 넣을 티커 수
TV_REQUEST_DELAY = 0.3            # 요청 사이 대기(초)
