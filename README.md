# 나라장터 회계 용역공고 텔레그램 알림 (v2)

2시간마다 나라장터 용역 입찰공고를 조회 → 공고명에 회계 관련 키워드가 있는 신규 건만 텔레그램 발송.

## GitHub Secrets (Settings > Secrets and variables > Actions)
| 이름 | 값 |
|---|---|
| G2B_SERVICE_KEY | 공공데이터포털 일반 인증키 |
| TELEGRAM_TOKEN | BotFather 봇 토큰 |
| TELEGRAM_CHAT_ID | getUpdates의 chat id 숫자 |

## 조정
- 키워드: `notify_bids.py` 상단 `INCLUDE` / `EXCLUDE`
- 주기: `.github/workflows/g2b-alert.yml`의 cron (UTC 기준)
- Actions 실행 시 `API 응답 오류` → data.go.kr 해외 IP 차단 가능성. 국내 서버(Oracle Cloud 서울 무료 VM 등)로 이전
