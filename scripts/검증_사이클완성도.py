# -*- coding: utf-8 -*-
# 월배당 트래커 — 커밋 전 사이클 완성도 점검
# 사용: cd github/montly-div && python3 scripts/검증_사이클완성도.py
# index.html의 curKey/헤더를 '이번 사이클'로 보고, 각 데이터 파일이 이번 사이클로 갱신됐는지 ✅/❌ 출력.
# 특히 '과표(이번 사이클)'가 미갱신이면 ❌로 크게 표시 — 2026/07 월중에 과표 누락 재발 방지용.
import json, re, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # repo root
def rp(*a): return os.path.join(ROOT, *a)

h = open(rp("index.html"), encoding="utf-8").read()

# ── 이번 사이클 마커 (index.html = 기준) ──
curKey = (re.search(r'const curKey\s*=\s*"([^"]+)"', h) or [None, "?"])[1]
hdr = (re.search(r'//\s*PRICE_UPDATES[^\n]*', h) or [""])[0]
cyc = "월중" if "월중" in hdr else ("월말" if "월말" in hdr else "?")
hdrdate = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})\s*갱신', hdr)
macros = re.findall(r'"(\d{4}-\d{2}-\d{2})":\s*\[', h)
macro_latest = max(macros) if macros else None
# curKey "26-7" → "2026/07"
yy, nn = curKey.split("-")
cyc_prefix = f"20{yy}/{int(nn):02d}"

# ── RAW에서 월중/월말 코드 그룹 ──
s = h.index("const RAW"); e = h.index("\n];", s); raw = h[s:e]
rows = re.findall(r'\[((?:"[^"]*"|null|\{\}|[^\[\]])*?)\]', raw)
groups = {"월중": [], "월말": []}
for row in rows:
    p = re.findall(r'"([^"]*)"', row)
    if len(p) >= 8 and p[7] in groups:
        groups[p[7]].append(p[4])

def load(f): return json.load(open(rp("data", f), encoding="utf-8"))
tb = load("tax-base.json"); tbx = load("tax-base-extra.json")
alltb = {**tb["data"], **tbx["data"]}
exp = load("expense.json"); hold = load("holdings.json")

def top_date(code):
    r = alltb.get(code)
    return r[0][0] if r and r[0] else None

def group_latest(codes):
    c = Counter(top_date(x) for x in codes if top_date(x))
    return c.most_common(1)[0] if c else (None, 0)

mz = group_latest(groups["월중"]); me = group_latest(groups["월말"])
active_latest = mz[0] if cyc == "월중" else me[0]
tax_ok = bool(active_latest and active_latest.startswith(cyc_prefix))

print("=" * 60)
print(f"이번 사이클 (index.html 기준): {cyc}  |  curKey={curKey}  |  헤더 {hdrdate.group(0) if hdrdate else '?'}")
print("=" * 60)
def mark(ok): return "✅" if ok else "❌"

# index.html 자체
idx_ok = bool(hdrdate) and curKey and macro_latest
print(f"{mark(idx_ok)} index.html      : curKey {curKey} / 헤더 {cyc} {'/'.join(hdrdate.groups()) if hdrdate else '?'} / MACRO 최신 {macro_latest}")
# holdings
hf = hold["meta"].get("fetched")
print(f"{mark(bool(hf))} holdings.json   : meta.fetched = {hf}")
# 과표 (핵심)
print(f"{mark(tax_ok)} tax-base 과표   : 이번({cyc}) 최신 배당락일 = {active_latest}  → " + ("이번 사이클 반영됨" if tax_ok else "❌❌ 미갱신! 과표 수집(ETF CHECK D+1) 아직 안 됨"))
print(f"     ├ 월중 과표 최신: {mz[0]} ({mz[1]}종)   ├ 월말 과표 최신: {me[0]} ({me[1]}종)")
print(f"     └ tax-base _meta lastCycle={tb['_meta'].get('lastCycle')} / lastUpdate={tb['_meta'].get('lastUpdate')}")
# expense (KOFIA 시차 정상)
print(f"ℹ expense.json    : KOFIA {exp['meta'].get('basisLabel')} (basis {exp['meta'].get('basis')}) — KOFIA는 ~1개월 시차라 사이클과 달라도 정상. 새 월말분 뜨면 갱신")

print("-" * 60)
if tax_ok:
    print("→ 모든 사이클 데이터 반영됨. 커밋 진행 가능.")
else:
    print("→ ❌ 과표가 이번 사이클로 갱신 안 됨. 커밋 전에 ETF CHECK 과표 수집 필요 (bulk_fetch 아님, Claude-in-Chrome 5탭 병렬).")
print("=" * 60)
