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

# 자산가치 하한. 사업이 계획대로 안 되면 EBITDA 배수는 무너지지만 데이터센터와
# GPU는 남는다. 그래서 기업가치의 바닥을 '완공 시점 유형자산 x 회수율'로 깐다.
#
# 회수율은 공시에서 읽을 수 없고, 이 저장소에서 확률 다음으로 결과를 크게
# 흔드는 가정이다. 토지·건물·전력 계약은 잘 받지만 중고 GPU는 수요가 식은
# 국면에서 특히 안 받으므로 둘의 중간쯤인 60%를 기본값으로 둔다.
#
# 보수 시나리오에서 이 값이 58% 아래면 주당가치가 다시 0이 된다. 그만큼
# 예민하므로 --recovery 로 바꿔 볼 수 있게 열어 둔다.
ASSET_RECOVERY = 0.60

# 시나리오 값은 전부 '완공 시점' 값이다. 거기까지 가는 데 걸리는 시간을 현재로
# 당겨와야 오늘의 적정가격이 된다. 회사는 $4B ARR 달성을 2027년 1~2월로 제시
# 했지만 그건 0.3GW 프로그램 얘기고, 그 매출이 온전히 한 해를 돌아 실적으로
# 확인되는 시점은 FY2028 중반이다. 그래서 1.5년으로 둔다.
HORIZON_YEARS = 1.5
# 할인율은 자기자본 요구수익률이다. 이 회사의 베타와 레버리지를 감안한 값이고,
# 가정이다 — 15%p 를 12%로 바꾸면 적정가격이 약 4% 움직인다.
DISCOUNT_RATE = 0.15


@dataclass(frozen=True)
class Scenario:
    name: str
    arr: float            # 달성 ARR
    margin: float         # 매출총이익률 (매출원가 제외, 감가상각 전)
    multiple: float       # EV / EBITDA
    capex: float          # 여기까지 가는 데 더 쓰는 CAPEX
    prepay_share: float   # 그 CAPEX 중 고객 선급금이 덮는 비율
    equity_raise: float   # 증자 금액
    prob: float           # 이 결말이 일어날 확률
    color: str
    note: str


def scenarios() -> list[Scenario]:
    """세 가지 결말. 가정은 전부 여기 적혀 있다.

    확률(prob)만은 공시에서 끌어낼 수 없는 값이다. 무엇을 읽고 이렇게 매겼는지는
    README의 '확률 30 / 50 / 20 의 근거' 절에 사실 단위로 적어 뒀다. 요약하면
    기준에 절반을 준 건 회사가 그 구간에 대해서만 계약과 자금을 양쪽 다
    못박았기 때문이고, 보수를 낙관보다 무겁게 둔 건 미확보 $6B 이 추가 용량보다
    먼저 닥치는 문제라서다. 공시가 바뀌면 여기 숫자도 바뀌어야 한다.
    """
    return [
        Scenario("보수 — 목표 미달", 2.5e9, 0.78, 7.0, 10.0e9, 0.15, 0.0, 0.30,
                 idata.DEBT_COLOR,
                 "$15B 중 $10B 을 쓴 채로 자금이 끊겨 ARR은 $2.5B 에서 멈춘다.\n"
                 "마진은 코로케이션 비중이 늘며 하락, 부족분은 전부 차입"),
        Scenario("기준 — 회사 목표 달성", disc.ARR_TARGET.value,
                 disc.AI_CLOUD_GROSS_MARGIN.value, 10.0,
                 disc.CAPEX_REMAINING_FY27.value, 0.30, 2.0e9, 0.50,
                 idata.CLOUD_COLOR,
                 "공시한 $4B ARR 을 공시한 $15B CAPEX 로 달성.\n"
                 "현재 마진 유지, 부족분 중 $2B 는 증자"),
        Scenario("낙관 — 0.8GW 절반까지", 6.0e9,
                 disc.AI_CLOUD_GROSS_MARGIN.value, 13.0, 22.0e9, 0.40, 2.0e9, 0.20,
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
    floor_bound: bool = False   # 기업가치가 EBITDA가 아니라 자산 하한으로 정해졌나


def evaluate(s: Scenario, net_debt_now: float, shares_now: float,
             price: float, converts: tuple[float, float],
             assets_now: float = 0.0,
             recovery: float = ASSET_RECOVERY) -> Result:
    opex = OPEX_AT_TARGET + max(s.arr - disc.ARR_TARGET.value, 0) * OPEX_SLOPE
    ebitda = s.arr * s.margin - opex

    net_debt = net_debt_now + s.capex * (1 - s.prepay_share) - s.equity_raise

    # 증자는 오늘 주가로 한다고 본다. 주가가 낮을수록 같은 금액에 더 많이 희석된다 —
    # 이 되먹임이 자금 부족 상태의 주식이 비싸 보이지 않는 이유다.
    shares = shares_now + VEST_SHARES + (s.equity_raise / price if price else 0)

    principal, conv_shares = converts
    # 계속기업 가치와 청산 바닥 중 큰 쪽. 둘 중 무엇이 값을 정했는지 남긴다 —
    # 바닥이 이겼다는 건 "이 시나리오에서는 사업이 아니라 자산이 전부"라는 뜻이고,
    # 그 결론은 회수율 가정 하나에 매달려 있으므로 드러나야 한다.
    going = ebitda * s.multiple
    floor = (assets_now + s.capex) * recovery
    enterprise = max(going, floor)
    floor_bound = floor > going
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

    return Result(s, ebitda, net_debt, enterprise, equity, shares, per_share,
                  dilute, floor_bound)


def discount(value: float) -> float:
    """완공 시점 값을 오늘로 당긴다."""
    return value / (1 + DISCOUNT_RATE) ** HORIZON_YEARS


def fair_value(results: list[Result]) -> float:
    """확률가중 기대 주당가치의 현재가치 — 이 저장소가 내는 단일 적정가격.

    범위를 내놓고 끝내면 "그래서 얼마냐"에 답하지 못한다. 그래서 각 결말에
    확률을 붙여 기댓값을 내고, 완공까지의 시간으로 할인한다. 확률은 가정이고
    가장 주관적인 입력이다. 그래서 아래 implied_downside()로 '시장은 이걸
    몇 퍼센트로 보고 있나'를 같이 계산해, 내 확률이 시장과 얼마나 다른지
    드러낸다. 자기자본이 음수로 나오는 결말은 0으로 자른다 — 주주는 유한책임
    이라 마이너스까지 책임지지 않는다.
    """
    total = sum(r.scenario.prob for r in results)
    expected = sum(max(r.per_share, 0) * r.scenario.prob for r in results) / total
    return discount(expected)


def implied_downside(results: list[Result], price: float) -> float:
    """현재 주가가 함의하는 '목표 미달' 확률.

    보수 시나리오의 확률만 움직이고, 나머지 둘의 상대 비중은 그대로 둔다.
    그러면 미지수가 하나라 바로 풀린다.
    """
    down = max(results[0].per_share, 0.0)
    rest = results[1:]
    weight = sum(r.scenario.prob for r in rest)
    if weight <= 0:
        return float("nan")
    up = sum(max(r.per_share, 0) * r.scenario.prob for r in rest) / weight
    if up <= down:
        return float("nan")
    # discount(p x down + (1-p) x up) = price 를 p 에 대해 푼다
    target = price * (1 + DISCOUNT_RATE) ** HORIZON_YEARS
    return max(0.0, min(1.0, (target - up) / (down - up)))


def per_share_curve(arrs, multiple, base: Scenario, net_debt_now, shares_now,
                    price, converts, assets_now=0.0, recovery=ASSET_RECOVERY):
    out = []
    for arr in arrs:
        # 곡선 위에서는 CAPEX가 ARR과 같이 움직인다. 자본집약도(ARR 1달러당
        # CAPEX)를 기준 시나리오 값으로 고정해, 적게 벌면 적게 썼다고 본다.
        capex = base.capex * arr / base.arr
        s = Scenario(base.name, arr, base.margin, multiple, capex,
                     base.prepay_share, base.equity_raise, base.prob,
                     base.color, "")
        out.append(evaluate(s, net_debt_now, shares_now, price, converts,
                            assets_now, recovery).per_share)
    return out


def draw(results, price, price_date, net_debt_now, shares_now, converts,
         multiples, out_path, assets_now=0.0, recovery=ASSET_RECOVERY):
    fig, (top, bottom) = idata.figure([1.0, 1.05], height=9.0)

    # --- 위: 시나리오 ----------------------------------------------------
    fair = fair_value(results)
    xs = list(range(len(results)))
    tops = [max(r.per_share, 0) for r in results]
    ceiling = max(max(tops), fair, price) * 1.28

    top.bar(xs, tops, width=0.46, color=[r.scenario.color for r in results],
            zorder=3)
    for x, r, value in zip(xs, results, tops):
        if value == 0:
            # 0 인 막대는 아무것도 안 그려지면 "빠진 막대"로 보인다. 바닥에
            # 얕은 자국을 남겨 '계산 결과가 0'임을 보이게 한다
            top.bar([x], [ceiling * 0.016], width=0.46,
                    color=r.scenario.color, alpha=0.55, zorder=3)
        label = (f"${value:,.0f}" if value > 0
                 else f"$0   계산상 -${abs(r.per_share):,.0f}")
        top.annotate(idata.tex_safe(label), (x, value if value else ceiling * 0.016),
                     xytext=(0, 9), textcoords="offset points", ha="center",
                     fontsize=15 if value else 13, fontweight="bold",
                     color=idata.INK_PRIMARY)
        top.annotate(idata.tex_safe(
            f"확률 {r.scenario.prob*100:,.0f}%   ARR ${r.scenario.arr/B:,.1f}B"
            f"   배수 {r.scenario.multiple:,.0f}x"
            + ("\n자산 하한이 값을 정한다" if r.floor_bound else "")),
            (x, 0), xycoords=("data", "axes fraction"), xytext=(0, -42),
            textcoords="offset points", ha="center", fontsize=9.5,
            color=idata.INK_SECONDARY, annotation_clip=False)

    for value, color, name, dy in (
            (fair, idata.INK_PRIMARY, f"적정가격 ${fair:,.2f}", 6),
            (price, idata.PRICE_COLOR, f"현재 주가 ${price:,.2f}", -15)):
        top.axhline(value, color=color, linewidth=1.6, zorder=4,
                    linestyle="-" if dy > 0 else (0, (5, 3)))
        top.annotate(idata.tex_safe(name), (0.0, value),
                     xycoords=("axes fraction", "data"), xytext=(4, dy),
                     textcoords="offset points", fontsize=10.5,
                     color=color, fontweight="bold")

    top.set_ylim(0, ceiling)
    top.set_xlim(-0.6, len(results) - 0.4)
    top.set_xticks(xs)
    top.set_xticklabels([r.scenario.name for r in results], fontsize=11.5)
    top.tick_params(axis="x", pad=8)
    top.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    idata.titles(top, "시나리오별 주당가치와 적정가격",
                 f"막대는 완공 시점 값 · 적정가격은 그 확률가중 기댓값을 "
                 f"{HORIZON_YEARS:,.1f}년 · 할인율 {DISCOUNT_RATE*100:,.0f}% 로 "
                 "현재로 당긴 값")

    # --- 아래: ARR x 배수 평면 -------------------------------------------
    base = results[1].scenario
    arrs = [x * 1e8 for x in range(10, 71)]
    xs_b = [a / B for a in arrs]
    curves = {m: per_share_curve(arrs, m, base, net_debt_now, shares_now,
                                 price, converts, assets_now, recovery)
              for m in multiples}
    lo, mid, hi = (curves[m] for m in sorted(curves))

    # 배수 범위를 면으로 깐다. 선 세 개를 겹쳐 그리면 어느 게 어느 건지
    # 읽히지 않는데, 면으로 깔면 '불확실성의 폭'으로 바로 읽힌다
    bottom.fill_between(xs_b, lo, hi, color=idata.CLOUD_COLOR, alpha=0.13,
                        zorder=2, linewidth=0)
    bottom.plot(xs_b, mid, color=idata.CLOUD_COLOR, linewidth=2.4, zorder=4)
    ceiling_b = max(hi) * 1.05

    for values, name in ((hi, f"{max(multiples):,.0f}x"),
                         (mid, f"{sorted(multiples)[1]:,.0f}x"),
                         (lo, f"{min(multiples):,.0f}x")):
        bottom.annotate(name, (xs_b[-1], values[-1]), xytext=(6, -3),
                        textcoords="offset points", fontsize=10,
                        color=idata.CLOUD_COLOR, fontweight="bold")

    bound = [evaluate(Scenario(base.name, a, base.margin, sorted(multiples)[1],
                               base.capex * a / base.arr, base.prepay_share,
                               base.equity_raise, base.prob, base.color, ""),
                      net_debt_now, shares_now, price, converts,
                      assets_now, recovery).floor_bound
             for a in arrs]
    if any(bound):
        edge = xs_b[max(i for i, b in enumerate(bound) if b)]
        bottom.axvspan(xs_b[0], edge, color=idata.INK_MUTED, alpha=0.07, zorder=1)
        # 라벨은 띠 안쪽 빈 곳에 세로로 앉힌다. 띠 아래에 가로로 깔면 축 밖으로
        # 삐져나가 잘린다
        bottom.annotate(idata.tex_safe(
            f"자산 하한이\n값을 정하는 구간\n(회수율 {recovery*100:,.0f}%)"),
            (xs_b[0], 0.86), xycoords=("data", "axes fraction"),
            xytext=(10, 0), textcoords="offset points", ha="left", va="top",
            fontsize=9.5, color=idata.INK_SECONDARY, linespacing=1.5)

    bottom.axhline(price, color=idata.PRICE_COLOR, linewidth=1.6,
                   linestyle=(0, (5, 3)), zorder=5)
    bottom.annotate(idata.tex_safe(f"현재 주가 ${price:,.2f}"), (0.0, price),
                    xycoords=("axes fraction", "data"), xytext=(4, 5),
                    textcoords="offset points", fontsize=10,
                    color=idata.PRICE_COLOR, fontweight="bold")

    # 기준 배수 곡선이 현재 주가를 지나는 지점 — 시장이 함의하는 ARR
    crossing = next((x for x, y in zip(xs_b, mid) if y >= price), None)
    if crossing:
        bottom.scatter([crossing], [price], s=70, color=idata.PRICE_COLOR,
                       zorder=6, edgecolor="white", linewidth=1.4)
        bottom.annotate(idata.tex_safe(
            f"현재 주가가 함의하는 ARR 약 ${crossing:,.1f}B"),
            (crossing, price), xytext=(10, -22), textcoords="offset points",
            fontsize=9.5, color=idata.INK_SECONDARY)

    for value, name in ((disc.ARR_OPERATING.value / B, "현재 가동"),
                        (disc.ARR_TARGET.value / B, "회사 목표")):
        bottom.axvline(value, color=idata.INK_MUTED, linewidth=1.0,
                       linestyle=":", zorder=2)
        bottom.annotate(idata.tex_safe(f"{name} ${value:,.0f}B"),
                        (value, 1.0), xycoords=("data", "axes fraction"),
                        xytext=(5, -14), textcoords="offset points",
                        fontsize=9.5, color=idata.INK_SECONDARY)

    bottom.set_xlim(1.0, 7.0)
    bottom.set_ylim(0, ceiling_b)
    bottom.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}B"))
    bottom.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    bottom.set_xlabel("달성 ARR", fontsize=10, color=idata.INK_SECONDARY)
    idata.titles(bottom, "달성 ARR과 배수가 만드는 주당가치",
                 f"띠는 EV/EBITDA {min(multiples):,.0f}~{max(multiples):,.0f}x "
                 f"구간, 가운데 선이 {sorted(multiples)[1]:,.0f}x · "
                 "나머지 가정은 기준 시나리오와 같다")

    idata.footer(fig, "출처: SEC EDGAR 10-Q · Yahoo Finance · Q1 FY27 보도자료    "
                      "투자 판단이나 권유가 아니다")
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--multiples", default="7,10,13",
                    help="아래 패널에 그릴 EV/EBITDA 배수")
    ap.add_argument("--recovery", type=float, default=ASSET_RECOVERY,
                    help="자산 하한에 쓰는 회수율 (0~1)")
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

    assets_now = bs["ppe"]
    results = [evaluate(s, bs["net_debt"], shares_now, price, converts,
                        assets_now, args.recovery)
               for s in scenarios()]
    multiples = [float(x) for x in args.multiples.split(",")]
    draw(results, price, price_date, bs["net_debt"], shares_now, converts,
         multiples, args.out, assets_now, args.recovery)

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

    print(f"\n시나리오 (현금 영업비용 목표 구간 ${OPEX_AT_TARGET/B:,.2f}B/년, "
          f"자산 회수율 {args.recovery*100:,.0f}% 가정)")
    for r in results:
        s = r.scenario
        print(f"\n  {s.name}")
        print(f"    ARR ${s.arr/B:,.1f}B · 마진 {s.margin*100:,.0f}% · "
              f"배수 {s.multiple:,.1f}x · CAPEX ${s.capex/B:,.0f}B · "
              f"선급금 {s.prepay_share*100:,.0f}% · 증자 ${s.equity_raise/B:,.1f}B")
        print(f"    자본집약도 ARR 1달러당 ${s.capex/s.arr:,.2f} · "
              f"계속기업 기준 자기자본이 0이 되는 배수 {r.net_debt/r.ebitda:,.1f}x")
        floor = (assets_now + s.capex) * args.recovery
        print(f"    계속기업 EV ${r.ebitda*s.multiple/B:,.1f}B vs "
              f"자산 하한 ${floor/B:,.1f}B"
              f"  ({'하한 적용' if r.floor_bound else '계속기업 적용'})")
        print(f"    EBITDA ${r.ebitda/B:,.2f}B → EV ${r.enterprise/B:,.1f}B "
              f"− 순차입 ${r.net_debt/B:,.1f}B = 자기자본 ${r.equity/B:,.1f}B")
        print(f"    주식수 {r.shares/1e6:,.0f}M → 주당 ${r.per_share:,.2f} "
              f"({r.per_share/price - 1:+.0%})"
              + ("  [전환사채 전환 반영]" if r.converts_dilute else ""))

    band = sorted(max(r.per_share, 0) for r in results)
    fair = fair_value(results)
    implied = implied_downside(results, price)
    expected = fair * (1 + DISCOUNT_RATE) ** HORIZON_YEARS
    print(f"\n주당가치 범위 ${band[0]:,.0f} ~ ${band[-1]:,.0f} "
          f"(중앙 ${band[len(band)//2]:,.0f})")
    print(f"확률가중 기대값 (완공 시점)  ${expected:,.2f}")
    print(f"  할인 {DISCOUNT_RATE*100:,.0f}% x {HORIZON_YEARS:,.1f}년")
    print(f"적정가격 (현재가치)          ${fair:,.2f}")
    print(f"현재 주가                    ${price:,.2f}  ({fair/price - 1:+.0%})")
    if implied == implied:   # NaN 아님
        print(f"\n현재 주가가 함의하는 '목표 미달' 확률  {implied*100:,.0f}%")
        print(f"  이 모델이 쓴 확률                     "
              f"{results[0].scenario.prob*100:,.0f}%")
    print("\n투자 판단이나 권유가 아니다.")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
