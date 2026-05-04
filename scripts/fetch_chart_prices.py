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
from datetime import datetime, timedelta
from pathlib import Path

# 176개 ETF 코드 (월배당 트래커 전체)
ETF_CODES = [
    "091170", "104530", "136340", "153130",
    "161510", "166400", "181480", "182480",
    "211900", "214980", "237370", "245340",
    "251600", "273140", "279530", "284430",
    "289480", "290080", "316300", "322410",
    "329200", "329650", "329660", "329670",
    "332610", "332620", "336160", "341850",
    "352540", "352560", "373790", "402970",
    "423160", "429000", "429740", "432840",
    "433330", "437070", "437080", "440340",
    "441640", "441680", "441800", "446720",
    "448100", "448330", "452360", "453330",
    "453850", "455030", "455660", "458260",
    "458730", "458750", "458760", "459580",
    "460660", "460960", "464470", "465670",
    "466940", "468370", "468380", "468630",
    "471460", "472150", "472830", "472870",
    "473330", "474220", "475080", "475380",
    "475720", "476550", "476690", "476750",
    "476760", "476800", "480020", "480030",
    "480040", "480460", "481050", "481060",
    "481340", "482730", "483280", "483290",
    "484790", "484880", "486290", "487950",
    "489030", "489250", "490490", "490590",
    "490600", "491620", "493420", "493810",
    "494210", "494300", "494420", "495040",
    "495050", "495230", "495330", "495850",
    "496080", "497780", "497880", "498400",
    "498410", "498860", "499150", "499660",
    "0000D0", "0004G0", "0005A0", "0008S0",
    "0013P0", "0013R0", "0015E0", "0015F0",
    "0018C0", "0022T0", "0036D0", "0040X0",
    "0040Y0", "0046A0", "0046Y0", "0048J0",
    "0049K0", "0049M0", "0052D0", "0073X0",
    "0080X0", "0084D0", "0084E0", "0085N0",
    "0085P0", "0086B0", "0086C0", "0089C0",
    "0089D0", "0091C0", "0094L0", "0094M0",
    "0097L0", "0098N0", "0104N0", "0104P0",
    "0105E0", "0107F0", "0111J0", "0115C0",
    "0128D0", "0132K0", "0138T0", "0139P0",
    "0144L0", "0152E0", "0153K0", "0153P0",
    "0153X0", "0167B0", "0174J0", "0177R0",
    "0127T0", "0127V0", "0177N0", "0183V0",
    "0176P0", "476850", "0057H0", "0089B0",
]


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
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    # 5년치 데이터
    start = yesterday.replace(year=yesterday.year - 5)

    s = start.strftime("%Y%m%d")
    e = yesterday.strftime("%Y%m%d")

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
