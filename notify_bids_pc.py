"""나라장터 회계 관련 용역 입찰공고 텔레그램 알림 (v6, 내 PC용)
- 같은 폴더의 config.json에서 키를 읽음
- 마지막 조회 시점~지금까지 조회 → PC가 꺼져 있던 동안의 공고도 켜진 뒤 한 번에 알림 (최대 3일)
- 실행 기록·오류는 같은 폴더 log.txt
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
BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "state.json")
LOG_FILE = os.path.join(BASE, "log.txt")
MAX_CATCHUP_DAYS = 3
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
            raise RuntimeError(f"API 응답 오류: {raw[:300]}")
        if resp["header"]["resultCode"] != "00":
            raise RuntimeError(f"API 오류: {resp['header']}")
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
    http(url, data=data, label="텔레그램")


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


def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(KST):%Y-%m-%d %H:%M} {msg}\n")


def main():
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        os.environ.update(json.load(f))
    now = datetime.now(KST).replace(second=0, microsecond=0)
    begin = now - timedelta(hours=2)
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            last = datetime.fromisoformat(json.load(f)["last_end"])
        begin = max(last + timedelta(minutes=1), now - timedelta(days=MAX_CATCHUP_DAYS))
    if begin > now:
        return
    new = [it for it in fetch(begin.strftime("%Y%m%d%H%M"), now.strftime("%Y%m%d%H%M"))
           if is_target(it.get("bidNtceNm", ""))]
    if new:
        send_alert(new, now)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_end": now.isoformat()}, f)
    log(f"{begin:%m/%d %H:%M}~{now:%m/%d %H:%M} 신규 {len(new)}건")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"오류: {e}")
        try:
            tg_send(f"[나라장터 알림] 실행 오류: {escape(str(e))[:500]}")
        except Exception:
            pass
