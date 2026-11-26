#!/usr/bin/env python3
"""목표까지 얼마나 남았나 — 회사가 공개한 숫자만으로 재는 진척.

IREN은 목표를 꽤 구체적으로 공개한다. ARR $4B, 용량 0.8GW, CAPEX $15B,
Microsoft Horizon 4개 동. 그런데 보도자료는 목표와 현재를 다른 문단에 떼어
놓기 때문에, 둘을 나란히 두기 전에는 "그래서 몇 퍼센트 왔나"가 안 보인다.
이 차트는 그것만 한다.

눈금 하나는 따로 본다. ARR 막대에는 **시간 경과율**을 같이 찍는다. 목표
시점까지의 달력이 얼마나 지났는지와 공시된 진척을 겹쳐 보면, 남은 기간에
어느 정도 속도가 필요한지가 바로 읽힌다.

주의 — 진척은 **공시 시점 기준**이다. ARR과 Horizon 인도는 분기마다, 또는
사건이 있을 때만 공시되므로 오늘의 실제 값은 이보다 앞서 있을 수 있다.
그 간격을 메우려고 추정치를 넣지는 않는다.

데이터 출처: SEC EDGAR FY2026 10-K · Q1 FY27 보도자료

사용 예:
  python progress.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date

import matplotlib.pyplot as plt

import iren_data as idata
import disclosures as disc

B = 1e9


@dataclass
class Goal:
    name: str
    done: float
    total: float
    unit: str
    color: str
    done_text: str
    left_text: str
    deadline: str = ""
    elapsed: float | None = None   # 시간 경과율 (0~1), 있으면 막대에 표시

    @property
    def ratio(self) -> float:
        return self.done / self.total if self.total else 0.0


def days_left(until: date, today: date) -> int:
    return (until - today).days


def goals(bl, today: date) -> list[Goal]:
    cap = disc.capacity_by_stage()
    total_mw = sum(cap.values())
    commenced = bl.lease_payments.get("Total", 0.0)

    # ARR 시간 경과율: 직전 공시 분기말 → 목표일
    start = disc.PERIOD_END
    span = (disc.ARR_TARGET_DATE - start).days
    elapsed = min(max((today - start).days / span, 0.0), 1.0) if span else None

    d1 = days_left(disc.ARR_TARGET_DATE, today)
    d2 = days_left(disc.ARR_TARGET_SLIP_DATE, today)

    return [
        Goal("가동 ARR", disc.ARR_OPERATING.value, disc.ARR_TARGET.value, "USD",
             idata.CLOUD_COLOR,
             f"${disc.ARR_OPERATING.value/B:,.0f}B 가동",
             f"${(disc.ARR_TARGET.value - disc.ARR_OPERATING.value)/B:,.0f}B 남음",
             f"목표 {disc.ARR_TARGET_DATE}  D-{d1}"
             + (f"  ·  연기 시 {disc.ARR_TARGET_SLIP_DATE}  D-{d2}" if d2 > d1 else ""),
             elapsed),
        Goal("Microsoft Horizon 인도", disc.HORIZON_DELIVERED, disc.HORIZON_TOTAL,
             "동", idata.LEASE_COLOR,
             f"{disc.HORIZON_DELIVERED}개 동 인도",
             f"{disc.HORIZON_TOTAL - disc.HORIZON_DELIVERED}개 동 남음",
             "Horizon 2~4 목표 2026년 4분기 · 유예 2027년 2분기 초"),
        Goal("FY2027 CAPEX 조달", disc.FUNDING_COMMITTED.value,
             disc.CAPEX_REMAINING_FY27.value, "USD", idata.PRICE_COLOR,
             f"${disc.FUNDING_COMMITTED.value/B:,.0f}B 확보",
             f"${disc.FUNDING_TARGET.value/B:,.0f}B 미확보",
             "회사 표현 'subject to market conditions'"),
        Goal("데이터센터 가동 용량", cap["가동"], total_mw, "MW",
             idata.MINING_COLOR,
             f"{cap['가동']:,.0f}MW 가동",
             f"건설 {cap['건설']:,.0f}MW · 개발 {cap['개발']:,.0f}MW",
             "계획 총 전력(gross) 기준. IT MW가 아니다"),
        Goal("수주잔고 개시", commenced, bl.total, "USD", idata.INK_MUTED,
             f"${commenced/B:,.1f}B 개시",
             f"${(bl.total - commenced)/B:,.1f}B 미개시",
             "개시된 임대의 최소 수취액 기준"),
    ]


def draw(items: list[Goal], today: date, out_path):
    fig, (ax,) = idata.figure(height=0.80 + 1.24 * len(items), width=12.0)
    # 오른쪽 끝에 붙는 "→ 남음" 라벨이 도화지 가장자리에 닿지 않게 여백을 준다
    fig.get_layout_engine().set(w_pad=0.10)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=False)
    ax.set_xticks([])

    ys = list(range(len(items)))[::-1]
    for y, g in zip(ys, items):
        ax.barh([y], [1.0], height=0.40, color=idata.GRID, zorder=2)
        ax.barh([y], [g.ratio], height=0.40, color=g.color, zorder=3)

        # 퍼센트는 막대 안에, 자리가 없으면 바로 옆에
        inside = g.ratio > 0.14
        ax.annotate(idata.tex_safe(f"{g.ratio*100:,.0f}%"),
                    (g.ratio / 2 if inside else g.ratio, y),
                    xytext=(0, 0) if inside else (8, 0),
                    textcoords="offset points",
                    ha="center" if inside else "left", va="center",
                    fontsize=13, fontweight="bold",
                    color="white" if inside else g.color, zorder=5)

        ax.annotate(idata.tex_safe(g.name), (0.0, y), xytext=(0, 26),
                    textcoords="offset points", fontsize=12.5,
                    fontweight="bold", color=idata.INK_PRIMARY)
        ax.annotate(idata.tex_safe(f"{g.done_text}  →  {g.left_text}"),
                    (1.0, y), xytext=(0, 26), textcoords="offset points",
                    ha="right", fontsize=10.5, color=idata.INK_SECONDARY)
        if g.deadline:
            ax.annotate(idata.tex_safe(g.deadline), (0.0, y), xytext=(0, -26),
                        textcoords="offset points", fontsize=9.5,
                        color=idata.INK_MUTED)

        if g.elapsed is not None:
            ax.plot([g.elapsed, g.elapsed], [y - 0.30, y + 0.30],
                    color=idata.DEBT_COLOR, linewidth=2.2, zorder=6)
            ax.annotate(idata.tex_safe(f"시간 {g.elapsed*100:,.0f}% 경과"),
                        (g.elapsed, y), xytext=(7, -26),
                        textcoords="offset points", fontsize=9.5,
                        color=idata.DEBT_COLOR, fontweight="bold")

    ax.set_xlim(0, 1.0)
    ax.set_ylim(-0.52, len(items) - 0.34)
    ax.set_yticks([])
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)

    arr = items[0]
    idata.titles(ax, "목표까지 얼마나 남았나",
                 f"{today} 기준 · 진척은 공시 시점 값이다 — "
                 f"ARR은 {disc.AS_OF} 공시, 그 뒤 변화는 반영돼 있지 않다")
    ax.annotate(idata.tex_safe(
        f"가동 ARR은 목표의 {arr.ratio*100:,.0f}%. "
        f"목표일까지 {days_left(disc.ARR_TARGET_DATE, today)}일 안에 "
        f"${(arr.total - arr.done)/B:,.0f}B을 더 켜야 한다 — "
        f"지금 가동 중인 것의 {(arr.total - arr.done)/arr.done:,.0f}배다"),
        (0.0, -0.055), xycoords="axes fraction", fontsize=10.5,
        color=idata.INK_PRIMARY)

    idata.footer(fig, "출처: SEC EDGAR FY2026 10-K · Q1 FY27 보도자료    "
                      "회사가 공개한 목표와 공시된 진척만 쓴다")
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "progress.png"))
    args = ap.parse_args()

    today = date.today()
    items = goals(idata.backlog(args.refresh), today)
    draw(items, today, args.out)

    print(f"\n{today} 기준 진척")
    for g in items:
        print(f"\n  {g.name}")
        print(f"    {g.ratio*100:5.1f}%   {g.done_text} → {g.left_text}")
        if g.deadline:
            print(f"    {g.deadline}")
        if g.elapsed is not None:
            print(f"    시간 경과 {g.elapsed*100:.0f}% "
                  f"({(disc.ARR_TARGET_DATE - disc.PERIOD_END).days}일 중 "
                  f"{(today - disc.PERIOD_END).days}일)")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
