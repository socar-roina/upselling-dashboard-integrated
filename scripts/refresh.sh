#!/bin/bash
# 업셀링 통합 대시보드 v2 자동 갱신: BQ 재집계 → data.js → 검증 → 변경 시 커밋/푸시
# launchd가 매일 11:00, 15:00(KST) 호출. 11시 성공 시 15시는 마커로 스킵.
REPO="/Users/admin/upselling-work/dashboards/upselling-dashboard-integrated-v2"
LOG="$REPO/scripts/refresh.log"
MARKER="$REPO/scripts/.last_success"
TODAY=$(date +%Y-%m-%d)
export PATH="/opt/homebrew/bin:/Users/admin/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export HOME="/Users/admin"
cd "$REPO" || exit 1
if [ "$(cat "$MARKER" 2>/dev/null)" = "$TODAY" ]; then
  echo "$(date '+%F %T') 오늘 이미 갱신됨, 스킵" >> "$LOG"; exit 0
fi
{
  echo "=== $(date '+%F %T') 갱신 시작 ==="
  if ! python3 scripts/gen_data.py --out data.js; then echo "gen_data.py 실패 → 종료"; exit 1; fi
  if ! node -e "global.window={};require('./data.js');const D=window.DASH;if(!(D.total.rsv>0)||!D.meta.cut||!(D.daily.length>0))process.exit(1);console.log('검증 OK 예약'+D.total.rsv+' cut'+D.meta.cut)"; then
    echo "검증 실패 → 커밋 안 함"; exit 1
  fi
  if git diff --quiet data.js; then
    echo "data.js 변경 없음"
  else
    git add data.js
    git commit -q -m "데이터 자동 갱신 (${TODAY})" || { echo "commit 실패"; exit 1; }
    if git push -q origin HEAD; then echo "푸시 완료"; else echo "푸시 실패"; exit 1; fi
  fi
  echo "$TODAY" > "$MARKER"
  echo "=== $(date '+%F %T') 성공 ==="
} >> "$LOG" 2>&1
