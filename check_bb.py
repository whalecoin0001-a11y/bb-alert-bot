# -*- coding: utf-8 -*-
"""주봉 볼린저밴드 상단/중단/하단 터치 대시보드 — 메인 실행 스크립트.

    python check_bb.py              # 감시 종목 전체 체크 + 고정 메시지 갱신
    python check_bb.py --refresh    # 종목 리스트(코스피200/S&P500/코인)를 강제로 새로 받음

매번 새 메시지를 보내는 게 아니라, 최초 1회 보낸 메시지를 고정(pin)해두고
그 이후로는 같은 메시지를 내용만 갈아끼운다(텔레그램 편집 API). 즉 대시보드
형태로 "지금 어떤 종목이 어느 구간에 있는지"를 계속 보여준다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import config as C
import telegram_notify as TG
import tv_scanner as TV
import universe as U

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass

PIN_STATE_PATH = C.DATA_DIR / "pinned_message.json"
TOUCH_STATE_PATH = C.DATA_DIR / "touch_alert_state.json"
PRICE_STATE_PATH = C.DATA_DIR / "price_state.json"
PRESENCE_STATE_PATH = C.DATA_DIR / "zone_presence_state.json"
NEW_MARK_STATE_PATH = C.DATA_DIR / "new_mark_state.json"
ZONE_TOUCH_LABEL = {"upper": "상단터치", "mid": "중단터치", "lower": "하단터치"}

GROUP_MARKET = {"kospi200": "korea", "sp500": "america", "coin": "crypto"}
GROUP_LABEL = {"kospi200": "코스피200", "sp500": "S&P500", "coin": "코인"}
GROUP_KIND = {"kospi200": "kr", "sp500": "us", "coin": "coin"}
KIND_ORDER = ["coin", "kr", "us"]
KIND_LABEL = {"kr": "KR", "us": "US", "coin": "COIN"}
ZONE_ORDER = ["upper", "mid", "lower"]
ZONE_TITLE = {"upper": "상단", "mid": "중단", "lower": "하단"}


KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """GitHub Actions는 UTC로 돌아가므로, 사람이 보는 시각은 전부 KST로 맞춘다."""
    return datetime.now(KST)


def trading_day_label(dt: datetime) -> str:
    """KST 09:00:00 ~ 다음날 08:59:59를 하루로 묶는 날짜 라벨.
    09시 이전이면 전날 날짜에 속한다(자정~08:59는 전날 거래일 연장으로 취급)."""
    d = dt.date() if dt.hour >= 9 else dt.date() - timedelta(days=1)
    return d.isoformat()


def log(msg: str) -> None:
    print(f"[{now_kst():%H:%M:%S}] {msg}", flush=True)


def proximities(close: float, upper: float, mid: float, lower: float,
               kind_cat: str) -> dict[str, float]:
    """각 밴드 선에서 ±임계값% 이내인 선들과, 그 선 기준 부호 있는 괴리율(%).

    괴리율 = (종가 - 그 선 값) / 그 선 값 × 100. 선 아래면 음수, 위면 양수.
    한 종목이 동시에 여러 선에 걸릴 수 있다(밴드 폭이 좁을 때).
    임계값은 구간(상단/중단/하단)×종류(주식/코인)별로 다르다(config.PROXIMITY_PCT).
    """
    out = {}
    for zone, band in (("upper", upper), ("mid", mid), ("lower", lower)):
        if not band:
            continue
        pct = (close - band) / band * 100
        if abs(pct) <= C.PROXIMITY_PCT[zone][kind_cat]:
            out[zone] = pct
    return out


def display_name(group: str, name: str) -> str:
    """코인은 'BTCUSDT' 대신 'BTC'로 표시한다.
    미국주식은 네이버 증권 한글명을 그대로 쓴다(티커는 안 붙임) — 한국주식과
    표기 방식을 통일해서 더 깔끔하게 보이도록."""
    if group == "coin" and name.endswith("USDT"):
        return name[:-4]
    return name


def _vwidth(s: str) -> int:
    """한글 등 non-ASCII 문자는 고정폭 글꼴에서 2칸을 차지한다고 보고 계산한 표시 너비."""
    return sum(2 if ord(c) > 0x2000 else 1 for c in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _vwidth(s))


NEW_MARK = "🆕"
NEW_MARK_BLANK = "  "  # 마커와 표시 너비(2칸)를 맞춰 정렬이 흐트러지지 않게 한다.


def _fmt_pct(pct: float) -> str:
    """방향을 +/- 대신 화살표로 표시해 눈으로 더 빨리 스캔되게 한다."""
    arrow = "▲" if pct >= 0 else "▼"
    return f"{arrow}{abs(pct):5.1f}%"


def _fmt_block(entries: list[tuple[str, float, float, bool]]) -> list[str]:
    """entries: [(이름, 괴리율%, 규모, 당일신규여부), ...] — 근접도(0%에 가까운 순)로
    정렬해 "지금 제일 급한 것"이 위로 오게 한다(규모는 더 이상 정렬 기준이 아님).
    이름을 자르지 않고, 그 블록에서 가장 긴 이름 기준으로 폭을 맞춰 괴리율을
    세로로 정렬한다(코드블록 안에 넣을 용도). 당일(거래일 기준) 새로 근접권에
    들어온 종목은 이름 앞에 🆕를 붙인다(텔레그램 코드블록은 글자색을 지원하지
    않아 색 대신 이모지로 표시)."""
    if not entries:
        return []
    entries = sorted(entries, key=lambda e: abs(e[1]))
    labeled = [(f"{NEW_MARK if is_new else NEW_MARK_BLANK}{name}", pct)
               for name, pct, _, is_new in entries]
    width = max(_vwidth(name) for name, _ in labeled)
    return [f"{_pad(name, width)} {_fmt_pct(pct)}" for name, pct in labeled]


def build_zone_message(zone: str, zone_buckets: dict[str, list[tuple[str, float, float, bool]]]) -> str:
    """한 구간(상단/중단/하단) 전체의 코드블록 메시지. 종목은 전부 표시한다.

    임계값이 구간×종류별로 좁게 잡혀 있어(config.PROXIMITY_PCT) 종목 수가 많지
    않으므로, 종류(COIN/KR/US)를 다시 한 메시지로 합쳐도 4096자 한도 안에 든다.
    """
    ts = now_kst().strftime("%Y-%m-%d %H:%M")
    block_lines = []
    total_count = 0
    new_count = 0
    for kind in KIND_ORDER:
        entries = zone_buckets[kind]
        total_count += len(entries)
        new_count += sum(1 for _, _, _, is_new in entries if is_new)
        kind_cat = "coin" if kind == "coin" else "stock"
        threshold = C.PROXIMITY_PCT[zone][kind_cat]
        block_lines.append(f"[{KIND_LABEL[kind]} {len(entries)} · ±{threshold:g}%]")
        block_lines += (_fmt_block(entries) if entries else ["  -"])
        block_lines.append("")
    header = [f"볼린저밴드 {ZONE_TITLE[zone]} 근접", f"{ts} 기준 · 근접도순",
              f"오늘 신규 {new_count}건 · 총 근접 {total_count}건", ""]
    code = "\n".join(header + block_lines).rstrip()
    return f"```\n{code}\n```"


def format_kr_time(dt: datetime) -> str:
    ampm = "오전" if dt.hour < 12 else "오후"
    h12 = dt.hour % 12 or 12
    return f"{dt:%Y-%m-%d} {ampm} {h12:02d}:{dt.minute:02d}"


def touch_alert_text(kind: str, name: str, zone: str) -> str:
    """Coin_notification [2026-08-23 오전 11:44]
    BTC 볼린저밴드 하단터치(1W)"""
    category = "Coin" if kind == "coin" else "STOCK"
    ts = format_kr_time(now_kst())
    return f"{category}_notification [{ts}]\n{name} 볼린저밴드 {ZONE_TOUCH_LABEL[zone]}({C.BB_TIMEFRAME})"


def surge_alert_text(kind: str, name: str, pct: float) -> str:
    """🚨🚨🚨 Coin_notification [2026-08-23 오전 11:44]
    BTC 5분 급등 +12.3%"""
    category = "Coin" if kind == "coin" else "STOCK"
    ts = format_kr_time(now_kst())
    label = "급등" if pct > 0 else "급락"
    return f"🚨🚨🚨 {category}_notification [{ts}]\n{name} 5분 {label} {pct:+.1f}%"


def load_price_state() -> dict[str, float]:
    if PRICE_STATE_PATH.exists():
        try:
            return json.loads(PRICE_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            return {}
    return {}


def save_price_state(prices: dict[str, float]) -> None:
    PRICE_STATE_PATH.write_text(json.dumps(prices, ensure_ascii=False), encoding="utf-8")


def load_touch_state() -> dict[str, str]:
    """"티커|구간" → 마지막으로 알림을 보낸 거래일 라벨(trading_day_label)."""
    if TOUCH_STATE_PATH.exists():
        try:
            raw = json.loads(TOUCH_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            return {}
        if isinstance(raw, list):
            # 구 형식(현재 근접 종목 목록만 저장) 마이그레이션 — 배포 직후 재알림
            # 폭주를 막기 위해 전부 "오늘 이미 알림 보냄"으로 간주한다.
            return {key: trading_day_label(now_kst()) for key in raw}
        return dict(raw)
    return {}


def save_touch_state(state: dict[str, str], today: str) -> None:
    """오늘·어제 라벨만 남기고 오래된 항목은 정리해 파일이 무한히 커지지 않게 한다."""
    yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    pruned = {k: v for k, v in state.items() if v in (today, yesterday)}
    TOUCH_STATE_PATH.write_text(json.dumps(pruned, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def load_presence_state() -> set[str]:
    """지난 실행(약 5분 전)에 근접권에 있던 "티커|구간" 집합 — 대시보드 🆕 표시가
    "진짜 방금 들어온 것"만 잡도록, 개별 알림용 하루 단위 상태와는 별개로 둔다."""
    if PRESENCE_STATE_PATH.exists():
        try:
            return set(json.loads(PRESENCE_STATE_PATH.read_text(encoding="utf-8")))
        except Exception:                                   # noqa: BLE001
            return set()
    return set()


def save_presence_state(keys: set[str]) -> None:
    PRESENCE_STATE_PATH.write_text(json.dumps(sorted(keys), ensure_ascii=False), encoding="utf-8")


def load_new_mark_state() -> dict[str, str]:
    """"티커|구간" → 🆕로 표시하기 시작한 거래일 라벨. 그날 안에는 벗어났다 다시
    들어와도 계속 🆕로 유지되고, 거래일이 바뀌면 자연히 사라진다."""
    if NEW_MARK_STATE_PATH.exists():
        try:
            return dict(json.loads(NEW_MARK_STATE_PATH.read_text(encoding="utf-8")))
        except Exception:                                   # noqa: BLE001
            return {}
    return {}


def save_new_mark_state(state: dict[str, str], today: str) -> None:
    yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    pruned = {k: v for k, v in state.items() if v in (today, yesterday)}
    NEW_MARK_STATE_PATH.write_text(json.dumps(pruned, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def load_pin_state() -> dict:
    if PIN_STATE_PATH.exists():
        try:
            return json.loads(PIN_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            return {}
    return {}


def save_pin_state(state: dict) -> None:
    PIN_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def publish(key: str, label: str, text: str, state: dict) -> None:
    """구간×종류별 고정 메시지가 없으면 새로 보내고 고정, 있으면 내용만 편집.

    내용이 지난번과 같으면(state의 last_text와 일치) 아예 API를 호출하지 않는다 —
    텔레그램의 '변경 없음' 오류와 '진짜 편집 실패'를 구분하기 위함이다. 편집이
    실패해도 새 메시지를 또 보내지 않는다(그러면 고정 메시지가 계속 늘어난다) —
    다음 주기에 같은 message_id로 다시 시도한다.
    """
    entry = state.get(key) or {}
    message_id = entry.get("message_id")

    if message_id and entry.get("last_text") == text:
        log(f"[{label}] 변경 없음")
        return

    if message_id:
        if TG.edit_message(message_id, text):
            entry["last_text"] = text
            state[key] = entry
            save_pin_state(state)
            log(f"[{label}] 고정 메시지 갱신 완료")
        else:
            log(f"[{label}]  ! 고정 메시지 편집 실패 — 다음 주기에 재시도")
        return

    new_id = TG.send_and_get_id(text)
    if not new_id:
        log(f"[{label}]  ! 텔레그램 전송 실패(토큰/채팅ID 확인)")
        return
    TG.pin_message(new_id)
    state[key] = {"message_id": new_id, "last_text": text}
    save_pin_state(state)
    log(f"[{label}] 새 메시지 전송 + 고정 완료 (message_id={new_id})")


def run(refresh: bool = False) -> None:
    items = U.build_universe(force=refresh)
    buckets = {z: {k: [] for k in KIND_ORDER} for z in ZONE_ORDER}
    coin_mcap = U.fetch_coin_market_caps()
    touch_info: dict[str, tuple[str, str, str]] = {}   # "티커|구간" → (kind, name, zone)
    price_now: dict[str, tuple[str, str, float]] = {}  # 티커 → (kind, name, 현재가)

    by_group: dict[str, list[dict]] = {}
    for it in items:
        by_group.setdefault(it["group"], []).append(it)

    for group, group_items in by_group.items():
        market = GROUP_MARKET[group]
        tickers = [it["ticker"] for it in group_items]
        name_of = {it["ticker"]: it["name"] for it in group_items}
        log(f"{GROUP_LABEL[group]} {len(tickers)}종목 조회 중…")
        bb = TV.fetch_bb(tickers, market)

        kind = GROUP_KIND[group]
        kind_cat = "coin" if kind == "coin" else "stock"
        for ticker, vals in bb.items():
            name = display_name(group, name_of.get(ticker, ticker))
            size = vals["mcap"] if vals["mcap"] is not None else coin_mcap.get(name, 0.0)
            price_now[ticker] = (kind, name, vals["close"])
            for zone, pct in proximities(vals["close"], vals["upper"], vals["basis"],
                                         vals["lower"], kind_cat).items():
                buckets[zone][kind].append((ticker, name, pct, size))
                touch_info[f"{ticker}|{zone}"] = (kind, name, zone)

    # 급등/급락 감지: 이번 체크 가격을 지난 체크(약 5분 전) 가격과 비교.
    # 최초 실행은 비교 기준이 없으므로 가격만 저장하고 알림은 건너뛴다.
    is_first_price_run = not PRICE_STATE_PATH.exists()
    price_prev = load_price_state()
    if is_first_price_run:
        log(f"[급등락] 최초 실행 — 기준가 {len(price_now)}건 저장, 알림 생략")
    else:
        for ticker, (kind, name, close) in price_now.items():
            prev = price_prev.get(ticker)
            if not prev:
                continue
            pct = (close - prev) / prev * 100
            if abs(pct) >= C.SURGE_PCT:
                text = surge_alert_text(kind, name, pct)
                if TG.send(text, parse_mode=None):
                    log(f"[급등락] {text.replace(chr(10), ' ')}")
                else:
                    log(f"[급등락]  ! 전송 실패: {text.replace(chr(10), ' ')}")
    save_price_state({t: c for t, (_, _, c) in price_now.items()})

    # 같은 종목×구간은 하루(KST 09:00~다음날 08:59:59)에 1번만 개별 알림.
    # 그 안에서 근접권을 벗어났다 다시 들어와도 재알림하지 않는다(스팸 방지).
    # 단, 같은 날 다른 구간(상/중/하단)에 닿으면 구간별로는 각각 알림이 온다.
    # 최초 실행(상태 파일이 아예 없음)은 지금 근접해 있는 것 전부가 쏟아지므로,
    # 그때는 기준선만 저장하고 알림은 건너뛴다.
    is_first_run = not TOUCH_STATE_PATH.exists()
    touch_prev = load_touch_state()
    today = trading_day_label(now_kst())
    new_touches = set() if is_first_run else {
        key for key in touch_info if touch_prev.get(key) != today
    }
    if is_first_run:
        log(f"[개별알림] 최초 실행 — 기준선 {len(touch_info)}건 저장, 알림 생략")
    for key in sorted(new_touches):
        kind, name, zone = touch_info[key]
        text = touch_alert_text(kind, name, zone)
        if TG.send(text, parse_mode=None):
            log(f"[개별알림] {text.replace(chr(10), ' ')}")
        else:
            log(f"[개별알림]  ! 전송 실패: {text.replace(chr(10), ' ')}")
    touch_prev.update({key: today for key in touch_info})
    save_touch_state(touch_prev, today)

    # 고정 대시보드용 "당일 신규 진입" 표시 — 개별 알림 dedup(위 touch_prev, 하루에
    # 한 번은 계속 있어도 리셋됨)과는 별개로, "지난 실행에는 없었는데 지금 생겼다"는
    # 진짜 진입 이벤트만 🆕로 잡는다. 그래야 원래부터 계속 근접해 있던 종목이 단순히
    # 날짜가 바뀌었다는 이유만으로 🆕로 잘못 표시되지 않는다. 같은 거래일 안에서
    # 벗어났다 다시 들어오면 그 시점에 다시 진입 이벤트로 잡혀 하루 내내 🆕 유지.
    is_first_presence_run = not PRESENCE_STATE_PATH.exists()
    presence_prev = load_presence_state()
    new_mark_state = load_new_mark_state()
    entered_now = set() if is_first_presence_run else set(touch_info) - presence_prev
    new_mark_state.update({key: today for key in entered_now})
    save_new_mark_state(new_mark_state, today)
    save_presence_state(set(touch_info))
    if is_first_presence_run:
        log(f"[신규표시] 최초 실행 — 기준선 {len(touch_info)}건 저장, 🆕 표시 생략")

    new_today: set[str] = {key for key in touch_info if new_mark_state.get(key) == today}
    display_buckets = {
        z: {k: [(name, pct, size, f"{ticker}|{z}" in new_today)
                for ticker, name, pct, size in buckets[z][k]]
            for k in KIND_ORDER}
        for z in ZONE_ORDER
    }

    state = load_pin_state()
    for zone in ZONE_ORDER:
        text = build_zone_message(zone, display_buckets[zone])
        label = ZONE_TITLE[zone]
        log(f"[{label}] {text.replace(chr(10), ' | ')[:200]}")
        publish(zone, label, text, state)
    TG.clear_error_state()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="종목 리스트 강제 갱신")
    args = ap.parse_args()

    try:
        run(refresh=args.refresh)
    except Exception as e:                                  # noqa: BLE001
        import traceback
        traceback.print_exc()
        TG.send_error_once("주봉 볼린저밴드 체크(check_bb.py)", e)
