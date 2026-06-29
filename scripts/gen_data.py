#!/usr/bin/env python3
"""업셀링 통합 대시보드 데이터 생성기 (결정형).
bq CLI로 BigQuery를 집계해 일별 통합 퍼널을 data.js로 출력한다.
사람이 손으로 숫자를 고치지 않아 정합성/누락/표현 변동이 구조적으로 없다.

대상: 결제 직전 바텀시트 업셀링 3종(PF 보험, 시간연장, 차종)을 합친 통합 퍼널.
(부가서비스는 이 바텀시트 아이템이 아니므로 제외.)

usage: python3 gen_data.py [--start 'YYYY-MM-DD HH:MM:SS'] [--cut YYYY-MM-DD] [--out data.js]
  --start 통합 집계 시작(정규화 시작 시각). 기본 '2026-05-21 14:00:00'.
  --cut   집계 종료일(포함). 기본 = 어제 KST (이벤트/결제 D+1 적재 때문).
"""
import argparse, json, subprocess, sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
BQ_PROJECT = "socar-data"


def bq(sql):
    cmd = ["bq", "query", f"--project_id={BQ_PROJECT}", "--nouse_legacy_sql",
           "--format=json", "--max_rows=100000", sql]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(f"[bq error]\n{p.stderr}\n")
        raise SystemExit(2)
    return json.loads(p.stdout or "[]")


def i(x):
    return int(float(x)) if x not in (None, "") else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-05-21 14:00:00")
    ap.add_argument("--cut", default=None)
    ap.add_argument("--out", default="data.js")
    a = ap.parse_args()
    cut = a.cut or (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")
    start_dt = a.start
    start_day = start_dt.split(" ")[0]
    end_dt = (datetime.strptime(cut, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00"

    # 일별 통합 퍼널: 전체 예약 / 노출(예약 회원이 그날 바텀시트 view) / 수락(노출 & PF0 결제전환)
    rows = bq(f"""
WITH v AS (
  SELECT DISTINCT DATE(event_at_kst) AS d, member_id
  FROM `socar-data.app_web_log.socar_app_web_log`
  WHERE page_name='upsell_bottomsheet' AND event_name='view'
    AND event_at_kst >= DATETIME '{start_dt}'
    AND event_at_kst <  DATETIME '{end_dt}'
),
r AS (
  SELECT DATE(created_at_kst) AS d, member_id, CAST(pf_type AS STRING) AS pf_type
  FROM `socar-data.socar_biz_profit.profit_socar_reservation`
  WHERE created_at_kst >= DATETIME '{start_dt}'
    AND created_at_kst <  DATETIME '{end_dt}'
)
SELECT FORMAT_DATE('%Y-%m-%d', r.d) AS dt,
  COUNT(*) AS rsv,
  COUNTIF(v.member_id IS NOT NULL) AS exp,
  COUNTIF(v.member_id IS NOT NULL AND r.pf_type='0') AS acc
FROM r LEFT JOIN v ON r.d=v.d AND r.member_id=v.member_id
GROUP BY 1 ORDER BY 1""")

    by = {r["dt"]: r for r in rows}
    d0 = datetime.strptime(start_day, "%Y-%m-%d").date()
    dN = datetime.strptime(cut, "%Y-%m-%d").date()
    days = [(d0 + timedelta(days=k)).strftime("%Y-%m-%d") for k in range((dN - d0).days + 1)]
    daily = [{"dt": d,
              "rsv": i(by.get(d, {}).get("rsv")),
              "exp": i(by.get(d, {}).get("exp")),
              "acc": i(by.get(d, {}).get("acc"))} for d in days]

    tot_rsv = sum(x["rsv"] for x in daily)
    tot_exp = sum(x["exp"] for x in daily)
    tot_acc = sum(x["acc"] for x in daily)

    D = {
        "meta": {"start": start_day, "cut": cut,
                 "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")},
        "daily": daily,
        "total": {"rsv": tot_rsv, "exp": tot_exp, "acc": tot_acc},
    }

    with open(a.out, "w") as fp:
        fp.write("window.DASH = " + json.dumps(D, ensure_ascii=False) + ";\n")
    print(f"wrote {a.out} (cut={cut}) 예약 {tot_rsv:,} / 노출 {tot_exp:,} / 수락 {tot_acc:,}")


if __name__ == "__main__":
    main()
