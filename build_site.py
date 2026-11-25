#!/usr/bin/env python3
"""docs/index.html — GitHub Pages 대시보드.

차트는 assets/ 에서 복사해 쓴다 (update.sh가 먼저 복사한다). 숫자는
SNAPSHOT.md 와 같은 계산을 쓰되, 여기서는 읽기 편한 카드로 깐다.

사용 예:
  python build_site.py
"""

from __future__ import annotations

import argparse
import html
import shutil
from datetime import datetime, timezone
from pathlib import Path

import iren_data as idata
import disclosures as disc
import valuation as val

B = 1e9
M = 1e6

CHARTS = [
    ("segments.png", "매출 구성의 교체",
     "두 분기 만에 채굴이 사라지고 AI 클라우드가 매출의 88%가 됐다. "
     "아래 패널의 비트코인 가격과 비교하면, 채굴 매출 감소분의 대부분은 "
     "가격이 아니라 스스로 전력을 돌린 결과다."),
    ("backlog.png", "수주잔고 $20.3B 의 구성",
     "잔고의 60%는 아직 개시되지 않은 임대 계약이다. 계약은 됐지만 "
     "데이터센터를 지어야 매출이 된다."),
    ("arr_model.png", "ARR = MW(IT) x MW당 단가",
     "회사 목표가 함의하는 단가와 실제 체결 단가가 60% 수준으로 어긋난다. "
     "ARR 추정의 가장 큰 미지수다."),
    ("funding.png", "자금 — $15B 중 $6B 이 열려 있다",
     "차입 $10B 중 3분의 2가 전환사채다. 주가가 전환가에서 멀어지면 "
     "그냥 빚으로 남는다."),
    ("valuation.png", "적정가격 — 단일 숫자가 아니라 범위",
     "결과는 달성 ARR과 배수에 거의 전적으로 달려 있다. "
     "레버리지가 높아 가정이 조금만 움직여도 주당가치가 크게 흔들린다."),
]

PAGE = """<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IREN 매출 구조와 적정가격</title>
<style>
  :root {{
    --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #8a8985;
    --surface: #fcfcfb; --line: #e6e5e1; --accent: #2a78d6;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--surface); color: var(--ink);
    font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
          "Segoe UI", "Noto Sans KR", sans-serif;
  }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 56px 20px 80px; }}
  h1 {{ font-size: 30px; margin: 0 0 6px; letter-spacing: -0.02em; }}
  .sub {{ color: var(--ink-2); margin: 0 0 8px; }}
  .stamp {{ color: var(--ink-3); font-size: 13px; margin: 0 0 36px; }}
  .cards {{
    display: grid; gap: 12px; margin: 0 0 44px;
    grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
  }}
  .card {{
    border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px;
    background: #fff;
  }}
  .card .k {{ color: var(--ink-3); font-size: 12px; margin-bottom: 4px; }}
  .card .v {{ font-size: 22px; font-weight: 650; letter-spacing: -0.01em; }}
  .card .n {{ color: var(--ink-2); font-size: 12px; margin-top: 2px; }}
  section {{ margin: 0 0 52px; }}
  h2 {{ font-size: 20px; margin: 0 0 6px; letter-spacing: -0.01em; }}
  section p {{ color: var(--ink-2); margin: 0 0 16px; max-width: 72ch; }}
  img {{ width: 100%; border: 1px solid var(--line); border-radius: 10px; }}
  footer {{
    border-top: 1px solid var(--line); padding-top: 20px; color: var(--ink-3);
    font-size: 13px;
  }}
  a {{ color: var(--accent); }}
</style>
<div class="wrap">
  <h1>IREN 매출 구조와 적정가격</h1>
  <p class="sub">비트코인 채굴에서 AI 데이터센터로 옮겨 가는 회사를, 공시된 숫자로만 뜯어본다.</p>
  <p class="stamp">{stamp} · 출처 SEC EDGAR · Yahoo Finance ·
     <a href="https://github.com/{repo}">저장소</a></p>

  <div class="cards">{cards}</div>

  {sections}

  <footer>
    모든 수치는 SEC 공시와 공개 시세에서 가져온다. 배수·마진·조달 구성은 가정이며
    이 페이지에 명시돼 있다. 투자 판단이나 권유가 아니다.
  </footer>
</div>
"""


def card(key: str, value: str, note: str = "") -> str:
    return (f'<div class="card"><div class="k">{html.escape(key)}</div>'
            f'<div class="v">{html.escape(value)}</div>'
            + (f'<div class="n">{html.escape(note)}</div>' if note else "")
            + "</div>")


def build(repo: str, refresh: bool = False) -> str:
    revenue = idata.quarterly_revenue(refresh)
    bl = idata.backlog(refresh)
    bs = idata.balance_sheet(refresh)
    price_date, price = idata.latest(idata.price(refresh))
    _, shares = idata.shares_outstanding(refresh)[-1]
    dil = idata.dilution(refresh)
    _, debts = idata.debt_stack(refresh)

    converts = (sum(d.principal for d in debts if d.kind == "전환사채"),
                dil.get("Convertible notes", 0.0))
    results = [val.evaluate(s, bs["net_debt"], shares, price, converts)
               for s in val.scenarios()]
    band = sorted(max(r.per_share, 0) for r in results)

    q = revenue[-1]
    ev = price * shares + bs["net_debt"]
    cards = "".join([
        card("주가", f"${price:,.2f}", str(price_date)),
        card("시가총액", f"${price*shares/B:,.2f}B", f"{shares/M:,.0f}M주"),
        card("EV", f"${ev/B:,.1f}B", f"순차입 ${bs['net_debt']/B:,.1f}B 포함"),
        card(f"{idata.label(q.quarter)} 매출", f"${q.total/M:,.0f}M",
             f"AI 클라우드 {(q.ai_cloud or 0)/q.total*100:,.0f}%"),
        card("수주잔고", f"${bl.total/B:,.1f}B", f"{bl.as_of}"),
        card("가동 ARR", f"약 ${disc.ARR_OPERATING.value/B:,.0f}B",
             f"목표 ${disc.ARR_TARGET.value/B:,.0f}B"),
        card("EV / 목표 ARR", f"{ev/disc.ARR_TARGET.value:,.1f}x",
             "목표 달성을 전제한 값"),
        card("남은 CAPEX", f"${disc.CAPEX_REMAINING_FY27.value/B:,.0f}B",
             f"미확보 ${disc.FUNDING_TARGET.value/B:,.0f}B"),
        card("주당가치 범위", f"${band[0]:,.0f} ~ ${band[-1]:,.0f}",
             f"중앙 ${band[len(band)//2]:,.0f}"),
    ])

    sections = "".join(
        f'<section><h2>{html.escape(title)}</h2><p>{html.escape(note)}</p>'
        f'<img src="assets/{name}" alt="{html.escape(title)}" loading="lazy">'
        f"</section>"
        for name, title, note in CHARTS
        if (idata.ROOT / "assets" / name).exists()
    )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return PAGE.format(stamp=stamp, repo=repo, cards=cards, sections=sections)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--repo", default="gwonyongjin94-ui/IREN-Revenue-structure")
    ap.add_argument("--out", default=str(idata.ROOT / "docs" / "index.html"))
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.parent / "assets").mkdir(exist_ok=True)
    for name, _, _ in CHARTS:
        src = idata.ROOT / "assets" / name
        if src.exists():
            shutil.copy2(src, out.parent / "assets" / name)
    out.write_text(build(args.repo, args.refresh))
    print(f"저장 {out}")


if __name__ == "__main__":
    main()
