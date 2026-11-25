#!/usr/bin/env python3
"""자금 — 이 회사의 밸류에이션을 실제로 흔드는 변수.

AI 데이터센터 사업은 매출이 아니라 자금에서 끊긴다. IREN은 2026-09-30 기준
FY2027에 $15B 을 더 써야 한다고 공시했다. 같은 공시에서 조달 계획을 둘로
나눠 적었다.

  확보   $9B   현금 + 약정된 GPU 금융 + 계약된 고객 선급금
  목표   $6B   "subject to market conditions"

이 $6B 이 열려 있는 구멍이다. 주식으로 메우면 희석이고, 차입으로 메우면
이미 $10B 인 차입이 더 늘어난다. 둘 다 주당가치를 깎는다. 그래서 적정가격
계산은 이 구멍을 어떻게 메운다고 보느냐에 가장 민감하다.

위    FY2027 자금 수요와 원천
아래  차입 스택 — 전환사채가 대부분이고, 주가가 전환가에서 멀어지면 그냥 빚이다

데이터 출처: SEC EDGAR 10-Q · Q1 FY27 보도자료

사용 예:
  python funding.py
"""

from __future__ import annotations

import argparse
import re

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import iren_data as idata
import disclosures as disc

B = 1e9

KIND_COLOR = {
    "전환사채": idata.PRICE_COLOR,
    "GPU 담보": idata.CLOUD_COLOR,
    "비소구": idata.LEASE_COLOR,
    "기타": idata.INK_MUTED,
}


def draw(bs, debts, maturities, out_path):
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(12, 8.6), dpi=160,
        gridspec_kw={"height_ratios": [1, 1], "hspace": 0.42})
    fig.patch.set_facecolor(idata.SURFACE)

    # --- 위: 수요 vs 원천 ----------------------------------------------
    idata.style_axes(top)
    need = disc.CAPEX_REMAINING_FY27.value
    cash = bs["cash_total"]
    committed_other = max(disc.FUNDING_COMMITTED.value - cash, 0.0)
    gap = disc.FUNDING_TARGET.value

    top.bar([0], [need / B], width=0.5, color=idata.INK_SECONDARY, zorder=3)
    top.annotate(idata.tex_safe(f"${need/B:,.0f}B"), (0, need / B),
                 xytext=(0, 6), textcoords="offset points", ha="center",
                 fontsize=12, fontweight="bold", color=idata.INK_PRIMARY)

    stack = [("현금·제한현금", cash, idata.LEASE_COLOR),
             ("약정 GPU 금융 + 고객 선급금", committed_other, idata.CLOUD_COLOR),
             ("미확보 — 시장 상황에 달렸다", gap, idata.DEBT_COLOR)]
    base = 0.0
    for name, value, color in stack:
        top.bar([1], [value / B], bottom=[base / B], width=0.5, color=color, zorder=3,
                hatch="///" if color == idata.DEBT_COLOR else None,
                edgecolor="white", linewidth=0)
        top.annotate(idata.tex_safe(f"{name}  ${value/B:,.1f}B"),
                     (1.28, (base + value / 2) / B), fontsize=10,
                     color=idata.INK_PRIMARY, va="center")
        base += value

    top.set_xlim(-0.6, 2.6)
    top.set_xticks([0, 1])
    top.set_xticklabels(["FY2027 남은 CAPEX", "조달 계획"], fontsize=11)
    top.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}B"))
    top.set_title("FY2027 자금 수요와 원천", fontsize=15, color=idata.INK_PRIMARY,
                  fontweight="bold", loc="left", pad=16)
    top.annotate(idata.tex_safe(
        f"기준 {disc.PERIOD_END} · 분기 영업현금흐름으로는 못 메운다 "
        f"(Q1 FY27 영업현금흐름 $0.5B)"),
        (0.0, 1.03), xycoords="axes fraction", fontsize=9.5, color=idata.INK_MUTED)

    # --- 아래: 차입 스택 -------------------------------------------------
    idata.style_axes(bottom)
    bottom.grid(axis="y", visible=False)
    bottom.grid(axis="x", color=idata.GRID, linewidth=0.8, zorder=0)

    order = sorted(debts, key=lambda d: (list(KIND_COLOR).index(d.kind), -d.principal))
    names = [d.name for d in order]
    ys = list(range(len(order)))[::-1]
    bottom.barh(ys, [d.principal / B for d in order], height=0.62,
                color=[KIND_COLOR[d.kind] for d in order], zorder=3)
    for y, d in zip(ys, order):
        rate = f"{d.rate:.2f}%" if d.rate else "—"
        bottom.annotate(idata.tex_safe(f"${d.principal/B:,.2f}B · 실효 {rate}"),
                        (d.principal / B, y), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=9,
                        color=idata.INK_SECONDARY)
    bottom.set_yticks(ys)
    bottom.set_yticklabels(names, fontsize=9.5)
    bottom.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.1f}B"))
    bottom.set_xlim(0, max(d.principal for d in order) / B * 1.32)

    total = sum(d.principal for d in debts)
    by_kind: dict[str, float] = {}
    for d in debts:
        by_kind[d.kind] = by_kind.get(d.kind, 0.0) + d.principal
    legend = " · ".join(f"{k} ${v/B:,.1f}B ({v/total*100:.0f}%)"
                        for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1]))
    bottom.set_title(idata.tex_safe(f"차입 스택 ${total/B:,.1f}B — {bs['as_of']}"),
                     fontsize=15, color=idata.INK_PRIMARY, fontweight="bold",
                     loc="left", pad=16)
    bottom.annotate(idata.tex_safe(legend), (0.0, 1.03), xycoords="axes fraction",
                    fontsize=9.5, color=idata.INK_MUTED)

    wall = {k: v for k, v in maturities.items() if k != "Total"}
    near = sum(v for k, v in wall.items() if re.search(r"Remainder|2028|2029", k))
    bottom.annotate(idata.tex_safe(
        f"FY2029까지 상환 예정 ${near/B:,.1f}B · 나머지 ${(total-near)/B:,.1f}B 는 FY2030 이후. "
        f"순차입 ${bs['net_debt']/B:,.1f}B (현금 ${bs['cash_total']/B:,.1f}B 차감 후)"),
        xy=(0.0, -0.17), xycoords="axes fraction", fontsize=9.5,
        color=idata.INK_SECONDARY)

    fig.text(0.5, 0.012,
             "출처: SEC EDGAR 10-Q 차입 주석 · Q1 FY27 보도자료 (각주 11·12)",
             ha="center", fontsize=8.5, color=idata.INK_MUTED)
    fig.subplots_adjust(top=0.91, bottom=0.10, left=0.17, right=0.975)
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "funding.png"))
    args = ap.parse_args()

    bs = idata.balance_sheet(args.refresh)
    _, debts = idata.debt_stack(args.refresh)
    maturities = idata.debt_maturities(args.refresh)
    draw(bs, debts, maturities, args.out)

    print(f"\n재무상태 ({bs['as_of']})")
    for key, name in (("cash_total", "현금 + 제한현금"), ("debt_total", "차입 + 금융리스"),
                      ("net_debt", "순차입"), ("equity", "자기자본"),
                      ("ppe", "유형자산"), ("total_assets", "총자산")):
        print(f"  {name:16} ${bs[key]/B:7.2f}B")
    print(f"\nFY2027 자금")
    print(f"  남은 CAPEX       ${disc.CAPEX_REMAINING_FY27.value/B:7.2f}B")
    print(f"  확보             ${disc.FUNDING_COMMITTED.value/B:7.2f}B")
    print(f"  미확보           ${disc.FUNDING_TARGET.value/B:7.2f}B")
    print(f"\n만기 분포")
    for k, v in maturities.items():
        print(f"  {k:34} ${v/B:6.2f}B")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
