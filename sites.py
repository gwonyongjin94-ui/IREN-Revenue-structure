#!/usr/bin/env python3
"""데이터센터 지도 — 어디가 돌아가고 어디를 짓고 있나.

IREN이 공시한 사이트는 9개, 계획 총 전력은 5.6GW다. 그런데 그중 실제로
매출을 내고 있는 건 네 곳(0.9GW)뿐이고 나머지는 짓는 중이거나 부지만
확보한 상태다. 숫자로만 보면 "5GW 확보"가 커 보이지만, 지도에 단계별로
색을 입히면 어디까지가 현실이고 어디부터가 계획인지가 한눈에 갈린다.

용량은 **gross MW**다. 랙에 들어가는 IT MW가 아니라 사이트 전체 전력이고,
둘은 보통 2~3배 차이가 난다. $4B ARR이 대응하는 0.3GW(IT)와 이 지도의
5.6GW(gross)를 같은 단위로 보면 안 된다.

위    지역별 지도 — 색은 단계, 크기는 계획 용량
아래  단계별 계획 용량 — 가동 중인 몫이 얼마나 되는지

데이터 출처: SEC EDGAR FY2026 10-K Item 2 · Q1 FY27 보도자료 ·
            Natural Earth (배경 지도, 퍼블릭 도메인)

사용 예:
  python sites.py
"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import iren_data as idata
import disclosures as disc

STAGE_COLOR = {
    "가동": idata.LEASE_COLOR,
    "건설": idata.CLOUD_COLOR,
    "개발": idata.INK_MUTED,
}
STAGE_LABEL = {
    "가동": "가동 — 매출이 나온다",
    "건설": "건설 중",
    "개발": "개발 — 부지·전력만 확보",
}

# 패널은 사이트가 모여 있는 곳만 잘라 본다. 북미를 한 장으로 그리면 BC와
# 텍사스 사이의 빈 땅이 화면의 절반을 먹고 라벨이 서로 밟는다.
PANELS = {
    "브리티시컬럼비아": dict(region="북미", extent=(-129, -112, 47.5, 58.5)),
    "텍사스 · 오클라호마": dict(region="북미", extent=(-104.5, -92.5, 28.5, 37.5)),
    "스페인": dict(region="유럽", extent=(-10, 3, 35.5, 44)),
    "남호주": dict(region="오세아니아", extent=(133, 143, -38, -30)),
}

# 가까이 붙은 사이트는 라벨을 수동으로 떼어 놓는다. 자동 배치를 넣을 만큼
# 점이 많지 않다 — 9개뿐이다.
LABEL_OFFSET = {
    "Sweetwater 1": (11, 7),
    "Sweetwater 2": (11, -15),
    "Childress": (12, 4),
    "Kiowa": (13, 4),
    "Mackenzie": (11, 5),
    "Prince George": (11, -4),
}


def marker_size(mw: float) -> float:
    """면적이 용량에 비례하게. 지름에 비례시키면 큰 사이트가 지도를 먹는다."""
    return 26 + mw * 0.22


def draw_panel(ax, title: str, rings, borders) -> None:
    conf = PANELS[title]
    idata.draw_map(ax, rings, conf["extent"], fill="#f0efec", edge="#dedbd4")
    idata.draw_map(ax, borders, conf["extent"], fill="none", edge="#dedbd4",
                   linewidth=0.5)
    ax.set_facecolor("#f7fafc")
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    west, east, south, north = conf["extent"]
    sites = [s for s in disc.SITES
             if s.region == conf["region"] and west <= s.lon <= east
             and south <= s.lat <= north]
    for site in sorted(sites, key=lambda s: -s.mw):
        ax.scatter([site.lon], [site.lat], s=marker_size(site.mw),
                   color=STAGE_COLOR[site.stage], zorder=4,
                   edgecolor="white", linewidth=1.2)
        ax.annotate(idata.tex_safe(f"{site.name}  {site.mw:,.0f}MW"),
                    (site.lon, site.lat),
                    xytext=LABEL_OFFSET.get(site.name, (11, 4)),
                    textcoords="offset points", fontsize=10,
                    color=idata.INK_PRIMARY, zorder=5)

    total = sum(s.mw for s in sites)
    ax.annotate(idata.tex_safe(f"{title}   {total:,.0f}MW · {len(sites)}곳"),
                (0.0, 1.0), xycoords="axes fraction", xytext=(2, 7),
                textcoords="offset points", fontsize=11.5, fontweight="bold",
                color=idata.INK_PRIMARY)


def draw(out_path, refresh: bool = False):
    rings = idata.land(refresh)
    borders = idata.subdivisions(refresh)

    fig = plt.figure(figsize=(12.4, 10.2), dpi=160, layout="constrained")
    fig.patch.set_facecolor(idata.SURFACE)
    fig.get_layout_engine().set(h_pad=0.06, w_pad=0.05, hspace=0.07, wspace=0.06)
    grid = fig.add_gridspec(3, 2, height_ratios=[1.3, 0.92, 0.42])

    for cell, title in zip([grid[0, 0], grid[0, 1], grid[1, 0], grid[1, 1]],
                           PANELS):
        draw_panel(fig.add_subplot(cell), title, rings, borders)

    # --- 아래: 단계별 계획 용량 -------------------------------------------
    bar = fig.add_subplot(grid[2, :])
    idata.style_axes(bar)
    bar.grid(axis="y", visible=False)
    bar.grid(axis="x", color=idata.GRID, linewidth=0.8, zorder=0)

    by_stage = disc.capacity_by_stage()
    total = sum(by_stage.values())
    left = 0.0
    for stage in disc.STAGE_ORDER:
        value = by_stage[stage]
        bar.barh([0], [value], left=left, height=0.5,
                 color=STAGE_COLOR[stage], zorder=3)
        bar.annotate(idata.tex_safe(f"{value:,.0f}MW"), (left + value / 2, 0),
                     ha="center", va="center", fontsize=12, fontweight="bold",
                     color="white", zorder=4)
        bar.annotate(idata.tex_safe(
            f"{STAGE_LABEL[stage]}  ({value/total*100:,.0f}%)"),
            (left + value / 2, -0.26), xytext=(0, 0), textcoords="offset points",
            ha="center", fontsize=9.5, color=idata.INK_SECONDARY, zorder=4)
        left += value

    bar.set_ylim(-0.62, 0.40)
    bar.set_yticks([])
    bar.set_xlim(0, total)
    bar.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}MW"))
    idata.titles(bar, f"단계별 계획 용량 — 합계 {total:,.0f}MW (gross)",
                 f"자금이 확보됐다고 공시된 프로그램은 "
                 f"{disc.IT_MW_FOR_TARGET.value:,.0f}MW(IT), "
                 f"CY2027 목표는 {disc.IT_MW_TARGET_CY2027.value:,.0f}MW(IT)다. "
                 "gross MW와 IT MW는 단위가 다르다", size=13)

    fig.suptitle("IREN 데이터센터 — 어디가 돌아가고 어디를 짓고 있나",
                 fontsize=16, color=idata.INK_PRIMARY, fontweight="bold",
                 x=0.012, ha="left")
    # 제목 줄 오른쪽 빈 자리에 범례를 눕힌다. 지도 네 장이 서로 떨어져 있어서
    # 아래 막대만으로는 색을 되짚기 어렵다
    x = 0.60
    for stage in disc.STAGE_ORDER:
        fig.text(x, 0.978, "●", color=STAGE_COLOR[stage], fontsize=12,
                 va="center")
        fig.text(x + 0.016, 0.978, STAGE_LABEL[stage], fontsize=10,
                 color=idata.INK_SECONDARY, va="center")
        x += 0.016 + len(STAGE_LABEL[stage]) * 0.0098
    idata.footer(fig, "출처: SEC EDGAR FY2026 10-K Item 2 (용량) · "
                      "Q1 FY27 보도자료 (단계) · 배경 지도 Natural Earth    "
                      "좌표는 지명 기준 근사치")
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "sites.png"))
    args = ap.parse_args()
    draw(args.out, args.refresh)

    print(f"\n{'사이트':14} {'지역':10} {'용량':>9}  단계")
    for s in sorted(disc.SITES, key=lambda s: (disc.STAGE_ORDER.index(s.stage), -s.mw)):
        print(f"{s.name:14} {s.region:10} {s.mw:7,.0f}MW  {s.stage}"
              + (f"  — {s.note}" if s.note else ""))
    by_stage = disc.capacity_by_stage()
    total = sum(by_stage.values())
    print(f"\n{'합계':14} {'':10} {total:7,.0f}MW (gross)")
    for stage in disc.STAGE_ORDER:
        print(f"  {stage} {by_stage[stage]:7,.0f}MW ({by_stage[stage]/total*100:4.0f}%)")
    print(f"\n자금 확보 프로그램 {disc.IT_MW_FOR_TARGET.value:,.0f}MW(IT) · "
          f"CY2027 목표 {disc.IT_MW_TARGET_CY2027.value:,.0f}MW(IT) "
          f"[{disc.SITES_SRC}]")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
