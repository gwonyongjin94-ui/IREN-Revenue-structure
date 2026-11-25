#!/usr/bin/env python3
"""수주잔고 $20.3B 을 쪼갠다 — 이미 돌아가는 돈과, 지어야 생기는 돈.

보도자료의 'revenue backlog'는 성격이 다른 두 수치의 합이다.

  ASC 606 잔여 수행의무   GPU 시간당 과금 계약. 인식 시점이 주석에 나온다.
  ASC 842 계약 임대 총액  코로케이션. **개시되지 않은 계약까지 포함**한 총액.

둘째 다리가 중요하다. 개시된 임대의 최소 수취액은 10-Q에 따로 공시되는데,
그 값이 계약 임대 총액보다 훨씬 작다. 차이는 아직 건물이 없어서 임대가
시작되지 않은 계약이다. 즉 잔고의 대부분은 "계약은 됐지만 CAPEX를 더 써야
매출이 되는" 돈이다. 자금 조달이 이 회사 밸류에이션의 핵심인 이유다.

위    잔고 구성 — 개시 여부로 가른다
아래  계약으로 확정된 수취액의 시간 분포

데이터 출처: SEC EDGAR 10-Q 주석

사용 예:
  python backlog.py
"""

from __future__ import annotations

import argparse
import re

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import iren_data as idata
import disclosures as disc

B = 1e9


def fiscal_year_key(label: str) -> int | None:
    m = re.search(r"(\d{4})", label)
    return int(m.group(1)) if m else None


def draw(bl, revenue, out_path):
    commenced = bl.lease_payments.get("Total", 0.0)
    not_commenced = max(bl.leases - commenced, 0.0)

    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(12, 8.2), dpi=160,
        gridspec_kw={"height_ratios": [1, 1.15], "hspace": 0.38})
    fig.patch.set_facecolor(idata.SURFACE)

    # --- 위: 구성 ------------------------------------------------------
    idata.style_axes(top)
    top.grid(axis="y", visible=False)
    top.grid(axis="x", color=idata.GRID, linewidth=0.8, zorder=0)

    parts = [
        ("개시된 임대\n최소 수취액", commenced, idata.LEASE_COLOR,
         "건물이 인도돼 이미 임대가 돌아간다"),
        ("ASC 606 잔여 수행의무\n(GPU 시간당 과금)", bl.rpo, idata.CLOUD_COLOR,
         f"이 중 향후 12개월 ${(bl.rpo_next_12m or 0)/B:,.2f}B"),
        ("개시 전 임대 계약", not_commenced, idata.DEBT_COLOR,
         "데이터센터를 지어야 매출이 된다"),
    ]
    left = 0.0
    for name, value, color, _ in parts:
        top.barh([0], [value / B], left=left / B, height=0.42, color=color, zorder=3)
        if value / bl.total > 0.06:
            top.annotate(idata.tex_safe(f"${value/B:,.1f}B"),
                         (left / B + value / B / 2, 0), ha="center", va="center",
                         fontsize=11, fontweight="bold", color="white", zorder=4)
        left += value

    # 범례를 막대 밑에 설명과 함께 둔다 — 색만으로는 세 다리의 성격 차이가 안 보인다
    y = -0.52
    for name, value, color, note in parts:
        top.annotate("■", (0, y), xycoords=("axes fraction", "data"), xytext=(2, 0),
                     textcoords="offset points", color=color, fontsize=11, va="center")
        top.annotate(f"{name.replace(chr(10), ' ')} — {note}  "
                     f"({value / bl.total * 100:.0f}%)",
                     (0, y), xycoords=("axes fraction", "data"), xytext=(20, 0),
                     textcoords="offset points", fontsize=9.5,
                     color=idata.INK_SECONDARY, va="center")
        y -= 0.30

    top.set_ylim(-1.5, 0.5)
    top.set_yticks([])
    top.set_xticks(range(0, int(bl.total / B) + 5, 5))
    top.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}B"))
    top.set_title(idata.tex_safe(
        f"수주잔고 ${bl.total/B:,.1f}B 의 구성 — {bl.as_of}"),
        fontsize=15, color=idata.INK_PRIMARY, fontweight="bold", loc="left", pad=16)

    ttm = sum(r.total for r in revenue[-4:])
    top.annotate(idata.tex_safe(
        f"직전 4개 분기 실제 매출 ${ttm/B:,.2f}B — 잔고는 그 {bl.total/ttm:,.0f}배다"),
        (0.0, 1.02), xycoords="axes fraction", fontsize=9.5, color=idata.INK_MUTED)

    # --- 아래: 시간 분포 -----------------------------------------------
    idata.style_axes(bottom)
    years, values = [], []
    for name, value in bl.lease_payments.items():
        if name == "Total":
            continue
        fy = fiscal_year_key(name)
        years.append(("잔여 FY2027" if "Remainder" in name else
                      f"FY{fy}" if fy else name))
        values.append(value)

    xs = list(range(len(years)))
    bottom.bar(xs, [v / B for v in values], width=0.6,
               color=idata.LEASE_COLOR, zorder=3, label="개시된 임대 최소 수취액")
    # ASC 606 막대가 위에 쌓이는 두 해는 라벨을 막대 안에 흰 글씨로 넣는다 —
    # 막대 위에 두면 해치 패턴에 가려 안 보인다
    stacked_until = 2
    for x, v in zip(xs, values):
        if not v:
            continue
        inside = x < stacked_until
        bottom.annotate(
            idata.tex_safe(f"${v/1e6:,.0f}M"), (x, v / B / 2 if inside else v / B),
            textcoords="offset points", xytext=(0, 0 if inside else 5), ha="center",
            va="center" if inside else "bottom", fontsize=9,
            color="white" if inside else idata.INK_SECONDARY,
            fontweight="bold" if inside else "normal", zorder=5)

    # ASC 606 쪽은 회계연도가 아니라 '분기말로부터 12개월' 단위로 공시된다.
    # 회계연도 축에 억지로 얹지 않고 따로 표시한다.
    rpo_bars = [(0, bl.rpo_next_12m), (1, bl.rpo_following_12m)]
    for x, v in rpo_bars:
        if not v:
            continue
        bottom.bar([x], [v / B], width=0.6, bottom=[values[x] / B],
                   color=idata.CLOUD_COLOR, alpha=0.85, zorder=3,
                   hatch="///", edgecolor="white", linewidth=0,
                   label="ASC 606 인식 예정 (12개월 단위)" if x == 0 else None)
        bottom.annotate(idata.tex_safe(f"${v/B:,.2f}B"),
                        (x, values[x] / B + v / B), textcoords="offset points",
                        xytext=(0, 5), ha="center", fontsize=9,
                        color=idata.CLOUD_COLOR, fontweight="bold", zorder=4)

    bottom.set_xticks(xs)
    bottom.set_xticklabels(years, fontsize=9.5)
    bottom.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.1f}B"))
    bottom.set_title("계약으로 확정된 수취액의 시간 분포", fontsize=13,
                     color=idata.INK_PRIMARY, fontweight="bold", loc="left", pad=12)
    bottom.legend(loc="upper right", frameon=False, fontsize=9.5)
    bottom.annotate(
        idata.tex_safe(
            f"두 막대의 합 ${(commenced + (bl.rpo_next_12m or 0) + (bl.rpo_following_12m or 0))/B:,.1f}B "
            f"는 잔고 ${bl.total/B:,.1f}B 의 일부일 뿐이다. 나머지는 개시 전 임대로, "
            "데이터센터가 완공돼야 이 축에 올라온다."),
        xy=(0.0, -0.20), xycoords="axes fraction", fontsize=9.5,
        color=idata.INK_SECONDARY)

    fig.text(0.5, 0.012,
             "출처: SEC EDGAR 10-Q 매출 주석 (잔여 수행의무 · 최소 임대 수취액)",
             ha="center", fontsize=8.5, color=idata.INK_MUTED)
    fig.subplots_adjust(top=0.90, bottom=0.135, left=0.075, right=0.975)
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "backlog.png"))
    args = ap.parse_args()

    bl = idata.backlog(args.refresh)
    revenue = idata.quarterly_revenue(args.refresh)
    draw(bl, revenue, args.out)

    commenced = bl.lease_payments.get("Total", 0.0)
    print(f"\n수주잔고 ({bl.as_of})")
    print(f"  ASC 606 잔여 수행의무        ${bl.rpo/B:6.2f}B")
    print(f"    향후 12개월               ${(bl.rpo_next_12m or 0)/B:6.2f}B")
    print(f"    그다음 12개월             ${(bl.rpo_following_12m or 0)/B:6.2f}B")
    print(f"  ASC 842 계약 임대            ${bl.leases/B:6.2f}B")
    print(f"    개시된 임대 최소 수취액     ${commenced/B:6.2f}B")
    print(f"    개시 전                   ${(bl.leases - commenced)/B:6.2f}B "
          f"({(bl.leases - commenced)/bl.leases*100:.0f}%)")
    print(f"  합계                        ${bl.total/B:6.2f}B")
    print(f"\n  투자적격 거래상대 비중 약 {disc.BACKLOG_INVESTMENT_GRADE.value*100:.0f}% "
          f"[{disc.BACKLOG_INVESTMENT_GRADE.src}]")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
