#!/usr/bin/env python3
"""적정가격 — 단일 숫자 대신 범위와, 현재 주가가 함의하는 가정.

이 회사는 지금 손실을 내고 있고, 매출은 두 분기 만에 성격이 바뀌었다. 과거
실적 배수로는 아무것도 재지 못한다. 쓸 수 있는 닻은 하나뿐이다 — 회사가
"계약됐고 자금도 마련됐다"고 공시한 **$4B ARR**, 그리고 거기 도달하는 데
필요한 **$15B CAPEX**.

그래서 계산을 이렇게 둔다.

  EBITDA      = 달성 ARR x 매출총이익률 − 현금 영업비용
  순차입(완공) = 현재 순차입 + 남은 CAPEX − 고객 선급금 − 증자
  자기자본     = EBITDA x 배수 − 순차입(완공)
  주당가치     = 자기자본 / (현재 주식수 + 증자 주식수 + 베스팅)

배수·마진·조달 구성이 가정이고, 나머지는 공시 숫자다. 가정이 결과를 지배하므로
단일 적정주가를 내지 않고 시나리오 범위를 낸다.

전환사채는 부채로 둔다. 원금 $6.7B 에 희석 주식수 1.27억주를 맞추면 평균
전환가가 나오는데, 현재 주가는 그보다 한참 아래다. 주가가 거기까지 오르면
그때는 주식이 되므로, 상단 시나리오에서는 희석을 같이 반영해야 한다.
그 지점을 차트에 표시한다.

위    시나리오별 주당가치 vs 현재 주가
아래  달성 ARR x 배수 평면 — 현재 주가가 함의하는 조합

데이터 출처: SEC EDGAR · Yahoo Finance · Q1 FY27 보도자료

사용 예:
  python valuation.py
  python valuation.py --multiples 6,9,12
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import iren_data as idata
import disclosures as disc

B = 1e9

# 현금 영업비용은 ARR과 같이 늘지만 비례하지는 않는다. Q1 FY27 실적 $118M 에
# 회사가 가이던스로 준 다음 분기 증가폭을 더해 연율화하면 약 $0.7B 이고,
# 그게 $4B ARR 구간의 기준점이다. 그 위로는 ARR의 일정 비율로 늘린다고 본다.
OPEX_AT_TARGET = (disc.CASH_OPEX[(2027, 1)] + sum(disc.CASH_OPEX_GUIDE_NEXT) / 2) * 4
OPEX_SLOPE = 0.06   # 목표 ARR을 넘는 매출 1달러당 추가 현금비용

VEST_SHARES = 36.8e6   # 스톡옵션 + RSU. 전환사채는 따로 다룬다


@dataclass(frozen=True)
class Scenario:
    name: str
    arr: float            # 달성 ARR
    margin: float         # 매출총이익률 (매출원가 제외, 감가상각 전)
    multiple: float       # EV / EBITDA
    capex: float          # 여기까지 가는 데 더 쓰는 CAPEX
    prepay_share: float   # 그 CAPEX 중 고객 선급금이 덮는 비율
    equity_raise: float   # 증자 금액
    color: str
    note: str


def scenarios() -> list[Scenario]:
    """세 가지 결말. 가정은 전부 여기 적혀 있다."""
    return [
        Scenario("보수 — 목표 미달", 2.5e9, 0.78, 7.0, 10.0e9, 0.15, 0.0,
                 idata.DEBT_COLOR,
                 "$15B 중 $10B 을 쓴 채로 자금이 끊겨 ARR은 $2.5B 에서 멈춘다.\n"
                 "마진은 코로케이션 비중이 늘며 하락, 부족분은 전부 차입"),
        Scenario("기준 — 회사 목표 달성", disc.ARR_TARGET.value,
                 disc.AI_CLOUD_GROSS_MARGIN.value, 10.0,
                 disc.CAPEX_REMAINING_FY27.value, 0.30, 2.0e9,
                 idata.CLOUD_COLOR,
                 "공시한 $4B ARR 을 공시한 $15B CAPEX 로 달성.\n"
                 "현재 마진 유지, 부족분 중 $2B 는 증자"),
        Scenario("낙관 — 0.8GW 절반까지", 6.0e9,
                 disc.AI_CLOUD_GROSS_MARGIN.value, 13.0, 22.0e9, 0.40, 2.0e9,
                 idata.LEASE_COLOR,
                 "CY2027 목표 용량의 절반이 추가로 계약·가동.\n"
                 "자본집약도는 목표 구간과 같게 두고 배수만 프리미엄"),
    ]


@dataclass
class Result:
    scenario: Scenario
    ebitda: float
    net_debt: float
    enterprise: float
    equity: float
    shares: float
    per_share: float
    converts_dilute: bool


def evaluate(s: Scenario, net_debt_now: float, shares_now: float,
             price: float, converts: tuple[float, float]) -> Result:
    opex = OPEX_AT_TARGET + max(s.arr - disc.ARR_TARGET.value, 0) * OPEX_SLOPE
    ebitda = s.arr * s.margin - opex

    net_debt = net_debt_now + s.capex * (1 - s.prepay_share) - s.equity_raise

    # 증자는 오늘 주가로 한다고 본다. 주가가 낮을수록 같은 금액에 더 많이 희석된다 —
    # 이 되먹임이 자금 부족 상태의 주식이 비싸 보이지 않는 이유다.
    shares = shares_now + VEST_SHARES + (s.equity_raise / price if price else 0)

    principal, conv_shares = converts
    enterprise = ebitda * s.multiple
    equity = enterprise - net_debt
    per_share = equity / shares if shares else 0.0

    # 전환사채는 주가가 평균 전환가를 넘으면 주식이 된다. 넘는 시나리오에서는
    # 원금을 부채에서 빼고 주식수를 늘려 다시 푼다.
    conv_price = principal / conv_shares if conv_shares else float("inf")
    dilute = per_share > conv_price
    if dilute:
        equity = enterprise - (net_debt - principal)
        shares += conv_shares
        per_share = equity / shares

    return Result(s, ebitda, net_debt, enterprise, equity, shares, per_share, dilute)


def per_share_curve(arrs, multiple, base: Scenario, net_debt_now, shares_now,
                    price, converts):
    out = []
    for arr in arrs:
        # 곡선 위에서는 CAPEX가 ARR과 같이 움직인다. 자본집약도(ARR 1달러당
        # CAPEX)를 기준 시나리오 값으로 고정해, 적게 벌면 적게 썼다고 본다.
        capex = base.capex * arr / base.arr
        s = Scenario(base.name, arr, base.margin, multiple, capex,
                     base.prepay_share, base.equity_raise, base.color, "")
        out.append(evaluate(s, net_debt_now, shares_now, price, converts).per_share)
    return out


def draw(results, price, price_date, net_debt_now, shares_now, converts,
         multiples, out_path):
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(12, 9.4), dpi=160,
        gridspec_kw={"height_ratios": [1, 1.1], "hspace": 0.62})
    fig.patch.set_facecolor(idata.SURFACE)

    # --- 위: 시나리오 ----------------------------------------------------
    idata.style_axes(top)
    xs = list(range(len(results)))
    tops = [max(r.per_share, 0) for r in results]
    top.bar(xs, tops, width=0.5, color=[r.scenario.color for r in results], zorder=3)
    for x, r in zip(xs, results):
        shown = (f"${r.per_share:,.0f}" if r.per_share > 0
                 else f"$0  (계산상 -${abs(r.per_share):,.0f})")
        top.annotate(idata.tex_safe(shown),
                     (x, max(r.per_share, 0)), xytext=(0, 7),
                     textcoords="offset points", ha="center", fontsize=13,
                     fontweight="bold", color=idata.INK_PRIMARY)
        top.annotate(idata.tex_safe(
            f"ARR ${r.scenario.arr/B:,.1f}B · 배수 {r.scenario.multiple:,.1f}x\n"
            f"EBITDA ${r.ebitda/B:,.2f}B · 완공 순차입 ${r.net_debt/B:,.1f}B\n"
            f"CAPEX ${r.scenario.capex/B:,.0f}B · 0이 되는 배수 "
            f"{r.net_debt/r.ebitda:,.1f}x"
            + ("\n전환사채 주식 전환 반영" if r.converts_dilute else "")),
            (x, 0), xytext=(0, -52), textcoords="offset points", ha="center",
            fontsize=9, color=idata.INK_SECONDARY, annotation_clip=False)

    top.axhline(price, color=idata.PRICE_COLOR, linewidth=1.6, linestyle="--", zorder=4)
    top.annotate(idata.tex_safe(f"현재 주가 ${price:,.2f} ({price_date})"),
                 (len(results) - 0.45, price), xytext=(6, 4),
                 textcoords="offset points", fontsize=10, color=idata.PRICE_COLOR,
                 fontweight="bold")

    top.set_xticks(xs)
    top.set_xticklabels([r.scenario.name for r in results], fontsize=11)
    top.tick_params(axis="x", pad=64)
    top.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    top.set_title("시나리오별 주당가치", fontsize=15, color=idata.INK_PRIMARY,
                  fontweight="bold", loc="left", pad=16)
    top.annotate("완공 시점 기준. 할인하지 않은 값이다 — 도달까지의 시간과 "
                 "실행 위험은 배수 가정에 들어 있다고 본다",
                 (0.0, 1.03), xycoords="axes fraction", fontsize=9.5,
                 color=idata.INK_MUTED)

    # --- 아래: ARR x 배수 평면 -------------------------------------------
    idata.style_axes(bottom)
    base = results[1].scenario
    arrs = [x * 1e8 for x in range(10, 71)]   # $1.0B ~ $7.0B
    for multiple, dash in zip(multiples, [(1, 0), (5, 2), (2, 2)]):
        ys = per_share_curve(arrs, multiple, base, net_debt_now, shares_now,
                             price, converts)
        line, = bottom.plot([a / B for a in arrs], ys, linewidth=2.0,
                            color=idata.CLOUD_COLOR, zorder=3)
        line.set_dashes(dash)
        last_visible = max((i for i, y in enumerate(ys) if y < 100), default=len(ys) - 1)
        bottom.annotate(f"{multiple:,.0f}x", (arrs[last_visible] / B, ys[last_visible]),
                        xytext=(6, -2), textcoords="offset points", fontsize=10,
                        color=idata.CLOUD_COLOR, fontweight="bold")

    bottom.axhline(price, color=idata.PRICE_COLOR, linewidth=1.6, linestyle="--", zorder=4)
    bottom.annotate(idata.tex_safe(f"현재 주가 ${price:,.2f}"), (1.05, price),
                    xytext=(0, 6), textcoords="offset points", fontsize=10,
                    color=idata.PRICE_COLOR, fontweight="bold")
    bottom.axvline(disc.ARR_TARGET.value / B, color=idata.INK_MUTED,
                   linewidth=1.0, linestyle=":", zorder=2)
    bottom.annotate(idata.tex_safe(f"회사 목표 ${disc.ARR_TARGET.value/B:,.0f}B"),
                    (disc.ARR_TARGET.value / B, 0), xytext=(6, 8),
                    textcoords="offset points", fontsize=9.5, color=idata.INK_SECONDARY)
    bottom.axvline(disc.ARR_OPERATING.value / B, color=idata.INK_MUTED,
                   linewidth=1.0, linestyle=":", zorder=2)
    bottom.annotate(idata.tex_safe(f"현재 가동 ${disc.ARR_OPERATING.value/B:,.0f}B"),
                    (disc.ARR_OPERATING.value / B, 0), xytext=(6, 8),
                    textcoords="offset points", fontsize=9.5, color=idata.INK_SECONDARY)

    bottom.set_xlim(1.0, 7.0)
    bottom.set_ylim(0, 100)
    bottom.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}B"))
    bottom.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    bottom.set_xlabel("달성 ARR", fontsize=10, color=idata.INK_SECONDARY)
    bottom.set_title("달성 ARR과 배수가 만드는 주당가치", fontsize=15,
                     color=idata.INK_PRIMARY, fontweight="bold", loc="left", pad=16)
    bottom.annotate(idata.tex_safe(
        "다른 가정은 기준 시나리오와 같다 — 마진 "
        f"{base.margin*100:,.0f}%, 선급금이 CAPEX의 {base.prepay_share*100:,.0f}%, "
        f"증자 ${base.equity_raise/B:,.0f}B, 자본집약도 ARR 1달러당 "
        f"${base.capex/base.arr:,.2f}. 곡선이 살짝 꺾이는 지점이 전환사채가 "
        "주식이 되는 구간이다"),
        (0.0, 1.03), xycoords="axes fraction", fontsize=9.5, color=idata.INK_MUTED)

    fig.text(0.5, 0.012,
             "출처: SEC EDGAR 10-Q · Yahoo Finance · Q1 FY27 보도자료    "
             "투자 판단이나 권유가 아니다",
             ha="center", fontsize=8.5, color=idata.INK_MUTED)
    fig.subplots_adjust(top=0.91, bottom=0.085, left=0.075, right=0.965)
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--multiples", default="7,10,13",
                    help="아래 패널에 그릴 EV/EBITDA 배수")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "valuation.png"))
    args = ap.parse_args()

    bs = idata.balance_sheet(args.refresh)
    price_date, price = idata.latest(idata.price(args.refresh))
    shares_date, shares_now = idata.shares_outstanding(args.refresh)[-1]
    dil = idata.dilution(args.refresh)
    _, debts = idata.debt_stack(args.refresh)

    conv_principal = sum(d.principal for d in debts if d.kind == "전환사채")
    conv_shares = dil.get("Convertible notes", 0.0)
    converts = (conv_principal, conv_shares)

    results = [evaluate(s, bs["net_debt"], shares_now, price, converts)
               for s in scenarios()]
    multiples = [float(x) for x in args.multiples.split(",")]
    draw(results, price, price_date, bs["net_debt"], shares_now, converts,
         multiples, args.out)

    cap = price * shares_now
    ev = cap + bs["net_debt"]
    print(f"\n현재 ({price_date})")
    print(f"  주가              ${price:,.2f}")
    print(f"  주식수            {shares_now/1e6:,.1f}M ({shares_date})")
    print(f"  시가총액          ${cap/B:,.2f}B")
    print(f"  순차입            ${bs['net_debt']/B:,.2f}B")
    print(f"  EV                ${ev/B:,.2f}B")
    print(f"  EV / 가동 ARR     {ev/disc.ARR_OPERATING.value:,.1f}x")
    print(f"  EV / 목표 ARR     {ev/disc.ARR_TARGET.value:,.1f}x")
    print(f"  EV / 수주잔고     {ev/idata.backlog(args.refresh).total:,.2f}x")

    print(f"\n전환사채")
    print(f"  원금              ${conv_principal/B:,.2f}B")
    print(f"  희석 주식수       {conv_shares/1e6:,.1f}M")
    print(f"  평균 전환가       ${conv_principal/conv_shares:,.2f}"
          f"  (현재 주가의 {conv_principal/conv_shares/price:,.1f}배)")

    print(f"\n시나리오 (현금 영업비용 목표 구간 ${OPEX_AT_TARGET/B:,.2f}B/년 가정)")
    for r in results:
        s = r.scenario
        print(f"\n  {s.name}")
        print(f"    ARR ${s.arr/B:,.1f}B · 마진 {s.margin*100:,.0f}% · "
              f"배수 {s.multiple:,.1f}x · CAPEX ${s.capex/B:,.0f}B · "
              f"선급금 {s.prepay_share*100:,.0f}% · 증자 ${s.equity_raise/B:,.1f}B")
        print(f"    자본집약도 ARR 1달러당 ${s.capex/s.arr:,.2f} · "
              f"자기자본이 0이 되는 배수 {r.net_debt/r.ebitda:,.1f}x")
        print(f"    EBITDA ${r.ebitda/B:,.2f}B → EV ${r.enterprise/B:,.1f}B "
              f"− 순차입 ${r.net_debt/B:,.1f}B = 자기자본 ${r.equity/B:,.1f}B")
        print(f"    주식수 {r.shares/1e6:,.0f}M → 주당 ${r.per_share:,.2f} "
              f"({r.per_share/price - 1:+.0%})"
              + ("  [전환사채 전환 반영]" if r.converts_dilute else ""))

    band = sorted(max(r.per_share, 0) for r in results)
    print(f"\n주당가치 범위 ${band[0]:,.0f} ~ ${band[-1]:,.0f} "
          f"(중앙 ${band[len(band)//2]:,.0f}) · 현재 ${price:,.2f}")
    print("투자 판단이나 권유가 아니다.")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
