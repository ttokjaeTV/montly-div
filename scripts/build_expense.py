# -*- coding: utf-8 -*-
# 실부담비용 스냅샷(실부담비용_YYYY-MM-DD.json) → 트래커 data/expense.json 재생성
# 사용: python build_expense.py <snapshot.json> <tracker_codes_source(holdings.json or index.html)> <out_expense.json> <basis YYYY-MM-DD> <label>
import json, sys, re, os

def load_tracker_codes(src):
    if src.endswith('.json'):  # holdings.json
        return list(json.load(open(src,encoding='utf-8'))['data'].keys())
    # index.html RAW
    h=open(src,encoding='utf-8').read(); s=h.index('const RAW'); e=h.index('\n];',s)
    return [m for m in re.findall(r'\["[^"]*","[^"]*","[^"]*","[^"]*","([0-9A-Z]{6})"', h[s:e])]

def build(snap_path, codes_src, basis, label):
    snap=json.load(open(snap_path,encoding='utf-8'))['data']
    codes=set(load_tracker_codes(codes_src))
    out={}
    skipped=[]
    for c in sorted(codes):
        s=snap.get(c)
        if not s or s.get('상태')!='집계':
            skipped.append(c); continue
        chong = s.get('총보수_kofia'); chong = s.get('총보수_master') if chong is None else chong
        out[c]=[chong, s.get('TER'), s.get('매매수수료'), s.get('실부담비용')]
    meta={"basis":basis,"basisLabel":label,"source":"KOFIA 금융투자협회 전자공시",
          "note":"실부담비용 = TER(총보수+기타비용) + 매매중개수수료. 값 = [총보수, TER, 매매수수료, 실부담비용] (%/년)",
          "count":len(out)}
    return {"meta":meta,"data":out}, skipped

if __name__=='__main__':
    snap, codes_src, basis, label = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    res, skipped = build(snap, codes_src, basis, label)
    print('생성 종목:', len(res['data']), '| 제외(집계전/없음):', len(skipped), skipped[:12])
    if len(sys.argv)>5:
        json.dump(res, open(sys.argv[5],'w',encoding='utf-8'), ensure_ascii=False, separators=(',',':'))
        print('저장:', sys.argv[5])
