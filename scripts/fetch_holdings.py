# -*- coding: utf-8 -*-
"""
구성종목 TOP10 갱신 스크립트 (data/holdings.json)
- 소스: 네이버 모바일 ETF API (m.stock.naver.com/api/etf/{code}/constituent)
- index.html의 RAW 블록에서 종목코드를 읽어 전종목 수집
- 실행: python scripts/fetch_holdings.py  (repo 루트 또는 scripts/에서 실행 가능)
- 데이터 기준일: 네이버 PDF는 보통 전영업일 기준
"""
import json, re, os, sys, datetime
import urllib.request
import concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    start = html.index('const RAW')
    end = html.index('\n];', start)
    codes = [c for c, _ in re.findall(
        r'\["[^"]*","[^"]*","[^"]*","[^"]*","([0-9A-Z]{6})","([^"]+)"', html[start:end])]
    print(f'트래커 종목 수: {len(codes)}')

    def fetch(c):
        req = urllib.request.Request(
            f"https://m.stock.naver.com/api/etf/{c}/constituent",
            headers={"User-Agent": "Mozilla/5.0"})
        try:
            d = json.load(urllib.request.urlopen(req, timeout=12))
            return c, [[r.get('itemName'), r.get('constituentWeight')]
                       for r in d.get('result', [])[:10]]
        except Exception:
            return c, None

    result, fail = {}, []
    with cf.ThreadPoolExecutor(6) as ex:
        for c, top in ex.map(fetch, codes):
            if top: result[c] = top
            else: fail.append(c)
    # 실패분 1회 재시도
    for c in list(fail):
        _, top = fetch(c)
        if top:
            result[c] = top
            fail.remove(c)

    today = datetime.date.today().isoformat()
    out = {"meta": {"source": "네이버 모바일 ETF constituent API",
                    "fetched": today, "count": len(result),
                    "note": "code: [[종목명, 비중%] x 최대10]. 네이버 PDF는 보통 전영업일 기준"},
           "data": dict(sorted(result.items()))}
    path = os.path.join(ROOT, 'data', 'holdings.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'수집 {len(result)} / 실패 {len(fail)} {fail if fail else ""}')
    print(f'저장: {path}')
    if fail:
        sys.exit(1)

if __name__ == '__main__':
    main()
