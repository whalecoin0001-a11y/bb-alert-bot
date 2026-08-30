# -*- coding: utf-8 -*-
"""감시 종목 리스트 구성: 코스피200 + S&P500 + 코인 상위 거래대금.

지수 구성종목은 자주 안 바뀌므로 data/universe.json에 캐시하고
config.UNIVERSE_CACHE_DAYS 이내면 재사용한다.
"""
from __future__ import annotations

import io
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

import config as C
import tv_scanner as TV
from state_io import read_json, write_json

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

CACHE_PATH = C.DATA_DIR / "universe.json"
US_SYMBOL_CACHE_PATH = C.DATA_DIR / "us_symbol_cache.json"
KR_NAME_CACHE_PATH = C.DATA_DIR / "us_kr_name_cache.json"

STABLE_QUOTES = {
    "USDCUSDT", "FDUSDUSDT", "BUSDUSDT", "TUSDUSDT", "USDPUSDT", "DAIUSDT",
    "EURUSDT", "GBPUSDT", "AEURUSDT", "USD1USDT", "PYUSDUSDT", "XUSDUSDT",
    "RLUSDUSDT", "USDEUSDT", "USDTBUSDT",
}


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------- 코스피200
def fetch_kospi200() -> list[dict]:
    """네이버 금융 코스피200 구성종목 페이지를 훑어 종목코드를 모은다.

    공식 문서 없는 페이지 스크래핑이지만, 지수 구성종목은 리밸런싱 때만 바뀌므로
    (기본 주 1회 캐시) 요청 빈도가 매우 낮아 차단 위험이 작다.
    """
    log("코스피200 구성종목 수집…")
    seen: dict[str, str] = {}       # code -> 종목명
    pattern = re.compile(r'code=(\d{6})"[^>]*>([^<]+)</a>')
    for page in range(1, 21):
        try:
            r = _SESSION.get("https://finance.naver.com/sise/entryJongmok.naver",
                             params={"type": "KPI200", "page": page}, timeout=C.REQUEST_TIMEOUT)
            r.encoding = "euc-kr"
            for code, name in pattern.findall(r.text):
                seen.setdefault(code, name)
        except Exception as e:                            # noqa: BLE001
            log(f"  ! {page}페이지 실패: {e}")
        time.sleep(0.15)
    out = [{"ticker": f"KRX:{c}", "name": n, "group": "kospi200"} for c, n in seen.items()]
    log(f"  → {len(out)}종목")
    return out


def resolve_korean_name(symbol_dot_form: str) -> str | None:
    """네이버 증권 자동완성에서 미국주식 한글명을 찾는다. 심볼은 원래 표기(점 형태,
    예: BRK.B)를 써야 한다 — 트레이딩뷰용으로 바꾼 대시 표기(BRK-B)는 안 걸린다."""
    try:
        r = _SESSION.get("https://ac.stock.naver.com/ac",
                         params={"q": symbol_dot_form, "target": "stock"},
                         timeout=C.REQUEST_TIMEOUT)
        r.raise_for_status()
        for it in r.json().get("items", []):
            if it.get("code", "").upper() == symbol_dot_form.upper():
                return it["name"]
    except Exception as e:                                # noqa: BLE001
        log(f"  ! {symbol_dot_form} 한글명 조회 실패: {e}")
    return None


# ---------------------------------------------------------------- S&P500
def fetch_sp500() -> list[dict]:
    """위키백과 S&P500 구성종목 표에서 심볼을 받아, 트레이딩뷰 거래소 접두어와
    네이버 증권 한글 종목명을 붙인다. 둘 다 종목당 1회만 조회하고 영구 캐시한다
    (거래소·한글명 모두 바뀔 일이 거의 없다).
    """
    log("S&P500 구성종목 수집…")
    r = _SESSION.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                     timeout=C.REQUEST_TIMEOUT)
    table = pd.read_html(io.StringIO(r.text))[0]
    orig_symbols = table["Symbol"].tolist()                      # 점 표기(BRK.B) 원본
    tv_symbols = table["Symbol"].str.replace(".", "-", regex=False)  # 트레이딩뷰용(BRK-B)

    tv_cache: dict[str, str] = read_json(US_SYMBOL_CACHE_PATH, {})
    kr_cache: dict[str, str] = read_json(KR_NAME_CACHE_PATH, {})

    out = []
    new_tv, new_kr = 0, 0
    for orig_sym, tv_sym, eng_name in zip(orig_symbols, tv_symbols, table["Security"]):
        ticker = tv_cache.get(tv_sym)
        if not ticker:
            ticker = TV.resolve_exchange(tv_sym)
            new_tv += 1
            if ticker:
                tv_cache[tv_sym] = ticker
            time.sleep(0.15)
        if not ticker:
            continue

        kr_name = kr_cache.get(orig_sym)
        if kr_name is None:
            kr_name = resolve_korean_name(orig_sym) or ""
            kr_cache[orig_sym] = kr_name
            new_kr += 1
            time.sleep(0.15)

        out.append({"ticker": ticker, "name": kr_name or eng_name, "group": "sp500"})

    if new_tv:
        write_json(US_SYMBOL_CACHE_PATH, tv_cache, indent=2)
    if new_kr:
        write_json(KR_NAME_CACHE_PATH, kr_cache, indent=2)
    log(f"  → {len(out)}종목 (신규 거래소 조회 {new_tv}건, 신규 한글명 조회 {new_kr}건)")
    return out


# ---------------------------------------------------------------- 코인
def fetch_all_perpetuals() -> list[dict]:
    """바이낸스 선물(USDT 무기한계약)에 상장된 전체 종목.

    트레이딩뷰에서 무기한선물은 현물과 구분되는 별도 심볼(".P" 접미사)이다
    (예: BINANCE:BTCUSDT.P) — 스팟이 아니라 실제 무기한계약 가격을 본다.
    """
    log("바이낸스 무기한선물 전체 종목 조회…")
    try:
        r = _SESSION.get("https://fapi.binance.com/fapi/v1/exchangeInfo",
                         timeout=C.REQUEST_TIMEOUT)
        r.raise_for_status()
        syms = [s["symbol"] for s in r.json()["symbols"]
               if s["contractType"] in ("PERPETUAL", "TRADIFI_PERPETUAL")
               and s["quoteAsset"] == "USDT"
               and s["status"] == "TRADING" and s["symbol"] not in STABLE_QUOTES]
    except Exception as e:                                # noqa: BLE001
        log(f"  ! 실패: {e}")
        syms = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT"]
    log(f"  → {len(syms)}종목")
    return [{"ticker": f"BINANCE:{s}.P", "name": s, "group": "coin"} for s in syms]


# ---------------------------------------------------------------- 캐시 오케스트레이션
def build_universe(force: bool = False) -> list[dict]:
    if not force:
        cached = read_json(CACHE_PATH, None)
        if cached:
            age = datetime.now() - datetime.fromisoformat(cached["built_at"])
            if age < timedelta(days=C.UNIVERSE_CACHE_DAYS):
                return cached["items"]

    items: list[dict] = []
    if C.INCLUDE_KOSPI200:
        items += fetch_kospi200()
    if C.INCLUDE_SP500:
        items += fetch_sp500()
    items += fetch_all_perpetuals()

    write_json(CACHE_PATH, {"built_at": datetime.now().isoformat(), "items": items}, indent=2)
    log(f"감시 종목 총 {len(items)}개 저장 → {CACHE_PATH.name}")
    return items


if __name__ == "__main__":
    u = build_universe(force=True)
    by_group = pd.Series([it["group"] for it in u]).value_counts()
    print(by_group.to_string())
