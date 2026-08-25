# -*- coding: utf-8 -*-
"""트레이딩뷰 스캐너 API(비공식) 래퍼.

공식 문서가 없는 내부 엔드포인트입니다. 트레이딩뷰 웹사이트 자체가 차트/스크리너에
쓰는 트래픽이라 개별 브로커 스크래핑보다는 덜 튀지만, 예고 없이 막힐 수 있습니다.
개인 리서치 목적으로만 쓰세요.
"""
from __future__ import annotations

import time

import requests

import config as C

SCAN_URL = "https://scanner.tradingview.com/{market}/scan"
SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/v3/"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

COLUMNS = ["close", f"BB.upper|{C.BB_TIMEFRAME}", f"BB.lower|{C.BB_TIMEFRAME}",
          f"BB.basis|{C.BB_TIMEFRAME}", "market_cap_basic", "high|5", "low|5"]


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def fetch_bb(tickers: list[str], market: str) -> dict[str, dict]:
    """티커 목록(예: ["KRX:005930", ...])의 주봉 볼린저밴드를 받아온다.

    market: "korea" | "america" | "crypto" (스캐너 엔드포인트 경로)
    반환: {ticker: {"close":.., "upper":.., "lower":.., "basis":.., "high5":.., "low5":..}}
    high5/low5는 직전 5분봉의 고가/저가 — 두 체크 사이(약 5분) 순간적으로
    급등락했다가 되돌아온 경우도 잡기 위한 것(급등락 판정은 close 하나만 보면
    놓친다). 실패한 티커는 결과에서 빠진다(호출자가 이전 값을 유지하면 됨).
    """
    out: dict[str, dict] = {}
    for chunk in _chunks(tickers, C.TV_CHUNK_SIZE):
        body = {"symbols": {"tickers": chunk, "query": {"types": []}}, "columns": COLUMNS}
        try:
            r = _SESSION.post(SCAN_URL.format(market=market), json=body,
                              timeout=C.REQUEST_TIMEOUT)
            r.raise_for_status()
            for row in r.json().get("data", []):
                close, upper, lower, basis, mcap, high5, low5 = row["d"]
                if close is None or upper is None or lower is None:
                    continue
                out[row["s"]] = {"close": float(close), "upper": float(upper),
                                 "lower": float(lower), "basis": float(basis),
                                 "mcap": float(mcap) if mcap is not None else None,
                                 "high5": float(high5) if high5 is not None else None,
                                 "low5": float(low5) if low5 is not None else None}
        except Exception as e:                            # noqa: BLE001
            print(f"  ! 스캐너 요청 실패({market}, {len(chunk)}개): {e}")
        time.sleep(C.TV_REQUEST_DELAY)
    return out


def resolve_exchange(ticker: str) -> str | None:
    """미국 주식 심볼(예: "AAPL")의 거래소 접두어를 찾아 "NASDAQ:AAPL" 형태로 반환.

    symbol-search는 Referer/Origin 헤더가 없으면 403을 돌려준다.
    """
    try:
        r = _SESSION.get(SEARCH_URL, params={
            "text": ticker, "hl": 1, "exchange": "", "lang": "en",
            "search_type": "stocks", "domain": "production",
        }, headers={"Referer": "https://www.tradingview.com/",
                    "Origin": "https://www.tradingview.com"},
                          timeout=C.REQUEST_TIMEOUT)
        r.raise_for_status()
        for s in r.json().get("symbols", []):
            sym = s.get("symbol", "").replace("<em>", "").replace("</em>", "")
            if sym.upper() == ticker.upper() and s.get("is_primary_listing"):
                return f"{s['exchange']}:{sym}"
        # 기본상장 표시가 없으면 첫 완전일치를 그대로 쓴다
        for s in r.json().get("symbols", []):
            sym = s.get("symbol", "").replace("<em>", "").replace("</em>", "")
            if sym.upper() == ticker.upper():
                return f"{s['exchange']}:{sym}"
    except Exception as e:                                # noqa: BLE001
        print(f"  ! {ticker} 거래소 확인 실패: {e}")
    return None
