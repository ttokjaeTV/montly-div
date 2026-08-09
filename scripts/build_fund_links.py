# -*- coding: utf-8 -*-
"""
data/fund-links.json 생성 스크립트

etf-selector repo의 두 파일을 읽어 트래커 종목별 '운용사 공식 페이지' 링크를
미리 해석(pre-resolve)해 단축코드 -> [url, label] 평면 맵으로 저장한다.

  1) etf-selector/data/amc_links.json      : 단축코드 -> 공식 상세 URL (825종, 최우선)
  2) etf-selector/data/krx_etf_master.json : ticker/isin/fundHouse/brand (1160종)

이렇게 사전 해석해 두면 트래커 RAW 데이터에 isin·fundHouse 컬럼을 추가할 필요가 없다.
(트래커 RAW 헤더에는 code/nm만 있고 isin·fundHouse가 없음)

사용법:
    python scripts/build_fund_links.py
    python scripts/build_fund_links.py --selector ../etf-selector
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

# 운용사별 공식 페이지 규칙 (etf-selector/index.html의 __AMC_LINK와 동일)
#   isin   : 표준코드 딥링크 / ticker : 단축코드 딥링크 / home : 공식 ETF 사이트
AMC_LINK = {
    "미래에셋자산운용":       ("isin",   "TIGER",  "https://investments.miraeasset.com/tigeretf/ko/product/search/detail/index.do?ksdFund="),
    "키움투자자산운용":       ("ticker", "KIWOOM", "https://www.kiwoometf.com/service/etf/KO02010200M?gcode="),
    "삼성자산운용":           ("home",   "KODEX",  "https://www.samsungfund.com/etf/main.do"),
    "케이비자산운용":         ("home",   "RISE",   "https://www.riseetf.co.kr/prod/finder"),
    "한국투자신탁운용":       ("home",   "ACE",    "https://www.aceetf.co.kr/fund"),
    "한화자산운용":           ("home",   "PLUS",   "https://www.plusetf.co.kr/product/find"),
    "신한자산운용":           ("home",   "SOL",    "https://www.soletf.com/"),
    "엔에이치아문디자산운용": ("home",   "HANARO", "https://www.hanaroetf.com/"),
    "우리자산운용":           ("home",   "WON",    "https://www.wooriam.kr/investment/etf-list"),
    "하나자산운용":           ("home",   "1Q",     "https://1qetf.com/"),
}

NAVER = "https://finance.naver.com/item/main.naver?code="


def read_tracker_codes(index_html: Path):
    """index.html의 const RAW 배열에서 (단축코드, 종목명)을 추출한다."""
    src = index_html.read_text(encoding="utf-8")
    start = src.index("const RAW = [")
    end = src.index("\n];", start)
    body = src[start:end]
    rows = re.findall(r'\[\s*"([^"]*)","([^"]*)","([^"]*)","([^"]*)","([^"]*)","([^"]*)"', body)
    # HEADERS = [c1, c2, c3, c4, code, nm, ...] -> 5번째가 code, 6번째가 nm
    return [(r[4], r[5]) for r in rows]


def resolve(code, amc_links, master):
    """단축코드 하나를 [url, label]로 해석한다."""
    # 1) 종목별 정확 딥링크 우선 (amc_links.json)
    if code in amc_links:
        brand = (master.get(code) or {}).get("brand") or "운용사"
        return [amc_links[code], f"{brand} 공식 상세"], "deep_json"

    m = master.get(code)
    cfg = AMC_LINK.get(m.get("fundHouse")) if m else None
    if cfg:
        kind, name, url = cfg
        if kind == "isin" and m.get("isin"):
            return [url + m["isin"], f"{name} 공식 상세"], "deep_isin"
        if kind == "ticker":
            return [url + code, f"{name} 공식 상세"], "deep_ticker"
        return [url, f"{name} 공식 사이트"], "home"

    # 2) 규칙에 없는 운용사 -> 네이버 종목정보 폴백
    return [NAVER + code, "종목 정보 (네이버)"], "naver"


def main():
    root = Path(__file__).resolve().parent.parent

    ap = argparse.ArgumentParser()
    ap.add_argument("--selector", default=str(root.parent / "etf-selector"),
                    help="etf-selector repo 경로 (기본: ../etf-selector)")
    args = ap.parse_args()

    sel = Path(args.selector)
    amc_raw = json.loads((sel / "data" / "amc_links.json").read_text(encoding="utf-8"))
    amc_links = amc_raw.get("links", {})
    master = {e["ticker"]: e for e in json.loads(
        (sel / "data" / "krx_etf_master.json").read_text(encoding="utf-8"))["etfs"]}

    tracker = read_tracker_codes(root / "index.html")

    data = {}
    stat = {"deep_json": 0, "deep_isin": 0, "deep_ticker": 0, "home": 0, "naver": 0}
    fallback = []
    for code, nm in tracker:
        link, kind = resolve(code, amc_links, master)
        data[code] = link
        stat[kind] += 1
        if kind == "naver":
            fallback.append(f"{code} {nm}")

    deep = stat["deep_json"] + stat["deep_isin"] + stat["deep_ticker"]
    out = {
        "meta": {
            "source": "etf-selector/data/amc_links.json + krx_etf_master.json",
            "generated": date.today().isoformat(),
            "amcLinksUpdated": amc_raw.get("meta", {}).get("updated", ""),
            "krxDataDate": json.loads((sel / "data" / "krx_etf_master.json")
                                      .read_text(encoding="utf-8"))["meta"].get("dataDate", ""),
            "total": len(data),
            "deepLink": deep,
            "deepLinkRate": round(deep / len(data) * 100, 1),
            "breakdown": stat,
            "note": "단축코드 -> [공식 페이지 URL, 버튼 라벨]. 사전 해석 완료 — 트래커는 code만 있으면 됨",
        },
        "data": data,
    }

    dest = root / "data" / "fund-links.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")

    print(f"저장: {dest}")
    print(f"총 {len(data)}종 / 딥링크 {deep}종 ({out['meta']['deepLinkRate']}%)")
    print(f"세부: {stat}")
    if fallback:
        print("네이버 폴백:")
        for f in fallback:
            print("  -", f)


if __name__ == "__main__":
    main()
