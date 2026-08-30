# -*- coding: utf-8 -*-
"""daily_close_history.json 1회성 백필 스크립트.

check_bb.py는 매 실행마다 오늘 종가를 스스로 기록하는 방식이라, 새로 배포하면
3일치가 쌓일 때까지 🔥/🧊 배지가 안 뜬다. 이 스크립트는 무료 공개 소스에서
최근 며칠치 일봉 종가를 직접 받아와 그 대기 시간을 없앤다.

    python backfill_history.py

이후 정상 운영(매 실행마다 오늘 자리 갱신)은 check_bb.py가 그대로 담당한다.

소스:
- 코인(바이낸스 무기한선물): 바이낸스 선물 공식 API 일봉 — UTC 자정 기준 캔들이라
  KST 09:00 경계인 trading_day_label과 정확히 일치한다(UTC 00:00 = KST 09:00).
- 코스피200: 네이버 금융 시세 API(비공식, 이미 다른 곳에서도 쓰는 소스).
- S&P500: Yahoo Finance 차트 API(비공식이지만 널리 쓰이는 무료 엔드포인트).
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import requests

import config as C
from state_io import write_json

KST = timezone(timedelta(hours=9))
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

HISTORY_PATH = C.DATA_DIR / "daily_close_history.json"
UNIVERSE_PATH = C.DATA_DIR / "universe.json"
DAYS_BACK = 8  # check_bb.py의 보관 기간(8일)과 맞춤 — 3일 비교 + 주말 공백 여유


def fetch_coin(ticker: str) -> dict[str, float]:
    """BINANCE:BTCUSDT.P → BTCUSDT. 바이낸스 일봉은 UTC 자정 기준이라 그 날짜가
    곧 KST 09:00~다음날 09:00 거래일 라벨과 그대로 같다."""
    symbol = ticker.split(":", 1)[1]
    if symbol.endswith(".P"):
        symbol = symbol[:-2]
    try:
        r = _SESSION.get("https://fapi.binance.com/fapi/v1/klines",
                         params={"symbol": symbol, "interval": "1d", "limit": DAYS_BACK},
                         timeout=10)
        r.raise_for_status()
        out = {}
        for k in r.json():
            date_label = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).date().isoformat()
            out[date_label] = float(k[4])
        return out
    except Exception:                                       # noqa: BLE001
        return {}


def fetch_kr(ticker: str) -> dict[str, float]:
    """KRX:005930 → 005930. 네이버 금융 일별 시세(비공식)."""
    code = ticker.split(":", 1)[1]
    end = datetime.now(KST).date()
    start = end - timedelta(days=DAYS_BACK * 2)  # 주말 감안 넉넉히 잡고 응답에서 최근 것만 씀
    try:
        r = _SESSION.get("https://api.finance.naver.com/siseJson.naver",
                         params={"symbol": code, "requestType": 1,
                                 "startTime": start.strftime("%Y%m%d"),
                                 "endTime": end.strftime("%Y%m%d"), "timeframe": "day"},
                         timeout=10)
        r.raise_for_status()
        rows = re.findall(r'\["(\d{8})",\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*([\d.]+)', r.text)
        out = {}
        for date_str, close in rows:
            date_label = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            out[date_label] = float(close)
        return out
    except Exception:                                       # noqa: BLE001
        return {}


def fetch_us(ticker: str) -> dict[str, float]:
    """NASDAQ:AAPL → AAPL. Yahoo Finance 차트 API(비공식)."""
    symbol = ticker.split(":", 1)[1]
    try:
        r = _SESSION.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                         params={"range": "15d", "interval": "1d"}, timeout=10)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
        out = {}
        for t, c in zip(ts, closes):
            if c is None:
                continue
            date_label = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(KST).date().isoformat()
            out[date_label] = float(c)
        return out
    except Exception:                                       # noqa: BLE001
        return {}


def main() -> None:
    # 1회성 수동 스크립트라 상태 파일이 없거나 깨진 경우 조용히 넘어가지 않고
    # 바로 실패한다 — 전제(universe 캐시가 미리 만들어져 있어야 함)가 안 맞으면
    # 사람이 그 자리에서 알아채야 한다(check_bb.py의 상시 자동 실행과는 다른 요구).
    if not UNIVERSE_PATH.exists():
        raise FileNotFoundError(f"{UNIVERSE_PATH} 없음 — 먼저 check_bb.py를 한 번 실행해 종목 캐시를 만드세요.")
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))["items"]
    fetchers = {"kospi200": fetch_kr, "sp500": fetch_us, "coin": fetch_coin}

    history: dict[str, dict[str, float]] = {}
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))

    def work(item):
        fn = fetchers[item["group"]]
        return item["ticker"], fn(item["ticker"])

    done = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(work, it) for it in universe]
        for fut in as_completed(futures):
            ticker, days = fut.result()
            if days:
                history.setdefault(ticker, {}).update(days)
            else:
                failed += 1
            done += 1
            if done % 100 == 0:
                print(f"{done}/{len(universe)}… (실패 {failed})", flush=True)

    write_json(HISTORY_PATH, history, sort_keys=True)
    print(f"완료: {len(history)}개 티커 히스토리 저장 (조회 실패 {failed}건)")


if __name__ == "__main__":
    main()
