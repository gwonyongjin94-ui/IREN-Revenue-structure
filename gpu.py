#!/usr/bin/env python3
"""GPU는 몇 대인가 — 회사는 대수를 공시하지 않는다.

IREN은 분기마다 GPU 대수를 밝히던 회사였지만, AI 클라우드로 넘어오면서
그 숫자를 멈췄다. FY2026 10-K에도 Q1 FY27 보도자료에도 대수는 없다. 적혀
있는 건 기종뿐이다 — AMD MI350X, NVIDIA H100·H200·B200·B300·GB300·VR200.

대신 돈은 공시된다. 그래서 이 차트는 **공시된 금액**을 먼저 보여 주고,
대수는 가정을 밝힌 역산으로만 붙인다. 역산을 두 가지로 따로 해서 서로
맞는지 보는 것이 이 차트의 핵심이다 — 하나가 틀리면 둘이 어긋난다.

  금액 기준   GPU 하드웨어 장부가액 ÷ 대당 단가 가정
  전력 기준   자금 확보 프로그램 0.3GW(IT) ÷ 대당 소비전력 가정

위    GPU 하드웨어 vs 채굴 하드웨어 장부가액 — 자산이 통째로 바뀌는 그림
가운데 분기별 컴퓨터 하드웨어 구매액
아래  역산한 대수 밴드와 NVIDIA 인도 상한

데이터 출처: SEC EDGAR 10-Q/10-K 유형자산 주석·현금흐름표

사용 예:
  python gpu.py
  python gpu.py --price-per-gpu 25000,55000
"""

from __future__ import annotations

import argparse
from datetime import date

from matplotlib.ticker import FuncFormatter

import iren_data as idata
import disclosures as disc

B = 1e9
M = 1e6

# 대당 올인 단가 가정. 'GPU hardware' 계정에는 서버·네트워킹이 섞여 있으므로
# 칩 단가가 아니라 GPU 1대를 돌리는 데 들어간 설비 전체의 단가로 본다.
# GB300 NVL72 랙(72대)이 대략 $3.0~3.5M, H100 세대는 그보다 낮다.
PRICE_BAND = (30_000.0, 50_000.0)

# 대당 소비전력 가정 (IT 기준). H100 세대가 0.7kW 안팎, GB300이 1.4kW 안팎이다.
POWER_BAND_KW = (0.7, 1.4)

GPU_MODELS = ("AMD MI350X", "NVIDIA H100", "H200", "B200", "B300",
              "GB300", "VR200")
MODELS_SRC = "10K-FY26"


def hardware_values(refresh: bool = False) -> dict[date, dict[str, float]]:
    """유형자산 주석에서 GPU·채굴 하드웨어 장부가액(총액)을 시점별로 모은다."""
    out: dict[date, dict[str, float]] = {}
    for f in idata.filings(refresh):
        try:
            t = idata.rfile(f["acc"],
                            r"Property, plant and equipment.*Schedule of [Pp]roperty",
                            refresh)
        except Exception:
            continue
        dates = [d for _, ds in t.groups for d in ds]
        for ctx, _, vals in t.rows:
            key = {"GPU hardware": "gpu", "Mining hardware": "mining",
                   "Construction in progress": "cip"}.get(ctx)
            if not key:
                continue
            for d, v in zip(dates, vals):
                if v is not None:
                    out.setdefault(d, {}).setdefault(key, v)
    return dict(sorted(out.items()))


# 같은 줄인데 FY2026Q1 공시만 이름이 다르다. 네 분기를 더하면 연간 $1,335M 과
# 정확히 맞으므로 같은 항목이 이름만 바뀐 것으로 본다.
CAPEX_ROWS = ("Payments for computer hardware",
              "Payments for computer hardware prepayments")


def hardware_capex(refresh: bool = False) -> dict[idata.Quarter, float]:
    """분기별 컴퓨터 하드웨어 구매액.

    현금흐름표는 분기가 아니라 **누적**으로 나온다. 10-Q 1분기만 3개월이고
    2·3분기는 6·9개월, 10-K는 12개월이다. 그래서 누적을 받아 차분한다.
    FY2026Q4가 $649M 으로 떨어지는데, 회사가 보도자료에 적은 값과 같다.

    FY2025 이전은 같은 줄 이름이 '선급금'을 가리키다가 바뀌어 분기 합이
    연간과 맞지 않는다. 그래서 라벨이 일정해진 FY2026 이후만 쓴다.
    """
    cumulative: dict[tuple[int, int], float] = {}   # (회계연도, 누적 개월) → 금액
    for f in idata.filings(refresh):
        try:
            t = idata.rfile(f["acc"], r"Statements of Cash Flows", refresh)
        except Exception:
            continue
        offset = 0
        for name, dates in t.groups:
            months = {"3": 3, "6": 6, "9": 9, "12": 12}.get(name.split()[0])
            if months is None or f["period"] not in dates:
                offset += len(dates)
                continue
            col = offset + dates.index(f["period"])
            value = next((v for v in (t.lookup(r, col) for r in CAPEX_ROWS)
                          if v is not None), None)
            offset += len(dates)
            if value is not None:
                fy = idata.fiscal_quarter(f["period"])[0]
                cumulative.setdefault((fy, months), abs(value))

    out: dict[idata.Quarter, float] = {}
    for (fy, months), value in cumulative.items():
        if fy < 2026:
            continue
        quarter = months // 3
        prior = cumulative.get((fy, months - 3), 0.0) if months > 3 else 0.0
        if months > 3 and (fy, months - 3) not in cumulative:
            continue      # 앞 누적이 없으면 차분할 수 없다
        out[(fy, quarter)] = value - prior
    return dict(sorted(out.items()))


def implied_counts(gpu_value: float, price_band, power_band) -> dict[str, tuple]:
    lo_p, hi_p = price_band
    lo_w, hi_w = power_band
    it_watts = disc.IT_MW_FOR_TARGET.value * 1e3   # MW → kW
    return {
        "금액 기준": (gpu_value / hi_p, gpu_value / lo_p),
        "전력 기준": (it_watts / hi_w, it_watts / lo_w),
    }


def draw(values, capex, price_band, power_band, out_path):
    fig, (top, mid, bottom) = idata.figure([1.15, 1.0, 0.95], height=11.0,
                                           width=12.2)

    # --- 위: 장부가액 ----------------------------------------------------
    dates = [d for d in values if "gpu" in values[d]]
    xs = list(range(len(dates)))
    gpu = [values[d].get("gpu", 0) / B for d in dates]
    mining = [values[d].get("mining", 0) / B for d in dates]
    top.bar([x - 0.19 for x in xs], gpu, width=0.36, color=idata.CLOUD_COLOR,
            zorder=3, label="GPU 하드웨어")
    top.bar([x + 0.19 for x in xs], mining, width=0.36, color=idata.MINING_COLOR,
            zorder=3, label="채굴 하드웨어")
    for x, g, m in zip(xs, gpu, mining):
        for off, v in ((-0.19, g), (0.19, m)):
            if v > 0.02:
                top.annotate(idata.tex_safe(f"${v:,.2f}B"), (x + off, v),
                             xytext=(0, 5), textcoords="offset points",
                             ha="center", fontsize=10,
                             color=idata.INK_SECONDARY)
    top.set_xticks(xs)
    top.set_xticklabels([str(d) for d in dates], fontsize=10.5)
    top.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}B"))
    top.legend(loc="upper left", frameon=False, fontsize=10)
    first, last = values[dates[0]].get("gpu", 0), values[dates[-1]].get("gpu", 0)
    idata.titles(top, "GPU 하드웨어 vs 채굴 하드웨어 — 장부가액(총액)",
                 f"GPU는 {first/M:,.0f}M → {last/B:,.2f}B 로 "
                 f"{last/first:,.0f}배가 됐고 채굴은 줄고 있다. "
                 "자산이 통째로 바뀌는 중이다")

    # --- 가운데: 분기별 구매액 ------------------------------------------
    quarters = sorted(capex)
    xs2 = list(range(len(quarters)))
    vals2 = [capex[q] / B for q in quarters]
    mid.bar(xs2, vals2, width=0.6, color=idata.PRICE_COLOR, zorder=3)
    for x, v in zip(xs2, vals2):
        mid.annotate(idata.tex_safe(f"${v:,.2f}B"), (x, v), xytext=(0, 5),
                     textcoords="offset points", ha="center", fontsize=10,
                     color=idata.INK_SECONDARY)
    mid.set_xticks(xs2)
    mid.set_xticklabels([idata.label(q) for q in quarters], fontsize=10.5)
    mid.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.1f}B"))
    idata.titles(mid, "분기별 컴퓨터 하드웨어 구매액",
                 f"직전 분기에만 ${capex[quarters[-1]]/B:,.2f}B 를 샀다 — "
                 f"그 앞 네 분기 합의 {capex[quarters[-1]]/sum(capex[q] for q in quarters[:-1]):,.1f}배다. "
                 "라벨이 일정해진 FY2026 이후만 쓴다", size=13)

    # --- 아래: 역산한 대수 ----------------------------------------------
    gpu_value = values[dates[-1]]["gpu"]
    bands = implied_counts(gpu_value, price_band, power_band)
    notes = {
        "금액 기준": f"GPU 하드웨어 ${gpu_value/B:,.2f}B ÷ 대당 "
                   f"${price_band[0]/1000:,.0f}~{price_band[1]/1000:,.0f}k (가정)",
        "전력 기준": f"자금 확보 프로그램 {disc.IT_MW_FOR_TARGET.value:,.0f}MW(IT) ÷ 대당 "
                   f"{power_band[0]:,.1f}~{power_band[1]:,.1f}kW (가정)",
    }
    ys = list(range(len(bands)))[::-1]
    for y, (name, (lo, hi)) in zip(ys, bands.items()):
        bottom.barh([y], [hi - lo], left=[lo], height=0.42,
                    color=idata.CLOUD_COLOR if y else idata.LEASE_COLOR, zorder=3)
        bottom.annotate(idata.tex_safe(f"{lo/1000:,.0f}k ~ {hi/1000:,.0f}k 대"),
                        ((lo + hi) / 2, y), ha="center", va="center",
                        fontsize=12, fontweight="bold", color="white", zorder=5)
        bottom.annotate(idata.tex_safe(notes[name]), (0.0, y),
                        xycoords=("axes fraction", "data"), xytext=(2, -24),
                        textcoords="offset points", fontsize=9.5,
                        color=idata.INK_SECONDARY)
    cap = disc.NVIDIA_GPU_RIGHT.value
    bottom.axvline(cap, color=idata.DEBT_COLOR, linewidth=1.8, zorder=4)
    bottom.annotate(idata.tex_safe(
        f"NVIDIA 인도 상한 {cap/1000:,.0f}k 대"), (cap, 1.0),
        xycoords=("data", "axes fraction"), xytext=(-6, -14),
        textcoords="offset points", ha="right", fontsize=10,
        color=idata.DEBT_COLOR, fontweight="bold")

    bottom.set_yticks(ys)
    bottom.set_yticklabels(list(bands), fontsize=11.5)
    bottom.set_ylim(-0.75, len(bands) - 0.4)
    bottom.set_xlim(0, cap * 1.12)
    bottom.grid(axis="y", visible=False)
    bottom.grid(axis="x", color=idata.GRID, linewidth=0.8, zorder=0)
    bottom.xaxis.set_major_formatter(
        FuncFormatter(lambda v, _: f"{v/1000:,.0f}k"))
    idata.titles(bottom, "역산한 GPU 대수 — 공시된 숫자가 아니다",
                 "회사는 대수를 공시하지 않는다. 두 가지로 따로 역산해 "
                 "서로 맞는지만 본다. 가정이 결과를 지배하므로 범위로만 읽어야 한다",
                 size=13)
    bottom.annotate(idata.tex_safe(
        "두 밴드가 겹치지 않는 게 정상이다 — 금액 기준은 지금 장부에 있는 몫이고, "
        "전력 기준은 0.3GW 프로그램을 다 채웠을 때다.\n"
        f"그 차이가 남은 CAPEX ${disc.CAPEX_REMAINING_FY27.value/B:,.0f}B 로 "
        "앞으로 더 사야 할 몫이고, NVIDIA 상한은 그보다도 위에 있다."),
        (0.0, -0.30), xycoords="axes fraction", fontsize=10.5,
        color=idata.INK_PRIMARY, linespacing=1.6)

    idata.footer(fig, "출처: SEC EDGAR 10-Q/10-K 유형자산 주석·현금흐름표    "
                      "대수는 공시 수치가 아니라 명시된 가정에 따른 역산이다")
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--price-per-gpu", default=",".join(str(int(x)) for x in PRICE_BAND),
                    help="대당 올인 단가 가정 범위, 예: 25000,55000")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "gpu.png"))
    args = ap.parse_args()

    price_band = tuple(float(x) for x in args.price_per_gpu.split(","))
    values = hardware_values(args.refresh)
    capex = hardware_capex(args.refresh)
    draw(values, capex, price_band, POWER_BAND_KW, args.out)

    print("\n하드웨어 장부가액 (총액)")
    for d, parts in values.items():
        row = "  ".join(f"{k} ${v/B:,.2f}B" for k, v in parts.items())
        print(f"  {d}  {row}")
    print("\n분기별 컴퓨터 하드웨어 구매액")
    for q in sorted(capex):
        print(f"  {idata.label(q)}  ${capex[q]/B:,.2f}B")

    latest = max(d for d in values if "gpu" in values[d])
    bands = implied_counts(values[latest]["gpu"], price_band, POWER_BAND_KW)
    print(f"\n역산한 GPU 대수 — 공시 수치가 아니다 ({latest} 기준)")
    for name, (lo, hi) in bands.items():
        print(f"  {name}  {lo:,.0f} ~ {hi:,.0f} 대")
    print(f"  참고: NVIDIA 인도 상한 {disc.NVIDIA_GPU_RIGHT.value:,.0f}대 "
          f"[{disc.NVIDIA_GPU_RIGHT.src}]")
    print(f"\n보유 기종 [{MODELS_SRC}]: {' · '.join(GPU_MODELS)}")


if __name__ == "__main__":
    idata.use_korean_font()
    main()
