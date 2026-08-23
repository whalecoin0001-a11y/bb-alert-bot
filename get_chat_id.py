# -*- coding: utf-8 -*-
"""텔레그램 봇에게 보낸 메시지에서 채팅 ID를 찾는다.
먼저 채팅방(그룹/DM)에서 봇과 대화를 시작하고 아무 메시지나 보낸 뒤 이 스크립트를 실행하세요.
"""
import requests
import config as C


def main():
    token = C.TELEGRAM_BOT_TOKEN
    if not token:
        print("TELEGRAM_BOT_TOKEN을 찾을 수 없습니다. secrets.env에 값을 채워 넣으세요.")
        return
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15)
    data = r.json()
    if not data.get("ok"):
        print(f"실패: {data}")
        return
    results = data.get("result", [])
    if not results:
        print("메시지가 없습니다. 채팅방에서 봇과 대화를 시작하고 메시지를 보낸 뒤 다시 실행하세요.")
        return
    seen = {}
    for upd in results:
        msg = upd.get("message") or upd.get("channel_post")
        if not msg:
            continue
        chat = msg["chat"]
        seen[chat["id"]] = chat
    print("발견된 채팅:")
    for cid, chat in seen.items():
        name = chat.get("username") or chat.get("first_name") or chat.get("title") or ""
        print(f"  chat_id = {cid}   ({chat.get('type')}, {name})")
    if len(seen) == 1:
        cid = next(iter(seen))
        print(f"\n이 값을 secrets.env 의 TELEGRAM_CHAT_ID 에 넣으세요: {cid}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
