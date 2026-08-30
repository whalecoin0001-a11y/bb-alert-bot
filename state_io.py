# -*- coding: utf-8 -*-
"""JSON 상태/캐시 파일 공용 읽기·쓰기 헬퍼. check_bb.py/universe.py/backfill_history.py 공용."""
from __future__ import annotations

import json
from pathlib import Path


def read_json(path: Path, default):
    """없거나 깨졌으면 default를 그대로 돌려준다."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            return default
    return default


def write_json(path: Path, obj, **kwargs) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, **kwargs), encoding="utf-8")
