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
# '용량'이라 불리는 숫자가 여섯 개다. 정의와 출처가 제각각이라 섞으면 안 된다.
POWER_SECURED = Figure(5.0, "GW", "10K-FY26",
                       "2026-06-30 기준 '계통연계 계약, 합의서(letters of agreement) "
                       "또는 그에 준하는 것'이 걸린 총 전력. 전부 확정 계약은 아니다")
PIPELINE = Figure(35.0, "GW", "PR-Q1FY27",
                  "개발 파이프라인. 회사가 투기적 총량이라고 명시했다. "
                  "같은 것을 FY2026 10-K는 'multi-GW'라고만 적는다")
NVIDIA_PARTNERSHIP = Figure(5.0, "GW", "10K-FY26",
                            "NVIDIA와의 전략적 제휴로 '시간을 두고' 배치할 수 있는 "
                            "DSX 정렬 AI 인프라 상한. 비구속적이라고 명시")
NVIDIA_GPU_RIGHT = Figure(600_000, "대", "10K-FY26",
                          "NVIDIA 투자권리가 걸린 GPU 인도 상한. 최대 $2.1B 주식 투자권")

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

# Microsoft 계약($9.7B)이 걸린 Childress 내 네 개 동. 인도 진척이 이 회사
# 실행력을 재는 가장 구체적인 눈금이다.
HORIZON_TOTAL = 4
HORIZON_DELIVERED = 1
HORIZON_SRC = "10K-FY26"
HORIZON_NOTE = ("Horizon 1은 2026년 8월 Microsoft 인도·검수 완료. "
                "Horizon 2~4는 2026년 4분기 단계 인도 목표이고, "
                "유예기간은 2027년 2분기 초까지다")
MICROSOFT_CONTRACT = Figure(9.7e9, "USD", "10K-FY26",
                            "2025년 11월 체결, 5년 평균 기간. Horizon 1~4")
NVIDIA_CONTRACT = Figure(3.4e9, "USD", "10K-FY26",
                         "2026년 5월 체결, 5년 클라우드 서비스 계약")

MINING_IMPAIRMENT_FY26 = Figure(638.8e6, "USD", "10K-FY26",
                                "FY2026 자산손상. 채굴기 폐기가 대부분")
CUSTOMER_COUNT = Figure(15, "개", "PR-Q1FY27",
                        "NVIDIA, Microsoft 외 13개사와 계약")

# ----------------------------------------------------------------- 사이트

# 용량은 FY2026 10-K Item 2 Properties 표 그대로다. **gross MW**, 즉 사이트의
# 계획 총 전력이고 랙에 들어가는 IT MW가 아니다. 둘을 섞으면 안 된다 —
# $4B ARR 이 대응하는 0.3GW 는 IT 기준이고, 아래 합계 5.6GW 는 gross 기준이다.
#
# 단계는 10-K 표에 열로 들어 있지 않아 Q1 FY27 보도자료의 서술에서 옮겼다.
# 좌표는 사이트가 속한 지명의 대략적 위치다. 필지 좌표가 아니라 지도에서
# 어느 지역인지 보이게 하는 용도다.
#
#   가동    이미 매출을 내고 있는 사이트
#   건설    착공해 짓는 중
#   개발    부지·전력은 확보했고 아직 짓지 않았다

@dataclass(frozen=True)
class Site:
    name: str          # 표기용 이름
    region: str        # 지도 패널 구분
    lat: float
    lon: float
    mw: float          # 계획 총 전력 (gross)
    stage: str         # 가동 | 건설 | 개발
    note: str = ""


SITES = [
    Site("Canal Flats", "북미", 50.15, -115.85, 30, "가동",
         "최초 사이트. BC Hydro 수력"),
    Site("Prince George", "북미", 53.92, -122.75, 50, "가동",
         "AI 클라우드 GPU 가동"),
    Site("Mackenzie", "북미", 55.34, -123.09, 80, "가동",
         "공랭 개조 + 액랭 신규 착공"),
    Site("Childress", "북미", 34.43, -100.20, 750, "가동",
         "Horizon 1 Microsoft 인도 완료, Horizon 2~4 건설 후반"),
    Site("Sweetwater 1", "북미", 32.47, -100.41, 1400, "건설",
         "액랭 건설 진행"),
    Site("Sweetwater 2", "북미", 32.30, -100.70, 600, "개발"),
    Site("Kiowa", "북미", 34.72, -95.90, 1600, "개발",
         "최대 부지. 오클라호마"),
    Site("Badajoz", "유럽", 38.88, -6.97, 300, "개발",
         "300MW 토목 인허가"),
    Site("Bundey", "오세아니아", -33.95, 139.45, 800, "개발",
         "애들레이드 북동 약 125km. 2028년 전력 투입 목표"),
]
SITES_SRC = "10K-FY26 Item 2 (용량) · PR-Q1FY27 (단계)"

STAGE_ORDER = ["가동", "건설", "개발"]


def capacity_by_stage() -> dict[str, float]:
    out = {k: 0.0 for k in STAGE_ORDER}
    for s in SITES:
        out[s.stage] += s.mw
    return out


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
