#!/usr/bin/env python3
"""매출 구성의 교체 — 채굴에서 AI 클라우드로.

위    분기 매출을 세그먼트로 쌓는다. 역전 분기를 표시한다.
아래  같은 시간축의 비트코인 가격. 채굴 매출이 왜 무너졌는지 가격만으로
      설명되는지 보기 위한 대조다.

채굴 매출은 해시프라이스(비트코인 가격 x 네트워크 난이도의 역수)에 비례하므로
가격과 같이 봐야 한다. 다만 IREN의 채굴 매출 감소는 가격 하락분보다 훨씬
크다 — 채굴기를 폐기하고 전력을 AI로 돌렸기 때문이다. 두 패널을 나란히 놓으면
"가격이 떨어져서"와 "스스로 접어서"를 구분할 수 있다.

데이터 출처: SEC EDGAR · Yahoo Finance

사용 예:
  python segments.py
"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import iren_data as idata
import disclosures as disc


def build(refresh: bool = False):
    revenue = idata.quarterly_revenue(refresh)
    btc = idata.btc_price(refresh)
    return revenue, btc


def crossover(revenue) -> int | None:
    """AI 클라우드가 채굴을 처음 넘어선 분기의 인덱스."""
    for i, r in enumerate(revenue):
        if r.mining is None or r.ai_cloud is None:
            continue
        if r.ai_cloud > r.mining:
            return i
    return None


def draw(revenue, btc, out_path):
    fig, (top, bottom) = idata.figure([2.2, 1.0], height=8.2)

    xs = list(range(len(revenue)))
    labels = [idata.label(r.quarter) for r in revenue]
    mining = [(r.mining or 0) / 1e6 for r in revenue]
    cloud = [(r.ai_cloud or 0) / 1e6 for r in revenue]

    top.bar(xs, mining, width=0.62, color=idata.MINING_COLOR,
            label="비트코인 채굴", zorder=3)
    top.bar(xs, cloud, width=0.62, bottom=mining, color=idata.CLOUD_COLOR,
            label="AI 클라우드", zorder=3)

    for x, r, m, c in zip(xs, revenue, mining, cloud):
        top.annotate(f"{m + c:,.0f}", (x, m + c), textcoords="offset points",
                     xytext=(0, 5), ha="center", fontsize=9,
                     color=idata.INK_SECONDARY, zorder=4)

    i = crossover(revenue)
    if i is not None:
        top.annotate(
            idata.tex_safe(f"{labels[i]}: AI 클라우드가 채굴을 넘어선 분기\n"
                           f"${cloud[i]:,.0f}M vs ${mining[i]:,.0f}M"),
            xy=(i, mining[i] + cloud[i]), xytext=(-150, 48),
            textcoords="offset points", fontsize=9.5, color=idata.INK_PRIMARY,
            arrowprops=dict(arrowstyle="-", color=idata.INK_MUTED, linewidth=0.9),
            zorder=5)

    top.set_xticks(xs)
    top.set_xticklabels(labels, fontsize=9.5)
    top.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}M"))
    idata.titles(top, "IREN 분기 매출 — 세그먼트",
                 "4분기 세그먼트 매출은 공시되지 않아 연간에서 1~3분기를 뺀 값")
    top.legend(loc="upper left", frameon=False, fontsize=9.5, ncol=2,
               bbox_to_anchor=(0.0, 0.96))

    # 아래: 같은 기간의 비트코인 가격. 분기 경계에 맞춰 x축을 공유시키지 않고
    # 날짜축을 쓴다 — 분기 눈금에 억지로 맞추면 가격의 모양이 뭉개진다.
    start = idata.quarter_end(revenue[0].quarter)
    pts = [(d, v) for d, v in btc if d >= start]
    bottom.plot([d for d, _ in pts], [v / 1e3 for _, v in pts],
                color=idata.BTC_COLOR, linewidth=1.4, zorder=3)
    bottom.fill_between([d for d, _ in pts], [v / 1e3 for _, v in pts],
                        color=idata.BTC_COLOR, alpha=0.10, zorder=2)
    bottom.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}k"))
    bottom.set_ylabel("비트코인", fontsize=10, color=idata.INK_SECONDARY)

    peak = max(pts, key=lambda p: p[1])
    last = pts[-1]
    for when, value, text, dx in ((peak[0], peak[1], f"고점 ${peak[1]/1e3:,.0f}k", 8),
                                  (last[0], last[1], f"${last[1]/1e3:,.0f}k", -60)):
        bottom.annotate(text, (when, value / 1e3), textcoords="offset points",
                        xytext=(dx, 6), fontsize=9, color=idata.INK_SECONDARY)

    drop = (last[1] / peak[1] - 1) * 100
    mining_drop = (mining[-1] / max(mining) - 1) * 100
    idata.titles(bottom, "비트코인 가격 — 대조군",
                 f"고점 대비 비트코인 {drop:+.0f}% · "
                 f"같은 기간 채굴 매출 {mining_drop:+.0f}% — "
                 "감소분의 절반은 가격으로 설명되지 않는다", size=13)

    idata.footer(fig, "출처: SEC EDGAR 10-Q/10-K · Yahoo Finance")
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="캐시 무시하고 다시 가져온다")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "segments.png"))
    args = ap.parse_args()

    revenue, btc = build(args.refresh)
    draw(revenue, btc, args.out)

    print(f"\n{'분기':>8} {'총매출':>9} {'채굴':>9} {'AI클라우드':>11} {'AI비중':>8}")
    for r in revenue:
        share = (r.ai_cloud / r.total * 100) if r.ai_cloud is not None else float("nan")
        print(f"{idata.label(r.quarter):>8} {r.total/1e6:9.1f} "
              f"{(r.mining or 0)/1e6:9.1f} {(r.ai_cloud or 0)/1e6:11.1f} {share:7.1f}%")
    latest = revenue[-1]
    if latest.ai_services and latest.ai_lease:
        print(f"\n{idata.label(latest.quarter)} AI 클라우드 내부 구성")
        print(f"  서비스 (GPU 시간당, ASC 606) ${latest.ai_services/1e6:,.0f}M")
        print(f"  임대 (코로케이션, ASC 842)   ${latest.ai_lease/1e6:,.0f}M")
    print(f"\n채굴 FY2026 자산손상 ${disc.MINING_IMPAIRMENT_FY26.value/1e6:,.0f}M "
          f"[{disc.MINING_IMPAIRMENT_FY26.src}]")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
