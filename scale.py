#!/usr/bin/env python3
"""데이터센터 '규모' 정리 — 같은 말로 불리는 여섯 개의 숫자.

IREN 자료를 읽다 보면 용량이라는 이름으로 35GW, 5GW, 5.6GW, 1.4GW, 0.9GW,
0.8GW, 0.3GW가 번갈아 나온다. 백 배 넘게 차이 나는 숫자들이 전부 '용량'이라
불린다. 어느 것이 땅이고 어느 것이 전기이고 어느 것이 실제로 매출을 내는
랙인지 갈라 두지 않으면, 이 회사 규모에 대해 아무 말이나 할 수 있게 된다.

두 축을 절대 섞지 않는다.

  gross MW   사이트 전체 전력. 변압기·냉각·손실까지 포함한 숫자다
  IT MW      랙에 실제로 들어가는 전력. 매출은 여기에 붙는다

회사는 둘 사이 환산 비율을 공시하지 않는다. 그래서 이 차트도 환산하지 않고,
패널을 나눠 각각의 축에 둔다.

위    gross 기준 — 파이프라인에서 가동까지 좁혀지는 사다리
아래  IT 기준 — 돈이 붙어 있는 용량

데이터 출처: SEC EDGAR FY2026 10-K · Q1 FY27 보도자료

사용 예:
  python scale.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from matplotlib.ticker import FuncFormatter

import iren_data as idata
import disclosures as disc


@dataclass(frozen=True)
class Step:
    name: str
    gw: float
    color: str
    meaning: str
    src: str


def gross_steps() -> list[Step]:
    cap = disc.capacity_by_stage()
    announced = sum(cap.values()) / 1000
    return [
        Step("개발 파이프라인", disc.PIPELINE.value, idata.GRID,
             "부지·전력 후보 총량. 회사가 투기적이라고 명시했고, "
             "10-K는 같은 것을 'multi-GW'라고만 적는다", disc.PIPELINE.src),
        Step("NVIDIA 제휴 상한", disc.NVIDIA_PARTNERSHIP.value, idata.INK_MUTED,
             "시간을 두고 배치 가능한 DSX 정렬 인프라 상한. 비구속적",
             disc.NVIDIA_PARTNERSHIP.src),
        Step("확보 전력", disc.POWER_SECURED.value, idata.PRICE_COLOR,
             "계통연계 계약·합의서 또는 그에 준하는 것이 걸린 전력. "
             "전부 확정 계약은 아니다", disc.POWER_SECURED.src),
        Step("공시 사이트 합계", announced, idata.MINING_COLOR,
             "10-K Item 2 표에 이름과 용량이 적힌 9개 사이트의 계획 전력",
             "10K-FY26"),
        Step("건설 중", cap["건설"] / 1000, idata.CLOUD_COLOR,
             "착공해 짓고 있는 사이트 (Sweetwater 1)", "PR-Q1FY27"),
        Step("가동", cap["가동"] / 1000, idata.LEASE_COLOR,
             "매출을 내고 있는 사이트 4곳의 계획 전력. "
             "지금 켜져 있는 전력이 아니라 그 사이트들의 계획 용량이다",
             "PR-Q1FY27"),
    ]


def it_steps() -> list[Step]:
    return [
        Step("CY2027 목표", disc.IT_MW_TARGET_CY2027.value / 1000, idata.CLOUD_COLOR,
             "2027 역년 말 목표. 추가 CAPEX가 필요할 수 있다고 명시",
             disc.IT_MW_TARGET_CY2027.src),
        Step("자금 확보 프로그램", disc.IT_MW_FOR_TARGET.value / 1000,
             idata.LEASE_COLOR,
             f"${disc.ARR_TARGET.value/1e9:,.0f}B ARR이 대응하는 용량. "
             "'계약됐고 자금도 됐다'고 공시한 유일한 구간",
             disc.IT_MW_FOR_TARGET.src),
    ]


def draw(out_path):
    gross, it = gross_steps(), it_steps()
    fig, (top, bottom) = idata.figure([len(gross), len(it) + 0.9], height=9.6,
                                      width=12.4)

    def panel(ax, steps, title, sub, unit_note, unit="GW"):
        mul = 1.0 if unit == "GW" else 1000.0
        ys = list(range(len(steps)))[::-1]
        ax.barh(ys, [s.gw * mul for s in steps], height=0.52,
                color=[s.color for s in steps], zorder=3)
        for y, s in zip(ys, steps):
            value = s.gw * mul
            ax.annotate(idata.tex_safe(
                f"{value:,.0f}{unit}" if value >= 10 else f"{value:,.2f}{unit}"),
                (value, y), xytext=(8, 1), textcoords="offset points",
                va="center", fontsize=12, fontweight="bold",
                color=idata.INK_PRIMARY)
            ax.annotate(idata.tex_safe(f"{s.meaning}  [{s.src}]"),
                        (value, y), xytext=(8, -14), textcoords="offset points",
                        va="center", fontsize=9, color=idata.INK_SECONDARY)
        ax.set_yticks(ys)
        ax.set_yticklabels([s.name for s in steps], fontsize=11.5)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=idata.GRID, linewidth=0.8, zorder=0)
        ax.set_xlim(0, max(s.gw for s in steps) * mul * 1.7)
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda v, _: f"{v:,.0f}{unit}"))
        ax.set_xlabel(idata.tex_safe(unit_note), fontsize=10,
                      color=idata.INK_PRIMARY, fontweight="bold", loc="right")
        idata.titles(ax, title, sub, size=14)

    panel(top, gross, "gross 기준 — 파이프라인에서 가동까지",
          "위에서 아래로 갈수록 확실해진다. 맨 위는 후보지 목록이고 "
          "맨 아래만 돈이 들어오고 있다",
          "단위: gross — 사이트 전체 전력")
    panel(bottom, it, "IT 기준 — 매출이 붙는 용량",
          "랙에 들어가는 전력. 위 패널과 축이 다르므로 두 숫자를 "
          "나란히 비교하면 안 된다",
          "단위: IT — 랙에 들어가는 전력", unit="MW")

    narrowing = gross[0].gw / gross[-1].gw
    bottom.annotate(idata.tex_safe(
        f"파이프라인 {gross[0].gw:,.0f}GW 와 가동 {gross[-1].gw:,.2f}GW 는 "
        f"{narrowing:,.0f}배 차이다. 둘 다 '용량'이라 불리지만 하나는 후보지 "
        "목록이고 하나는 매출이다.\n"
        "회사는 gross MW와 IT MW 사이 환산 비율을 공시하지 않는다 — "
        "그래서 이 두 패널은 끝까지 합쳐지지 않는다."),
        (0.0, -0.40), xycoords="axes fraction", fontsize=10.5,
        color=idata.INK_PRIMARY, linespacing=1.6)

    idata.footer(fig, "출처: SEC EDGAR FY2026 10-K Item 1·2 · Q1 FY27 보도자료    "
                      "같은 '용량'이라도 기준일과 확정 정도가 다르다")
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(idata.OUT_DIR / "scale.png"))
    args = ap.parse_args()
    draw(args.out)

    print("\ngross 기준")
    for s in gross_steps():
        print(f"  {s.name:16} {s.gw:7,.2f}GW  [{s.src}]  {s.meaning[:52]}")
    print("\nIT 기준 (위와 축이 다르다)")
    for s in it_steps():
        print(f"  {s.name:16} {s.gw:7,.2f}GW  [{s.src}]  {s.meaning[:52]}")
    print(f"\nNVIDIA 투자권리 GPU 상한 {disc.NVIDIA_GPU_RIGHT.value:,.0f}대 "
          f"[{disc.NVIDIA_GPU_RIGHT.src}]")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
