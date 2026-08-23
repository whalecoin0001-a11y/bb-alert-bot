# -*- coding: utf-8 -*-
"""텔레그램 전송. 토큰/채팅ID 없으면 조용히 스킵."""
from __future__ import annotations

import html
import json
import traceback

import requests

import config as C

_ERROR_STATE_PATH = C.DATA_DIR / "error_alert_state.json"


def _call(method: str, payload: dict) -> dict | None:
    if not C.TELEGRAM_BOT_TOKEN:
        return None
    try:
        r = requests.post(f"https://api.telegram.org/bot{C.TELEGRAM_BOT_TOKEN}/{method}",
                          json=payload, timeout=15)
        data = r.json()
        if not data.get("ok"):
            desc = data.get("description", "")
            if "message is not modified" not in desc:
                print(f"  ! 텔레그램 {method} 실패: {desc}")
            return None
        return data.get("result")
    except Exception as e:                                  # noqa: BLE001
        print(f"  ! 텔레그램 {method} 에러: {e}")
        return None


def send(text: str, parse_mode: str | None = "HTML") -> bool:
    if not C.TELEGRAM_CHAT_ID:
        return False
    payload = {"chat_id": C.TELEGRAM_CHAT_ID, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _call("sendMessage", payload) is not None


def send_and_get_id(text: str, parse_mode: str = "Markdown") -> int | None:
    if not C.TELEGRAM_CHAT_ID:
        return None
    result = _call("sendMessage", {"chat_id": C.TELEGRAM_CHAT_ID, "text": text,
                                   "parse_mode": parse_mode})
    return result.get("message_id") if result else None


def edit_message(message_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """기존 메시지를 새 내용으로 갈아끼운다. 내용이 이전과 같으면 텔레그램이
    'message is not modified' 오류를 주는데, 이건 실패가 아니라 정상(무변화)이다.
    """
    if not C.TELEGRAM_CHAT_ID:
        return False
    result = _call("editMessageText", {"chat_id": C.TELEGRAM_CHAT_ID, "message_id": message_id,
                                       "text": text, "parse_mode": parse_mode})
    return result is not None


def pin_message(message_id: int) -> bool:
    if not C.TELEGRAM_CHAT_ID:
        return False
    return _call("pinChatMessage", {"chat_id": C.TELEGRAM_CHAT_ID, "message_id": message_id,
                                    "disable_notification": True}) is not None


def unpin_message(message_id: int) -> bool:
    if not C.TELEGRAM_CHAT_ID:
        return False
    return _call("unpinChatMessage", {"chat_id": C.TELEGRAM_CHAT_ID,
                                      "message_id": message_id}) is not None


def send_error_once(context: str, exc: BaseException) -> None:
    """같은 오류가 반복되는 동안은 1회만 알린다(스팸 방지)."""
    key = f"{context}:{type(exc).__name__}:{exc}"
    prev_key = None
    if _ERROR_STATE_PATH.exists():
        try:
            prev_key = json.loads(_ERROR_STATE_PATH.read_text(encoding="utf-8")).get("key")
        except Exception:                                  # noqa: BLE001
            pass
    if prev_key == key:
        return
    tb = html.escape("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-1500:])
    send(f"🚨 <b>BB알림봇 오류</b>\n\n위치: {context}\n"
         f"{html.escape(type(exc).__name__)}: {html.escape(str(exc))}\n\n<pre>{tb}</pre>")
    try:
        _ERROR_STATE_PATH.write_text(json.dumps({"key": key}), encoding="utf-8")
    except Exception:                                       # noqa: BLE001
        pass


def clear_error_state() -> None:
    try:
        if _ERROR_STATE_PATH.exists():
            _ERROR_STATE_PATH.unlink()
    except Exception:                                       # noqa: BLE001
        pass
