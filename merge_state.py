# -*- coding: utf-8 -*-
"""git push 충돌 재시도 시, 겹쳐 돈 다른 실행이 이미 커밋해둔 상태를 잃지 않도록
"티커|구간 → 거래일 라벨" 형태의 상태 파일을 병합한다.

배경: 두 실행(예: 백업 크론과 GitHub 자체 스케줄)이 몇십 초 차이로 겹치면, 늦게
push하는 쪽이 자기 로컬 스냅샷으로 원격을 통째로 덮어써서 — 그 사이 다른 실행이
막 기록해둔 "오늘 이미 알림 보냄" 항목을 지워버릴 수 있다(실제로 이렇게 티커 하나가
사라졌다가 몇 분 뒤 "신규"로 오인돼 알림이 중복 발송된 사례가 있었다).

날짜 라벨(YYYY-MM-DD)은 문자열로 사전순 비교가 곧 날짜순 비교와 같으므로, 같은
키가 양쪽에 다 있으면 더 최신(큰) 라벨을 채택하고, 한쪽에만 있는 키는 그대로
살린다 — 즉 "합집합 + 최신값 우선" 병합. 이걸로 어느 실행이 이기든 데이터 유실이
없어진다.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
FLAT_MERGE_FILES = ["touch_alert_state.json", "new_mark_state.json"]
# 티커 → {날짜: 종가} 형태라 값이 아니라 날짜 키 자체를 합집합해야 한다(같은
# 날짜값 충돌은 어느 쪽이든 관측치 차이가 미미해 로컬을 우선한다). 이걸 빼먹으면
# 오늘 겪은 것과 같은 방식으로 히스토리 날짜가 통째로 유실된다.
NESTED_MERGE_FILES = ["daily_close_history.json"]


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {}


def _read_remote(rel_path: str) -> dict:
    try:
        out = subprocess.run(["git", "show", f"origin/main:{rel_path}"],
                             capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    except Exception:                                       # noqa: BLE001
        return {}


def main() -> None:
    for name in FLAT_MERGE_FILES:
        local_path = DATA_DIR / name
        local = _read_json(local_path)
        remote = _read_remote(f"data/{name}")
        merged = dict(local)
        for key, remote_label in remote.items():
            if key not in merged or remote_label > merged[key]:
                merged[key] = remote_label
        local_path.write_text(json.dumps(merged, ensure_ascii=False, sort_keys=True),
                              encoding="utf-8")
        print(f"[merge_state] {name}: local={len(local)} remote={len(remote)} "
              f"-> merged={len(merged)}", flush=True)

    for name in NESTED_MERGE_FILES:
        local_path = DATA_DIR / name
        local = _read_json(local_path)
        remote = _read_remote(f"data/{name}")
        merged = {t: dict(days) for t, days in remote.items()}
        for ticker, days in local.items():
            merged.setdefault(ticker, {}).update(days)
        local_path.write_text(json.dumps(merged, ensure_ascii=False, sort_keys=True),
                              encoding="utf-8")
        print(f"[merge_state] {name}: local={len(local)} remote={len(remote)} "
              f"-> merged={len(merged)}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
