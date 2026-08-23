# BB 알림봇

코스피200 + S&P500 + 코인(바이낸스 거래대금 상위)의 **주봉 볼린저밴드 상단/하단
터치**를 감시해서 텔레그램으로 알려주는 봇입니다.

## 동작 방식

1. `universe.py` — 감시 종목 리스트를 구성합니다.
   - 코스피200: 네이버 금융 구성종목 페이지 스크래핑
   - S&P500: 위키백과 구성종목 표 + 트레이딩뷰 심볼검색으로 거래소 접두어 확인
   - 코인: 바이낸스 USDⓈ-M 무기한선물에 상장된 USDT 페어 전체(스테이블코인 제외,
     금·토큰화주식 같은 TradFi 무기한선물 포함) — 개수 제한 없음
   - 지수 구성종목은 자주 안 바뀌므로 `data/universe.json`에 캐시하고
     기본 7일(`config.UNIVERSE_CACHE_DAYS`)간 재사용합니다.
2. `tv_scanner.py` — 트레이딩뷰 스캐너(비공식 API)에서 종목별 주봉 볼린저밴드
   (상단/중단/하단)를 배치로 받아옵니다. 계산은 트레이딩뷰가 이미 해줍니다.
3. `check_bb.py` — 각 종목의 주봉 상단/중단/하단 선까지 **±`config.PROXIMITY_PCT`%
   (기본 5%)** 이내로 근접한 종목을 모아 대시보드 형태로 보여줍니다.
   매번 새 메시지를 보내는 게 아니라 **최초 1회 보낸 메시지를 고정(pin)해두고
   그 이후로는 내용만 편집**합니다(`data/pinned_message.json`에 message_id 저장).

## 메시지 양식

```
*볼린저밴드 상단 근접(1W, ±5%)*
  COIN
  BTC(+3.2%) / ETH(-1.1%)
  STOCK
  삼성전자(+0.8%) / SK하이닉스(-4.3%)

*볼린저밴드 중단 근접(1W, ±5%)*
  ...

*볼린저밴드 하단 근접(1W, ±5%)*
  ...

_최근 갱신 2026-08-23 21:30_
```

괄호 안 숫자는 그 선(상단/중단/하단 각각) 대비 괴리율입니다. 선 아래면 `-`,
위면 `+`. 한 목록당 최대 40개까지만 보여주고 나머지는 "외 N개"로 축약합니다
(텔레그램 메시지 길이 제한 4096자 보호용). `±5%`는 넓은 편이라 상단/중단/하단
목록이 늘 꽤 길게 찰 수 있습니다 — 너무 많다 싶으면 `config.PROXIMITY_PCT`를
낮추세요.

## 설정

ant_rsi 프로젝트와 완전히 독립적인 봇을 씁니다. `secrets.env.example`을 복사해서
`secrets.env`로 이름을 바꾸고 아래 순서로 채우세요.

1. 텔레그램에서 **@BotFather**와 대화 시작 → `/newbot` → 이름 정하기 →
   발급된 토큰을 `TELEGRAM_BOT_TOKEN`에 붙여넣기
2. 이 봇을 쓸 채팅방(그룹 또는 개인 DM)에서 봇과 대화를 시작하고 아무 메시지나 보내기
3. `python get_chat_id.py` 실행 → 알려주는 chat_id를 `TELEGRAM_CHAT_ID`에 채우기

## 실행

```bash
python check_bb.py            # 1회 체크 + 고정 메시지 갱신
python check_bb.py --refresh  # 종목 리스트 강제 갱신 + 체크
python universe.py             # 종목 리스트만 갱신(디버그용)
python get_chat_id.py          # chat_id 확인
```

## 자동화

Windows 작업 스케줄러에 `BBAlert_Check` 작업이 이미 등록돼 있습니다
(`1_체크실행.bat` → `check_bb.py`, 5분마다, 콘솔창 숨김, 절전모드 깨우지 않음).

주기를 바꾸려면:
```powershell
$task = Get-ScheduledTask -TaskName "BBAlert_Check"
$trigger = $task.Triggers[0]
$trigger.Repetition.Interval = "PT10M"   # 원하는 주기로
Set-ScheduledTask -TaskName "BBAlert_Check" -Trigger $trigger
```

## 주의사항

- `scanner.tradingview.com` / `symbol-search.tradingview.com`은 **공식 문서가
  없는 비공식 엔드포인트**입니다. 트레이딩뷰 웹사이트 자체가 쓰는 트래픽이라
  개별 브로커 스크래핑보다 덜 튀지만, 예고 없이 막힐 수 있습니다. 개인 리서치
  목적으로만 쓰세요.
- 네이버 금융 코스피200 페이지 스크래핑도 비공식입니다. 다만 주 1회 정도만
  호출되므로(캐시) 차단 위험은 낮습니다.
- 종목 수가 많을 때(S&P500 최초 구축)는 트레이딩뷰 심볼검색을 종목당 1회씩
  호출하느라 몇 분 걸립니다. 이후에는 `data/us_symbol_cache.json`에 영구
  캐시돼서 빠릅니다.
