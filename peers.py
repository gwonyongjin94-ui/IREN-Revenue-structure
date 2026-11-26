#!/usr/bin/env python3
"""경쟁사 비교 — 누가 비싸고, 누가 빚으로 지었나.

IREN을 혼자 보면 "수주잔고가 시가총액의 4배"처럼 들리는 숫자가 다 싸 보인다.
같은 일을 하는 회사들과 같은 잣대로 재야 그게 업종 평균인지 이 회사만의
특징인지 갈린다.

비교군은 둘로 나눈다.

  채굴 출신   비트코인 채굴로 시작해 AI 데이터센터로 돌린 회사들.
              IREN, Core Scientific, Cipher, TeraWulf, Applied Digital,
              Riot, Hut 8
  순수 AI     처음부터 AI 클라우드로 시작한 회사. CoreWeave
              (Nebius는 외국 사모발행인이라 같은 방식으로 읽히지 않아 뺐다)

두 가지만 본다. 둘 다 SEC 공시와 시세만으로 계산되고, 회사가 정의한 지표
(ARR, 수주잔고)는 쓰지 않는다 — 정의가 회사마다 달라 비교가 안 된다.

  EV / TTM 매출   얼마나 비싼가
  순차입 / EV     얼마나 빚으로 지었나

데이터 출처: SEC EDGAR companyfacts · 각 공시 표지 주식수 · Yahoo Finance

사용 예:
  python peers.py
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from datetime import date

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import iren_data as idata

B = 1e9

# (티커, CIK, 표기명, 분류)
PEERS = [
    ("IREN", "0001878848", "IREN", "채굴 출신"),
    ("CORZ", "0001839341", "Core Scientific", "채굴 출신"),
    ("CIFR", "0001819989", "Cipher", "채굴 출신"),
    ("WULF", "0001083301", "TeraWulf", "채굴 출신"),
    ("APLD", "0001144879", "Applied Digital", "채굴 출신"),
    ("RIOT", "0001167419", "Riot Platforms", "채굴 출신"),
    ("HUT", "0001964789", "Hut 8", "채굴 출신"),
    ("CRWV", "0001769628", "CoreWeave", "순수 AI"),
]

# Nebius(NBIS)는 뺐다. 외국 사모발행인이라 10-Q 대신 20-F/6-K를 내고, 재무제표
# R파일 구조와 표지 주식수가 달라 같은 방식으로 읽히지 않는다. 억지로 다른
# 출처를 섞으면 이 표의 "전부 SEC 공시에서 같은 방식으로" 가 깨진다.

GROUP_COLOR = {"채굴 출신": idata.MINING_COLOR, "순수 AI": idata.CLOUD_COLOR}
SELF = "IREN"

REVENUE_TAGS = ("Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax")
# 현금과 차입은 XBRL 태그로 긁으면 틀린다. 같은 'LongTermDebt' 태그를 회사마다
# 다른 범위로 쓰고, 제한현금을 빼먹거나 중복으로 담는다. 실제로 그렇게 해 보니
# Applied Digital 순차입이 음수로 나왔다. 그래서 재무상태표 **본문**을 읽고
# 줄 이름으로 고른다 — 표시 형식은 회사가 달라도 표현이 비슷하다.
CASH_ROW = re.compile(r"^(cash and cash equivalents|restricted cash|"
                      r"cash, cash equivalents)", re.I)
DEBT_ROW = re.compile(r"(debt|notes payable|convertible|borrowings?|loans? payable|"
                      r"finance lease liabilit)", re.I)
# 합계·소계·비차입 항목은 걸러낸다
SKIP_ROW = re.compile(r"total (liabilities|current|non-?current)|"
                      r"stockholders|shareholders|deferred|operating lease|"
                      r"issuance costs|discount|net of|less:", re.I)


@dataclass
class Peer:
    ticker: str
    name: str
    group: str
    revenue_ttm: float = 0.0
    cash: float = 0.0
    debt: float = 0.0
    shares: float = 0.0
    price: float = 0.0
    as_of: date | None = None
    balance_date: date | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def market_cap(self) -> float:
        return self.price * self.shares

    @property
    def net_debt(self) -> float:
        return self.debt - self.cash

    @property
    def enterprise(self) -> float:
        return self.market_cap + self.net_debt

    @property
    def ev_sales(self) -> float | None:
        return self.enterprise / self.revenue_ttm if self.revenue_ttm else None

    @property
    def debt_share(self) -> float | None:
        """순차입이 기업가치에서 차지하는 비중. 음수면 순현금이다."""
        return self.net_debt / self.enterprise if self.enterprise else None


def _durations(facts: dict, tags, days: tuple[int, int]) -> list[tuple[date, float]]:
    """태그 후보를 순서대로 보고, 기간 길이가 맞는 사실만 모은다."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        unit = gaap.get(tag, {}).get("units", {}).get("USD")
        if not unit:
            continue
        by_end: dict[date, tuple[str, float]] = {}
        for row in unit:
            if "start" not in row:
                continue
            start, end = date.fromisoformat(row["start"]), date.fromisoformat(row["end"])
            if not days[0] <= (end - start).days <= days[1]:
                continue
            filed = row.get("filed", "")
            # 같은 기간이 여러 공시에 나오면 나중 공시가 정정본이다
            if end not in by_end or filed >= by_end[end][0]:
                by_end[end] = (filed, float(row["val"]))
        if by_end:
            return sorted((e, v) for e, (_, v) in by_end.items())
    return []


def balance_items(cik: str, refresh: bool) -> tuple[float, float, date | None, list[str]]:
    """최신 재무상태표에서 (현금, 차입, 기준일, 경고). 줄 이름으로 고른다."""
    notes: list[str] = []
    for f in idata.filings(refresh, cik)[:3]:
        try:
            t = idata.rfile(f["acc"], r"Balance Sheets?", refresh, cik)
        except Exception:
            continue
        cash = debt = 0.0
        for ctx, label, vals in t.rows:
            if not vals or vals[0] is None:
                continue
            value = vals[0]
            if SKIP_ROW.search(label):
                # 'Debt, net of unamortized issuance costs' 처럼 차입이면서
                # net of 가 붙는 줄은 살린다
                if not (DEBT_ROW.search(label) and "net of" in label.lower()
                        and "total" not in label.lower()):
                    continue
            if CASH_ROW.search(label):
                cash += value
            elif DEBT_ROW.search(label) and value > 0:
                debt += value
        if cash or debt:
            return cash, debt, f["period"], notes
    notes.append("재무상태표를 못 읽음")
    return 0.0, 0.0, None, notes


def _instant(facts: dict, tags) -> float | None:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        unit = gaap.get(tag, {}).get("units", {}).get("USD")
        if not unit:
            continue
        rows = [r for r in unit if "start" not in r]
        if rows:
            best = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
            return float(best["val"])
    return None


def quarterly_revenue(facts: dict) -> list[tuple[date, float]]:
    """매출 태그 후보를 **합쳐서** 분기 계열을 만든다.

    한 태그만 보면 안 된다. IREN은 'Revenues' 에 두 분기, 나머지는
    'RevenueFromContractWithCustomer...' 에 들어 있어서, 첫 태그만 읽으면
    분기가 모자라 연간으로 떨어진다.
    """
    merged: dict[date, float] = {}
    for tag in REVENUE_TAGS:
        for end, value in _durations(facts, (tag,), (85, 95)):
            merged.setdefault(end, value)

    # 4분기는 어느 회사도 분기로 공시하지 않는다. 연간에서 1~3분기를 뺀다.
    # 이걸 안 하면 TTM 이 네 분기 연속으로 이어지지 않아 계산이 통째로 막힌다.
    annual: dict[date, float] = {}
    for tag in REVENUE_TAGS:
        for end, value in _durations(facts, (tag,), (350, 380)):
            annual.setdefault(end, value)
    for fy_end, total in annual.items():
        if fy_end in merged:
            continue
        window = [v for e, v in merged.items()
                  if fy_end.replace(year=fy_end.year - 1) < e < fy_end]
        if len(window) == 3:
            merged[fy_end] = total - sum(window)
    return sorted(merged.items())


def revenue_ttm(facts: dict) -> tuple[float, str]:
    """직전 4개 분기 합. 분기 공시가 없으면 최근 연간으로 떨어진다."""
    quarters = quarterly_revenue(facts)
    if len(quarters) >= 4:
        last4 = quarters[-4:]
        span = (last4[-1][0] - last4[0][0]).days
        if span <= 290:            # 네 분기가 실제로 이어져 있는가
            return sum(v for _, v in last4), "분기 4개 합"
    annual = _durations(facts, REVENUE_TAGS, (350, 380))
    if annual:
        return annual[-1][1], f"연간 ({annual[-1][0]})"
    return 0.0, "없음"


def collect(refresh: bool = False) -> list[Peer]:
    out = []
    for ticker, cik, name, group in PEERS:
        p = Peer(ticker, name, group)
        facts = idata.company_facts(cik, refresh)
        p.revenue_ttm, basis = revenue_ttm(facts)
        if basis != "분기 4개 합":
            p.notes.append(f"매출 {basis}")

        p.cash, p.debt, p.balance_date, notes = balance_items(cik, refresh)
        p.notes += notes

        series = idata.shares_outstanding(refresh, cik, limit=3)
        if series:
            p.as_of, p.shares = series[-1]
        if not series:
            p.notes.append("표지 주식수 없음")
        try:
            prices = idata._yahoo(ticker, refresh, years=2)
            p.price = prices[-1][1] if prices else 0.0
        except Exception:
            p.notes.append("주가 없음")
        out.append(p)
    return out


def draw(peers: list[Peer], price_date: date, out_path):
    ranked = sorted((p for p in peers if p.ev_sales), key=lambda p: -p.ev_sales)
    fig, (top, bottom) = idata.figure([1.0, 1.0], height=9.2, width=12.0)

    def bars(ax, values, labels, fmt, title, sub, zero_line=False):
        ys = list(range(len(values)))[::-1]
        colors = [idata.DEBT_COLOR if p.ticker == SELF else GROUP_COLOR[p.group]
                  for p in ranked]
        ax.barh(ys, values, height=0.6, color=colors, zorder=3)
        span = max(values) - min(min(values), 0)
        for y, v, p in zip(ys, values, ranked):
            # 음수 막대라도 길이가 짧으면 라벨을 왼쪽에 두면 y축 이름과 겹친다.
            # 짧은 막대는 무조건 오른쪽에 붙인다.
            at_right = v >= 0 or abs(v) < span * 0.06
            ax.annotate(idata.tex_safe(fmt(v)), (v, y),
                        xytext=(7 if at_right else -7, 0),
                        textcoords="offset points", va="center",
                        ha="left" if at_right else "right", fontsize=10,
                        fontweight="bold" if p.ticker == SELF else "normal",
                        color=idata.INK_PRIMARY if p.ticker == SELF
                        else idata.INK_SECONDARY)
        ax.set_yticks(ys)
        ax.set_yticklabels(labels, fontsize=10.5)
        for tick, p in zip(ax.get_yticklabels(), ranked):
            if p.ticker == SELF:
                tick.set_fontweight("bold")
                tick.set_color(idata.INK_PRIMARY)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=idata.GRID, linewidth=0.8, zorder=0)
        if zero_line:
            ax.axvline(0, color=idata.INK_MUTED, linewidth=1.0, zorder=2)
        idata.titles(ax, title, sub, size=14)

    labels = [f"{p.name}" for p in ranked]
    bars(top, [p.ev_sales for p in ranked], labels,
         lambda v: f"{v:,.1f}x", "EV / 직전 4개 분기 매출",
         "회사가 정의한 ARR·수주잔고가 아니라 실제로 인식된 매출로 잰다")
    top.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}x"))

    shares = [p.debt_share * 100 for p in ranked]
    bars(bottom, shares, labels, lambda v: f"{v:,.0f}%",
         "순차입 / 기업가치",
         "기업가치 중 빚으로 채운 몫. 음수는 순현금 — 들고 있는 현금이 차입보다 많다",
         zero_line=True)
    bottom.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}%"))

    me = next(p for p in ranked if p.ticker == SELF)
    rank = ranked.index(me) + 1
    lev = sorted(ranked, key=lambda p: -(p.debt_share or 0)).index(me) + 1
    miners = [p for p in ranked if p.group == "채굴 출신"]
    med_sales = sorted(p.ev_sales for p in miners)[len(miners) // 2]
    med_lev = sorted(p.debt_share for p in miners)[len(miners) // 2]
    bottom.annotate(idata.tex_safe(
        f"IREN은 매출 배수 {rank}/{len(ranked)}위 ({me.ev_sales:,.1f}x), "
        f"레버리지 {lev}/{len(ranked)}위 ({me.debt_share*100:,.0f}%) — 둘 다 가운데다. "
        f"채굴 출신 {len(miners)}곳의 중앙값은 {med_sales:,.1f}x · "
        f"{med_lev*100:,.0f}% 다.\n"
        "배수가 낮다고 싼 게 아니다. 순차입이 기업가치의 절반 가까이면 "
        "매출이 흔들릴 때 주주 몫이 먼저 사라진다."),
        (0.0, -0.30), xycoords="axes fraction", fontsize=10.5,
        color=idata.INK_PRIMARY, linespacing=1.6)

    idata.footer(fig, f"출처: SEC EDGAR companyfacts · 각 공시 표지 주식수 · "
                      f"Yahoo Finance ({price_date})    "
                      "회계연도·사업구성이 서로 달라 배수를 액면 그대로 비교하면 안 된다")
    fig.savefig(out_path, facecolor=idata.SURFACE)
    print(f"저장 {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(idata.OUT_DIR / "peers.png"))
    args = ap.parse_args()

    peers = collect(args.refresh)
    price_date = idata.latest(idata.price(args.refresh))[0]
    draw(peers, price_date, args.out)

    print(f"\n{'회사':17} {'분류':9} {'TTM매출':>9} {'시총':>8} {'순차입':>8} "
          f"{'EV':>8} {'EV/매출':>8} {'순차입/EV':>9}")
    for p in sorted(peers, key=lambda p: -(p.ev_sales or 0)):
        ev_s = f"{p.ev_sales:7.1f}x" if p.ev_sales else "      —"
        ds = f"{p.debt_share*100:8.0f}%" if p.debt_share is not None else "       —"
        print(f"{p.name:17} {p.group:9} {p.revenue_ttm/B:8.2f}B {p.market_cap/B:7.1f}B "
              f"{p.net_debt/B:7.1f}B {p.enterprise/B:7.1f}B {ev_s} {ds}"
              + ("  ⚠ " + "; ".join(p.notes) if p.notes else ""))


if __name__ == "__main__":
    idata.use_korean_font()
    main()
