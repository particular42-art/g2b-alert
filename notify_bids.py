"""나라장터 회계 관련 용역 입찰공고 텔레그램 알림 (v8, 나라장터+누리장터, GitHub Actions용)

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
SOURCES = [  # (표시이름, 용역 공고목록 주소, 1회 조회 건수, 공고번호 접두어)
    ("나라장터", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc", 999, ""),
    ("누리장터", "https://apis.data.go.kr/1230000/ao/PrvtBidNtceService/getPrvtBidPblancListInfoServc", 100, "N-"),
]
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


def g(it, *keys):
    """여러 후보 항목명 중 값이 있는 첫 번째를 반환 (두 API의 항목명 차이 흡수)"""
    for k in keys:
        if it.get(k) not in (None, ""):
            return it[k]
    return ""


def fetch(endpoint, rows, begin, end, label):
    items, page = [], 1
    key = "".join(os.environ["G2B_SERVICE_KEY"].split()).replace("\ufeff", "").replace("\u200b", "")
    while True:
        q = f"ServiceKey={key}&" + urllib.parse.urlencode({  # 키는 브라우저처럼 그대로 전송
            "type": "json", "inqryDiv": "1", "inqryBgnDt": begin, "inqryEndDt": end,
            "pageNo": page, "numOfRows": rows})
        raw = http(f"{endpoint}?{q}", label=label)
        try:
            resp = json.loads(raw)["response"]
        except (ValueError, KeyError):
            raise RuntimeError(f"[{label}] 응답 오류: {raw[:300]}")
        if resp["header"]["resultCode"] != "00":
            raise RuntimeError(f"[{label}] API 오류: {resp['header']}")
        body = resp["body"]
        got = body.get("items") or []
        if isinstance(got, dict):
            got = got.get("item", [])
        if isinstance(got, dict):
            got = [got]
        items += got
        if page * rows >= int(body.get("totalCount", 0) or 0) or not got:
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
    for src, r in rows:
        link = escape(g(r, "bidNtceDtlUrl", "bidNtceUrl", "ntceUrl", "ntceSpecDocUrl1"))
        name = escape(g(r, "bidNtceNm", "ntceNm"))
        price = won(g(r, "presmptPrce", "asignBdgtAmt", "bssamt"))
        blocks.append(
            f"• [{src}] <a href='{link}'>{name}</a>\n"
            f"  {escape(g(r, 'ntceInsttNm', 'dminsttNm'))} | 마감 {escape(g(r, 'bidClseDt') or '-')}"
            f" | {price}원")
    head = f"<b>[입찰알림] 회계 관련 용역공고 {len(rows)}건</b> ({now:%m/%d %H:%M})"
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
    for src, endpoint, rows, prefix in SOURCES:
        try:
            items = fetch(endpoint, rows, begin.strftime("%Y%m%d%H%M"), now.strftime("%Y%m%d%H%M"), src)
        except Exception as e:            # 한쪽이 실패해도 다른 쪽 알림은 진행
            print(f"[경고] {src} 조회 실패: {e}")
            continue
        if items:
            print(f"[{src}] 조회 {len(items)}건, 항목명: {sorted(items[0].keys())[:40]}")
        for it in items:
            key = f"{prefix}{g(it, 'bidNtceNo')}-{g(it, 'bidNtceOrd')}"
            if key in seen or not is_target(g(it, "bidNtceNm", "ntceNm")):
                continue
            seen[key] = now.strftime("%Y-%m-%d")
            new.append((src, it))

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
