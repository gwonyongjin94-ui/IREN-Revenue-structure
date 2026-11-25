#!/usr/bin/env python3
"""ARR이 어디서 나오는가 — MW(IT) x MW당 단가.

AI 데이터센터 매출의 분모는 랙에 들어가는 전력이다. 계약 단가는 그 전력
1MW가 1년에 만드는 매출로 공시된다. 그래서 ARR은 사실상 곱셈 하나다.

    ARR = 가동 MW(IT) x MW당 연매출

회사가 공시한 점이 세 개 있다.

    가동 ARR        약 $1B          (2026-11-05)
    목표 ARR        $4B / 0.3GW(IT) → MW당 $13.3M 을 함의한다
    분기 후 계약    5년 $22M/MW · 단기 $40M/MW

셋이 서로 안 맞는다. 목표가 함의하는 단가가 새로 맺은 계약 단가의 60% 수준
이다. 설명은 둘 중 하나다. (1) 0.3GW 에는 단가가 낮은 코로케이션 전용 계약이
섞여 있다. (2) 0.3GW 가 매출을 내는 MW가 아니라 설치 기준 총량이다. 회사는
어느 쪽인지 밝히지 않았다. 이 차이가 ARR 추정에서 가장 큰 미지수이므로,
단일 선이 아니라 단가 밴드로 그린다.

위    MW x 단가 평면. 공시된 점 세 개를 얹는다
아래  분기 AI 클라우드 매출을 연율화한 값 — 공시 ARR과 같은 방향인지 본다

데이터 출처: SEC EDGAR 10-Q · Q1 FY27 보도자료

사용 예:
  python arr_model.py
"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import iren_data as idata
import disclosures as disc

B = 1e9
M = 1e6


def implied_rate() -> float:
    """회사 목표가 함의하는 MW당 연매출."""
    return disc.ARR_TARGET.value / disc.IT_MW_FOR_TARGET.value


def draw(revenue, out_path):
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(12, 8.8), dpi=160,
        gridspec_kw={"height_ratios": [1.25, 1], "hspace": 0.40})
    fig.patch.set_facecolor(idata.SURFACE)

    # --- 위: MW x 단가 --------------------------------------------------
    idata.style_axes(top)
    mws = list(range(0, 901, 10))
    rates = [
        (disc.REVENUE_PER_MW_SHORT.value, "단기 계약 $40M/MW", idata.MINING_COLOR, (2, 2)),
        (disc.REVENUE_PER_MW_5Y.value, "5년 계약 $22M/MW", idata.CLOUD_COLOR, (1, 0)),
        (implied_rate(), f"목표가 함의하는 ${implied_rate()/M:,.1f}M/MW",
         idata.INK_MUTED, (5, 2)),
    ]
    for rate, name, color, dash in rates:
        line, = top.plot(mws, [m * rate / B for m in mws], linewidth=1.8,
                         color=color, zorder=3)
        line.set_dashes(dash)
        # 기울기가 가파른 선은 화면 위로 빠져나간다. 라벨은 각 선이 보이는
        # 마지막 지점에 붙인다 — 오른쪽 끝에 고정하면 라벨이 사라진다
        ymax = 22
        last = max(m for m in mws if m * rate / B <= ymax * 0.98)
        top.annotate(idata.tex_safe(name), (last, last * rate / B),
                     xytext=(-6, 6), textcoords="offset points", ha="right",
                     fontsize=9.5, color=color, fontweight="bold")

    points = [
        (disc.IT_MW_FOR_TARGET.value, disc.ARR_TARGET.value,
         f"목표 ${disc.ARR_TARGET.value/B:,.0f}B / {disc.IT_MW_FOR_TARGET.value:,.0f}MW\n"
         f"{disc.ARR_TARGET_DATE} 목표, 2월 말까지 연기 가능"),
    ]
    for mw, arr, text in points:
        top.scatter([mw], [arr / B], s=90, color=idata.PRICE_COLOR, zorder=5)
        top.annotate(idata.tex_safe(text), (mw, arr / B), xytext=(14, -26),
                     textcoords="offset points", fontsize=9.5,
                     color=idata.INK_PRIMARY)

    top.axhline(disc.ARR_OPERATING.value / B, color=idata.LEASE_COLOR,
                linewidth=1.4, linestyle="--", zorder=4)
    top.annotate(idata.tex_safe(
        f"현재 가동 ARR 약 ${disc.ARR_OPERATING.value/B:,.0f}B"),
        (890, disc.ARR_OPERATING.value / B), xytext=(0, 7), ha="right",
        textcoords="offset points", fontsize=9.5, color=idata.LEASE_COLOR,
        fontweight="bold")

    top.axvline(disc.IT_MW_TARGET_CY2027.value, color=idata.INK_MUTED,
                linewidth=1.0, linestyle=":", zorder=2)
    top.annotate(idata.tex_safe(
        f"CY2027 용량 목표 {disc.IT_MW_TARGET_CY2027.value:,.0f}MW\n"
        "— 단가에 따라 ARR이 "
        f"${disc.IT_MW_TARGET_CY2027.value*implied_rate()/B:,.0f}B ~ "
        f"${disc.IT_MW_TARGET_CY2027.value*disc.REVENUE_PER_MW_5Y.value/B:,.0f}B "
        "로 갈린다"),
        (disc.IT_MW_TARGET_CY2027.value, 0), xytext=(-250, 18),
        textcoords="offset points", fontsize=9.5, color=idata.INK_SECONDARY)

    top.set_xlim(0, 900)
    top.set_ylim(0, 22)
    top.set_yticks(range(0, 23, 4))
    top.set_xlabel("가동 MW (IT)", fontsize=10, color=idata.INK_SECONDARY)
    top.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}B"))
    top.set_title("ARR = 가동 MW(IT) x MW당 연매출", fontsize=15,
                  color=idata.INK_PRIMARY, fontweight="bold", loc="left", pad=16)
    top.annotate("회사가 공시한 단가와, 회사 목표가 함의하는 단가가 어긋난다 — "
                 "그 차이가 ARR 추정의 가장 큰 미지수다",
                 (0.0, 1.03), xycoords="axes fraction", fontsize=9.5,
                 color=idata.INK_MUTED)

    # --- 아래: 분기 매출의 연율화 ----------------------------------------
    idata.style_axes(bottom)
    cloud = [(r.quarter, r.ai_cloud) for r in revenue if r.ai_cloud]
    xs = list(range(len(cloud)))
    ys = [v * 4 / B for _, v in cloud]
    bottom.bar(xs, ys, width=0.58, color=idata.CLOUD_COLOR, zorder=3)
    for x, y in zip(xs, ys):
        bottom.annotate(idata.tex_safe(f"${y:,.2f}B"), (x, y), xytext=(0, 5),
                        textcoords="offset points", ha="center", fontsize=9,
                        color=idata.INK_SECONDARY)
    bottom.axhline(disc.ARR_OPERATING.value / B, color=idata.LEASE_COLOR,
                   linewidth=1.4, linestyle="--", zorder=4)
    bottom.annotate(idata.tex_safe(
        f"공시 가동 ARR 약 ${disc.ARR_OPERATING.value/B:,.0f}B"),
        (len(xs) - 0.5, disc.ARR_OPERATING.value / B), xytext=(-4, 6),
        textcoords="offset points", ha="right", fontsize=9.5,
        color=idata.LEASE_COLOR, fontweight="bold")

    bottom.set_xticks(xs)
    bottom.set_xticklabels([idata.label(q) for q, _ in cloud], fontsize=9.5)
    bottom.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.1f}B"))
    bottom.set_title("AI 클라우드 분기 매출 x 4", fontsize=13, color=idata.INK_PRIMARY,
                     fontweight="bold", loc="left", pad=12)
    bottom.annotate(
        "ARR은 분기말 가동 기준이고 분기 매출은 기간 평균이라, 램프업 중에는 "
        "연율화 값이 ARR보다 낮게 나오는 게 정상이다",
        (0.0, -0.26), xycoords="axes fraction", fontsize=9.5,
        color=idata.INK_SECONDARY)

    fig.text(0.5, 0.012,
             "출처: SEC EDGAR 10-Q · Q1 FY27 보도자료 (각주 4·5·7·12)",
             ha="center", fontsize=8.5, color=idata.INK_MUTED)
    fig.subplots_adjust(top=0.91, bottom=0.115, left=0.075, right=0.975)
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "arr_model.png"))
    args = ap.parse_args()

    revenue = idata.quarterly_revenue(args.refresh)
    draw(revenue, args.out)

    rate = implied_rate()
    print(f"\n목표가 함의하는 단가   ${rate/M:,.1f}M / MW(IT) / 년")
    print(f"  5년 계약 단가        ${disc.REVENUE_PER_MW_5Y.value/M:,.0f}M "
          f"({rate/disc.REVENUE_PER_MW_5Y.value - 1:+.0%})")
    print(f"  단기 계약 단가       ${disc.REVENUE_PER_MW_SHORT.value/M:,.0f}M "
          f"({rate/disc.REVENUE_PER_MW_SHORT.value - 1:+.0%})")

    print(f"\nCY2027 목표 {disc.IT_MW_TARGET_CY2027.value:,.0f}MW 의 ARR 범위")
    for name, r in (("목표 함의 단가", rate),
                    ("5년 계약 단가", disc.REVENUE_PER_MW_5Y.value),
                    ("단기 계약 단가", disc.REVENUE_PER_MW_SHORT.value)):
        print(f"  {name:14} ${disc.IT_MW_TARGET_CY2027.value * r / B:6.1f}B")

    print("\nAI 클라우드 분기 매출 x 4")
    for r in revenue:
        if r.ai_cloud:
            print(f"  {idata.label(r.quarter):>8} ${r.ai_cloud*4/B:,.2f}B")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
