# -*- coding: utf-8 -*-
"""GitHub Actions 워크플로우 자체가 실패했을 때(의존성 설치 실패 등) 텔레그램으로 알린다.

check_bb.py 내부에서 발생하는 오류는 이미 그 안에서 send_error_once로 처리되므로,
이 스크립트는 그 코드가 아예 실행되지 못하는 워크플로우 레벨 실패를 잡기 위한 것이다.
"""
import os

import telegram_notify as TG

run_url = os.environ.get("RUN_URL", "(URL 없음)")
TG.send_error_once("GitHub Actions 워크플로우", RuntimeError(f"실행 실패 — {run_url}"))
