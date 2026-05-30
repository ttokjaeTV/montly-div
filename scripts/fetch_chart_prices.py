# -*- coding: utf-8 -*-
"""
똑재TV 월배당 ETF 트래커 — 차트 데이터 수집 (GitHub Actions 자동 실행)

매일 한국시간 18:00 (UTC 09:00)에 GitHub Actions가 자동 실행.
176개 ETF의 5년치 일봉 종가를 네이버 금융 API에서 fetch 후
data/chart-prices.json 으로 저장.

이 JSON은 같은 GitHub Pages 도메인에서 정적 파일로 제공되므로
CORS 문제가 원천적으로 발생하지 않음.

수동 실행:
    python scripts/fetch_chart_prices.py
"""
import urllib.request
import urllib.error
import json
import time
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 한국시간 (GitHub Actions는 UTC라 명시적으로 KST 사용)
KST = timezone(timedelta(hours=9))

# ETF 코드는 index.html의 ETFS 배열에서 자동 추출 (2026/05/28 영구 패치)
# 매월 신규상장 ETF 추가 시 fetch_chart_prices.py 수동 수정 불필요
import re

INDEX_PATH = Path(__file__).resolve().parent.parent / "index.html"

def get_etf_codes():
    """index.html의 ETFS 배열에서 모든 종목 코드 자동 추출.
    패턴: ["c1","c2","c3","c4","code","name","desc","월중/월말", ...]
    """
    content = INDEX_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\["[^"]*","[^"]*","[^"]*","[^"]*","([^"]+)","[^"]*","[^"]*","(월중|월말)"'
    )
    codes = []
    seen = set()
    for m in pattern.finditer(content):
        code = m.group(1)
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes

ETF_CODES = get_etf_codes()
print(f"[fetch_chart_prices] ETF 코드 자동 추출: {len(ETF_CODES)}종 (index.html ETFS 배열 기반)")


def fetch_one(code, start_ymd, end_ymd):
    """단일 ETF의 일봉 종가 가져오기. 반환: [[date_str, close_int], ...]"""
    url = (
        "https://api.finance.naver.com/siseJson.naver"
        f"?symbol={code}&requestType=1"
        f"&startTime={start_ymd}&endTime={end_ymd}&timeframe=day"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ttokjaetv-bot/1.0)",
        "Accept": "application/json",
        "Referer": "https://finance.naver.com/",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    text = text.replace("'", '"')
    parsed = json.loads(text)
    if not isinstance(parsed, list) or len(parsed) < 2:
        return []
    rows = []
    for r in parsed[1:]:
        if not r or len(r) < 5:
            continue
        date = str(r[0])
        close = r[4]
        if close is None:
            continue
        try:
            close = int(close)
        except (ValueError, TypeError):
            continue
        rows.append([date, close])
    return rows


def main():
    # 한국시간 기준 today (cron 19:15 KST에 실행되므로 당일 종가까지 fetch 가능)
    today = datetime.now(KST)
    # 5년치 데이터: today에서 5년 전
    start = today.replace(year=today.year - 5)

    s = start.strftime("%Y%m%d")
    e = today.strftime("%Y%m%d")  # 당일 종가까지 fetch

    print(f"=== 차트 데이터 수집 시작 ===")
    print(f"기간: {s} ~ {e}")
    print(f"대상: {len(ETF_CODES)}개 ETF\n")

    out = {
        "updated": today.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "start": s,
        "end": e,
        "count": 0,
        "data": {},
    }
    success = 0
    fail = []

    for i, code in enumerate(ETF_CODES, 1):
        try:
            rows = fetch_one(code, s, e)
            if rows:
                out["data"][code] = rows
                success += 1
                print(f"[{i:>3}/{len(ETF_CODES)}] {code}: {len(rows)} rows OK")
            else:
                fail.append((code, "empty data"))
                print(f"[{i:>3}/{len(ETF_CODES)}] {code}: empty data")
        except urllib.error.HTTPError as ex:
            fail.append((code, f"HTTP {ex.code}"))
            print(f"[{i:>3}/{len(ETF_CODES)}] {code}: HTTP {ex.code}")
        except Exception as ex:
            fail.append((code, str(ex)))
            print(f"[{i:>3}/{len(ETF_CODES)}] {code}: {ex}")
        # 네이버 부담 줄이기
        time.sleep(0.05)

    out["count"] = success

    # data/ 폴더 생성 후 저장
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "chart-prices.json"
    with open(out_path, "w", encoding="utf-8") as f:
        # 압축: separators 좁게, ASCII 허용
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\n=== 완료 ===")
    print(f"성공: {success} / 실패: {len(fail)}")
    print(f"파일: {out_path} ({size_mb:.2f} MB)")

    if fail:
        print(f"\n실패 종목:")
        for code, reason in fail:
            print(f"  {code}: {reason}")

    # 실패가 너무 많으면 (10개 이상) actions 실패 처리
    if len(fail) > 10:
        print(f"\n[ERROR] 실패 종목 {len(fail)}개로 임계값(10) 초과", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
