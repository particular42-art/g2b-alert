"""나라장터 회계 관련 용역 입찰공고 텔레그램 알림 (v7, GitHub Actions용)

환경변수
  G2B_SERVICE_KEY  : 공공데이터포털 일반 인증키
  TELEGRAM_TOKEN   : BotFather가 준 봇 토큰
  TELEGRAM_CHAT_ID : 받을 사람의 chat id (숫자)
  LOOKBACK_HOURS  : 조회 구간(시간), 기본 3  ← 실행주기(2h)보다 약간 길게 두고 중복은 seen.json으로 제거
"""
import json, os, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from html import escape

# ---------------- 설정 ----------------
INCLUDE = ["회계", "결산", "재무", "세무", "원가", "가치평가", "기업진단",
           "정산검증", "사업비 정산", "외부감사", "내부통제", "감사인"]
NOISE = ["회계연도", "회계년도"]          # 공고명에서 지운 뒤 키워드 매칭 (예: '2027회계연도 청소용역')
EXCLUDE = ["감정평가"]                    # 포함 시 공고 자체 제외
ENDPOINT = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"  # 용역
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")
KEEP_DAYS = 30
KST = timezone(timedelta(hours=9))
# --------------------------------------
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def http(url, data=None, label=""):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=60) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"[{label}] HTTP {e.code}: {body}") from None


def fetch(begin, end):
    items, page = [], 1
    while True:
        key = "".join(os.environ["G2B_SERVICE_KEY"].split()).replace("\ufeff", "").replace("\u200b", "")
        q = f"ServiceKey={key}&" + urllib.parse.urlencode({  # 키는 브라우저처럼 그대로 전송
            "type": "json",
            "inqryDiv": "1", "inqryBgnDt": begin, "inqryEndDt": end,
            "pageNo": page, "numOfRows": 999})
        raw = http(f"{ENDPOINT}?{q}", label="나라장터 API")
        try:
            resp = json.loads(raw)["response"]
        except (ValueError, KeyError):
            sys.exit(f"API 응답 오류: {raw[:300]}")
        if resp["header"]["resultCode"] != "00":
            sys.exit(f"API 오류: {resp['header']}")
        body = resp["body"]
        got =
