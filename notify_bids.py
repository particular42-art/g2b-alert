"""나라장터 회계 관련 용역 입찰공고 텔레그램 알림 (v2)

환경변수
  G2B_SERVICE_KEY  : 공공데이터포털 일반 인증키
  TELEGRAM_TOKEN   : BotFather가 준 봇 토큰
  TELEGRAM_CHAT_ID : 받을 사람의 chat id (숫자)
  LOOKBACK_HOURS  : 조회 구간(시간), 기본 3  ← 실행주기(2h)보다 약간 길게 두고 중복은 seen.json으로 제거
"""
import json, os, sys, urllib.parse, urllib.request
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


def fetch(begin, end):
    items, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "ServiceKey": os.environ["G2B_SERVICE_KEY"], "type": "json",
            "inqryDiv": "1", "inqryBgnDt": begin, "inqryEndDt": end,
            "pageNo": page, "numOfRows": 999})
        with urllib.request.urlopen(f"{ENDPOINT}?{q}", timeout=60) as r:
            raw = r.read().decode("utf-8")
        try:
            resp = json.loads(raw)["response"]
        except (ValueError, KeyError):
            sys.exit(f"API 응답 오류(키 미승인·해외IP 차단 등): {raw[:300]}")
        if resp["header"]["resultCode"] != "00":
            sys.exit(f"API 오류: {resp['header']}")
        body = resp["body"]
        got = body.get("items") or []
        if isinstance(got, dict):
            got = got.get("item", [])
        if isinstance(got, dict):
            got = [got]
        items += got
        if page * 999 >= int(body.get("totalCount", 0)) or not got:
            return items
        page += 1


def is_target(title):
    if any(x in title for x in EXCLUDE):
        return False
    t = title
    for n in NOISE:
        t = t.replace(n, "")
    return any(k in t for k in INCLUDE)


def won(v):
    try:
        return f"{int(float(v)):,}"
    except (TypeError, ValueError):
        return "-"


def tg_send(text):
    data = urllib.parse.urlencode({
        "chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage"
    urllib.request.urlopen(url, data=data, timeout=30).read()


def send_alert(rows, now):
    blocks = []
    for r in rows:
        link = escape(r.get("bidNtceDtlUrl") or "")
        name = escape(r.get("bidNtceNm", ""))
        blocks.append(
            f"• <a href='{link}'>{name}</a>\n"
            f"  {escape(r.get('ntceInsttNm', ''))} | 마감 {escape(r.get('bidClseDt', '') or '-')}"
            f" | 추정 {won(r.get('presmptPrce'))}원")
    head = f"<b>[나라장터] 회계 관련 용역공고 {len(rows)}건</b> ({now:%m/%d %H:%M})"
    msg = head
    for b in blocks:                      # 텔레그램 1회 최대 4096자 → 나눠 보냄
        if len(msg) + len(b) + 2 > 3800:
            tg_send(msg)
            msg = ""
        msg += ("\n\n" if msg else "") + b
    if msg:
        tg_send(msg)


def main():
    now = datetime.now(KST)
    begin = now - timedelta(hours=float(os.getenv("LOOKBACK_HOURS", "3")))
    state = {"seen": {}}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
    seen = state.get("seen", {})

    new = []
    for it in fetch(begin.strftime("%Y%m%d%H%M"), now.strftime("%Y%m%d%H%M")):
        key = f"{it.get('bidNtceNo')}-{it.get('bidNtceOrd')}"
        if key in seen or not is_target(it.get("bidNtceNm", "")):
            continue
        seen[key] = now.strftime("%Y-%m-%d")
        new.append(it)

    if new:
        send_alert(new, now)
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    state = {"last_run": now.isoformat(timespec="minutes"),
             "seen": {k: v for k, v in seen.items() if v >= cutoff}}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print(f"신규 {len(new)}건")


if __name__ == "__main__":
    main()
