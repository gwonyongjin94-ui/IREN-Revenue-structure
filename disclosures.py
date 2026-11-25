#!/usr/bin/env python3
"""표에서 읽을 수 없는 공시 수치 — 출처를 한 줄씩 적어 둔다.

iren_data.py 는 전부 API에서 가져온다. 그런데 이 사업을 재는 데 꼭 필요한 몇
가지는 재무제표 표에 숫자로 찍히지 않는다. MW당 계약 단가, ARR, 남은 CAPEX
같은 것들이다. 그것들만 여기 모아 둔다. 분기마다 손으로 갱신해야 하므로,
갱신이 필요한 수치와 자동으로 갱신되는 수치가 섞이지 않게 파일을 나눴다.

원칙 두 가지.

  1. 회사가 말한 숫자만 적는다. 애널리스트 추정이나 언론의 해석은 넣지 않는다.
  2. 모든 항목에 `src`를 단다. 출처를 못 적겠으면 그 숫자는 쓰지 않는다.

출처 약칭
  PR-Q1FY27   2026-11-05 Q1 FY27 실적 보도자료 (8-K, EX-99.1,
              accession 0001878848-26-000065)
  10Q-Q1FY27  2026-11-05 10-Q, 2026년 9월 30일 분기
              (accession 0001878848-26-000066)
  10K-FY26    2026-08-27 FY2026 10-K (accession 0001878848-26-000052)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Figure:
    value: float
    unit: str
    src: str
    note: str = ""


AS_OF = date(2026, 11, 5)      # 아래 수치들이 말해진 날
PERIOD_END = date(2026, 9, 30)  # 그 수치들의 기준 분기말

# ----------------------------------------------------------------- 운영 규모

# 매출로 가는 체인의 분모. 'IT MW'는 랙에 실제로 들어가는 전력이고, 확보 전력
# (>5GW)이나 파이프라인(>35GW)과는 자리수가 다르다. 섞어 쓰면 밸류에이션이
# 10배 틀린다.
ARR_OPERATING = Figure(1.0e9, "USD/년", "PR-Q1FY27",
                       "CEO 발언 'operating ARR doubled to a billion'. "
                       "정확한 숫자는 공시되지 않았다")
ARR_TARGET = Figure(4.0e9, "USD/년", "PR-Q1FY27",
                    "'fully contracted and fully funded'. 0.3GW(IT) 프로그램에 대응. "
                    "달성 시점은 2027-01-31, 2027년 2월 말까지 밀릴 수 있다고 명시")
ARR_TARGET_DATE = date(2027, 1, 31)
ARR_TARGET_SLIP_DATE = date(2027, 2, 28)

IT_MW_FOR_TARGET = Figure(300, "MW(IT)", "PR-Q1FY27",
                          "$4B ARR 목표가 대응하는 용량 (각주 5)")
IT_MW_TARGET_CY2027 = Figure(800, "MW(IT)", "PR-Q1FY27",
                             "2027 역년 말 목표 (각주 12). 추가 CAPEX가 필요할 수 있다고 명시")
POWER_SECURED = Figure(5.0, "GW", "PR-Q1FY27", "확보 전력. IT 용량이 아니다")
PIPELINE = Figure(35.0, "GW", "PR-Q1FY27", "개발 파이프라인. 투기적 총량이라고 회사가 명시")

# ----------------------------------------------------------------- 계약 단가

# 분기 후 체결된 두 계약의 MW(IT)당 연매출. 밸류에이션의 핵심 가정이 이 범위다.
REVENUE_PER_MW_SHORT = Figure(40e6, "USD/MW(IT)/년", "PR-Q1FY27",
                              "분기 후 체결한 단기 계약")
REVENUE_PER_MW_5Y = Figure(22e6, "USD/MW(IT)/년", "PR-Q1FY27",
                           "분기 후 체결한 5년 계약. 고객 선급금이 관련 GPU CAPEX의 "
                           "90%를 덮는다")
PRICING_CHANGE_3Y = Figure(0.11, "비율", "PR-Q1FY27", "3년 계약 단가, ARR 가중 (각주 6)")
PRICING_CHANGE_5Y = Figure(0.12, "비율", "PR-Q1FY27", "5년 계약 단가, ARR 가중 (각주 6)")

# ----------------------------------------------------------------- 수익성

AI_CLOUD_GROSS_MARGIN = Figure(0.86, "비율", "PR-Q1FY27", "Q1 FY27 AI 클라우드 매출총이익률")
ADJ_EBITDA = {              # 회계연도·분기 → (조정 EBITDA, 마진)
    (2027, 1): (66e6, 0.29),
    (2026, 4): (19e6, 0.14),
}
ADJ_EBITDA_SRC = "PR-Q1FY27"
CASH_OPEX = {               # SG&A + R&D − 주식보상
    (2027, 1): 118e6,
    (2026, 4): 85e6,
}
CASH_OPEX_GUIDE_NEXT = (50e6, 60e6)   # Q2 FY27 증가폭 가이던스
CASH_OPEX_SRC = "PR-Q1FY27"

DC_ASSET_LIFE_YEARS = Figure(20, "년", "PR-Q1FY27",
                             "$6B 데이터센터 자산의 내용연수 (각주 10)")
DC_ASSETS = Figure(6.0e9, "USD", "PR-Q1FY27", "건물·건설중자산·토지 순액")

# ----------------------------------------------------------------- 자금

# FY27 남은 CAPEX와 그 조달 계획. '$9B 확보 / $6B 미확보'의 간격이 이 회사
# 주가의 변동성을 설명하는 가장 큰 변수다.
CAPEX_REMAINING_FY27 = Figure(15.0e9, "USD", "PR-Q1FY27",
                              "2026-09-30 기준 FY27 남은 CAPEX, 데이터센터와 GPU 합계 (각주 11)")
FUNDING_COMMITTED = Figure(9.0e9, "USD", "PR-Q1FY27",
                           "현금 + 약정된 GPU 금융 + 고객 선급금 (각주 12)")
FUNDING_TARGET = Figure(6.0e9, "USD", "PR-Q1FY27",
                        "GPU 금융·선급금·데이터센터 금융 등으로 '목표'하는 금액. "
                        "'subject to market conditions' 라고 명시 (각주 12)")

BACKLOG_INVESTMENT_GRADE = Figure(2 / 3, "비율", "PR-Q1FY27",
                                  "수주잔고 중 투자적격 등급 거래상대 비중, 약 2/3")

# ----------------------------------------------------------------- 사업 전환

MINING_IMPAIRMENT_FY26 = Figure(638.8e6, "USD", "10K-FY26",
                                "FY2026 자산손상. 채굴기 폐기가 대부분")
CUSTOMER_COUNT = Figure(15, "개", "PR-Q1FY27",
                        "NVIDIA, Microsoft 외 13개사와 계약")

# 사이트 상태는 MW가 공시되지 않아 정성 서술만 가능하다. 차트에 쓰지 않고
# README의 서술에만 쓴다.
SITE_STATUS = {
    "Horizon 1": "Microsoft에 인도 완료 (Q1 FY27)",
    "Horizon 2-4": "건설 후반",
    "Childress / Mackenzie": "공랭식 개조 진행",
    "Sweetwater 1": "액침·수랭 건설 진행",
    "Sweetwater 2 / Kiowa / Bundey": "개발 초기",
    "Badajoz (스페인)": "300MW 개발 토목 인허가",
}
SITE_STATUS_SRC = "PR-Q1FY27"


def check() -> list[str]:
    """공시 수치끼리 어긋나는 데가 없는지 본다. 손으로 옮긴 값이라 필요하다."""
    problems = []
    implied = ARR_TARGET.value / IT_MW_FOR_TARGET.value / 1e6
    if not 5 <= implied <= 60:
        problems.append(f"$4B ARR / 300MW = MW당 ${implied:.1f}M — 계약 단가 범위를 벗어난다")
    if FUNDING_COMMITTED.value + FUNDING_TARGET.value != CAPEX_REMAINING_FY27.value:
        problems.append("확보 + 목표 조달액이 남은 CAPEX와 맞지 않는다")
    return problems


if __name__ == "__main__":
    print(f"기준: {PERIOD_END} 분기, {AS_OF} 공시\n")
    rows = [
        ("가동 ARR", ARR_OPERATING), ("목표 ARR", ARR_TARGET),
        ("목표 대응 용량", IT_MW_FOR_TARGET), ("CY2027 용량 목표", IT_MW_TARGET_CY2027),
        ("MW당 단가 (5년)", REVENUE_PER_MW_5Y), ("MW당 단가 (단기)", REVENUE_PER_MW_SHORT),
        ("남은 FY27 CAPEX", CAPEX_REMAINING_FY27), ("확보 자금", FUNDING_COMMITTED),
        ("미확보 자금", FUNDING_TARGET),
    ]
    for name, f in rows:
        v = f"{f.value/1e9:,.2f}B" if f.value > 1e8 else f"{f.value:,.0f}"
        print(f"  {name:18} {v:>10} {f.unit:16} [{f.src}]")
    issues = check()
    print("\n정합성:", "이상 없음" if not issues else "")
    for p in issues:
        print("  ·", p)
