#!/usr/bin/env python3
"""SNAPSHOT.md — 지금 상태를 한 장으로.

README는 왜 그렇게 보는지를 적는 곳이고, 여기는 오늘 숫자만 적는 곳이다.
자동 생성되므로 손으로 고치지 않는다.

사용 예:
  python snapshot.py
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import iren_data as idata
import disclosures as disc
import valuation as val

B = 1e9
M = 1e6


def build(refresh: bool = False) -> str:
    revenue = idata.quarterly_revenue(refresh)
    bl = idata.backlog(refresh)
    bs = idata.balance_sheet(refresh)
    price_date, price = idata.latest(idata.price(refresh))
    shares_date, shares = idata.shares_outstanding(refresh)[-1]
    dil = idata.dilution(refresh)
    _, debts = idata.debt_stack(refresh)

    conv_principal = sum(d.principal for d in debts if d.kind == "전환사채")
    conv_shares = dil.get("Convertible notes", 0.0)
    converts = (conv_principal, conv_shares)
    results = [val.evaluate(s, bs["net_debt"], shares, price, converts,
                                bs["ppe"])
               for s in val.scenarios()]
    band = sorted(max(r.per_share, 0) for r in results)
    fair = val.fair_value(results)
    implied = val.implied_downside(results, price)

    q = revenue[-1]
    ttm = sum(r.total for r in revenue[-4:])
    cap = price * shares
    ev = cap + bs["net_debt"]
    commenced = bl.lease_payments.get("Total", 0.0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = [
        "# 스냅샷", "", f"자동 생성 — {now}", "",
        f"## 매출 ({idata.label(q.quarter)}, {q.end})", "", "| | |", "|---|---|",
        f"| 총매출 | ${q.total/M:,.0f}M |",
        f"| AI 클라우드 | ${(q.ai_cloud or 0)/M:,.0f}M "
        f"({(q.ai_cloud or 0)/q.total*100:,.0f}%) |",
    ]
    if q.ai_services and q.ai_lease:
        rows += [f"| — 서비스 (ASC 606) | ${q.ai_services/M:,.0f}M |",
                 f"| — 임대 (ASC 842) | ${q.ai_lease/M:,.0f}M |"]
    rows += [
        f"| 비트코인 채굴 | ${(q.mining or 0)/M:,.0f}M |",
        f"| 직전 4개 분기 | ${ttm/B:,.2f}B |",
        "",
        "## 수주잔고와 ARR", "", "| | |", "|---|---|",
        f"| 수주잔고 | ${bl.total/B:,.1f}B ({bl.as_of}) |",
        f"| — ASC 606 잔여 수행의무 | ${bl.rpo/B:,.2f}B |",
        f"| — 개시된 임대 최소 수취액 | ${commenced/B:,.2f}B |",
        f"| — 개시 전 임대 | ${(bl.leases - commenced)/B:,.2f}B |",
        f"| 가동 ARR | 약 ${disc.ARR_OPERATING.value/B:,.0f}B |",
        f"| 목표 ARR | ${disc.ARR_TARGET.value/B:,.0f}B "
        f"({disc.ARR_TARGET_DATE} 목표) |",
        "",
        f"## 재무상태 ({bs['as_of']})", "", "| | |", "|---|---|",
        f"| 현금 + 제한현금 | ${bs['cash_total']/B:,.2f}B |",
        f"| 차입 + 금융리스 | ${bs['debt_total']/B:,.2f}B |",
        f"| — 전환사채 | ${conv_principal/B:,.2f}B |",
        f"| 순차입 | ${bs['net_debt']/B:,.2f}B |",
        f"| 남은 FY2027 CAPEX | ${disc.CAPEX_REMAINING_FY27.value/B:,.0f}B |",
        f"| — 미확보 | ${disc.FUNDING_TARGET.value/B:,.0f}B |",
        "",
        "## 주가", "", "| | |", "|---|---|",
        f"| IREN | ${price:,.2f} ({price_date}) |",
        f"| 주식수 | {shares/M:,.1f}M ({shares_date}) |",
        f"| 시가총액 | ${cap/B:,.2f}B |",
        f"| EV | ${ev/B:,.2f}B |",
        f"| EV / 가동 ARR | {ev/disc.ARR_OPERATING.value:,.1f}x |",
        f"| EV / 목표 ARR | {ev/disc.ARR_TARGET.value:,.1f}x |",
        f"| EV / 수주잔고 | {ev/bl.total:,.2f}x |",
        f"| 평균 전환가 | ${conv_principal/conv_shares:,.0f} "
        f"(희석 {conv_shares/M:,.0f}M주) |",
        f"| **적정가격** | **${fair:,.2f}** ({fair/price - 1:+.0%}) |",
        f"| 주당가치 범위 | ${band[0]:,.0f} ~ ${band[-1]:,.0f} "
        f"(확률 {' / '.join(f'{r.scenario.prob*100:,.0f}%' for r in results)}) |",
        f"| 주가가 함의하는 '목표 미달' 확률 | {implied*100:,.0f}% |"
        if implied == implied else "",
        "",
        "숫자의 근거와 한계는 [README](README.md) 참조. 투자 판단이나 권유가 아니다.",
        "",
    ]
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(idata.ROOT / "SNAPSHOT.md"))
    args = ap.parse_args()
    text = build(args.refresh)
    with open(args.out, "w") as fh:
        fh.write(text)
    print(text)
    print(f"저장 {args.out}")


if __name__ == "__main__":
    main()
