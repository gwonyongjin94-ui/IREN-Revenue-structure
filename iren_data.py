#!/usr/bin/env python3
"""IREN 데이터 계층 — 전부 1차 출처에서 가져온다.

세 곳에서만 읽는다.

  SEC EDGAR    공시 재무제표. 분기 세그먼트 매출, 부채 스택, 수주잔고, 주식수.
  Yahoo Finance 주가 (IREN), 비트코인 가격 (BTC-USD).
  disclosures.py 수치로 공시되지 않아 표에서 읽을 수 없는 운영 지표
               (ARR, MW, MW당 단가) — 출처를 한 줄씩 적어 뒀다.

SEC의 XBRL은 세그먼트 차원을 companyfacts API로 돌려주지 않는다. 그래서
companyconcept 대신 각 공시의 **재무제표 R파일**(FilingSummary.xml이 목록을
들고 있는, 뷰어가 쓰는 작은 HTML 표)을 긁는다. 10-Q 하나에서 당기 3개월과
전년 동기 3개월이 같이 나오므로, 10-Q 세 개와 10-K 두 개로 FY2025Q1 이후
모든 분기가 채워진다. 4분기는 연간에서 1~3분기를 뺀 값이다.

SEC는 요청마다 연락처가 담긴 User-Agent를 요구한다. 환경변수로 넘긴다:

  export SEC_USER_AGENT="이름 you@example.com"
"""

from __future__ import annotations

import html
import json
import os
import re
import time

import requests
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
DATA_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)
CACHE_MAX_AGE_H = 12

# --- 색: dataviz 카테고리 팔레트(light). 색은 순위가 아니라 사업에 귀속된다 ----
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8985"
SURFACE = "#fcfcfb"
GRID = "#e6e5e1"

CLOUD_COLOR = "#2a78d6"    # slot 1 blue   — AI 클라우드
MINING_COLOR = "#eb6834"   # slot 2 orange — 비트코인 채굴
LEASE_COLOR = "#1baf7a"    # slot 3 aqua   — 코로케이션 임대
PRICE_COLOR = "#4a3aa7"    # slot 7 violet — 주가
DEBT_COLOR = "#e34948"     # slot 8 red    — 차입·자금부족
BTC_COLOR = "#8a8985"      # 회색          — 비트코인 가격(배경 지표)

CIK = "0001878848"  # IREN Limited (구 Iris Energy)
TICKER = "IREN"
# `or` 를 쓴다. Actions가 시크릿이 없는 환경변수를 빈 문자열로 넘기므로
# os.environ.get(이름, 기본값) 은 기본값이 아니라 "" 를 돌려준다. 그러면 SEC가
# User-Agent 없는 요청으로 보고 403을 준다.
SEC_UA = (os.environ.get("SEC_USER_AGENT")
          or "IREN-Revenue-Structure research@example.com")
SUBMISSIONS = f"https://data.sec.gov/submissions/CIK{CIK}.json"
CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"
ARCHIVE = f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

Series = list[tuple[date, float]]
Quarter = tuple[int, int]  # (회계연도, 분기) — 회계연도는 6월 결산


# ------------------------------------------------------------------ 스타일

def use_korean_font() -> None:
    """한글 라벨이 두부(□)로 깨지지 않도록 사용 가능한 한글 폰트를 잡는다."""
    from matplotlib import font_manager
    import matplotlib.pyplot as plt
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in ("Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic",
                      "Noto Sans KR", "AppleGothic", "Arial Unicode MS"):
        if candidate in installed:
            plt.rcParams["font.family"] = candidate
            break
    plt.rcParams["axes.unicode_minus"] = False


def style_axes(ax) -> None:
    """격자와 축선은 뒤로 물리고, 데이터가 앞에 오게 한다."""
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9.5, length=0)
    ax.margins(x=0.02)


def tex_safe(text: str) -> str:
    """matplotlib이 $...$ 를 수식으로 파싱하는 걸 막는다."""
    return text.replace("$", r"\$")


def label(q: Quarter) -> str:
    return f"FY{str(q[0])[2:]}Q{q[1]}"


# --------------------------------------------------------------- 가져오기

def _get(url: str, *, json_accept: bool = False) -> bytes:
    """SEC 요청. requests 기본 헤더를 그대로 쓴다.

    urllib로 `Accept-Encoding: identity` 를 보내면 데이터센터 IP에서 403이
    돌아온다 (로컬에서는 통과한다). SEC의 fair access 정책이 압축 응답을
    받을 수 있는 클라이언트를 전제하기 때문으로 보인다. requests 기본값은
    gzip·deflate 를 받겠다고 알리므로 그대로 둔다.
    """
    headers = {"User-Agent": SEC_UA}
    if json_accept:
        headers["Accept"] = "application/json"
    r = requests.get(url, timeout=60, headers=headers)
    if r.status_code == 403:
        raise PermissionError(
            f"SEC가 403으로 막았다. User-Agent 를 확인한다: {SEC_UA!r}\n"
            "  · '이름 메일주소' 형식이어야 한다\n"
            "  · 주소에 github.com 계열 도메인이 들어가면 거부된다 "
            "(users.noreply.github.com 확인)\n"
            "  · SEC_USER_AGENT 환경변수로 넘긴다")
    r.raise_for_status()
    return r.content


def _cached(name: str, fetch, refresh: bool = False, *, text: bool = False):
    """디스크 캐시. 외부를 두 번 두드리지 않는다."""
    path = DATA_DIR / (name if "." in name else f"{name}.json")
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < CACHE_MAX_AGE_H * 3600
    if fresh and not refresh:
        return path.read_text(errors="replace") if text else json.loads(path.read_text())
    payload = fetch()
    path.write_text(payload if text else json.dumps(payload))
    return payload


# --------------------------------------------------------------- R파일 파서

@dataclass(frozen=True)
class Table:
    """R파일 하나. 단위는 이미 곱해 뒀다 (USD)."""
    title: str
    groups: list[tuple[str, list[date]]]   # ("3 Months Ended", [기간말, ...])
    rows: list[tuple[str, str, list[float | None]]]  # (세그먼트 맥락, 항목, 값)

    def column(self, group: str, period_end: date) -> int | None:
        """그룹과 기간말로 열 번호를 찾는다. 열 순서가 바뀌어도 맞는다."""
        offset = 0
        for name, dates in self.groups:
            if group.lower() in name.lower():
                for i, d in enumerate(dates):
                    if d == period_end:
                        return offset + i
            offset += len(dates)
        return None

    def value(self, label: str, col: int, context: str = "") -> float | None:
        want_label, want_ctx = label.lower(), context.lower()
        for ctx, lab, vals in self.rows:
            if lab.lower() != want_label or ctx.lower() != want_ctx:
                continue
            return vals[col] if col < len(vals) else None
        return None


_MONTHS = {m: i + 1 for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def _parse_date(s: str) -> date | None:
    m = re.match(r"([A-Z][a-z]{2})\.?\s+(\d{1,2}),\s*(\d{4})", s.strip())
    if not m:
        return None
    return date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))


def _cells(row_html: str) -> list[str]:
    out = []
    for cell in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", row_html):
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", cell)
        text = re.sub(r"<[^>]+>", " ", text)
        out.append(re.sub(r"[\s\xa0]+", " ", html.unescape(text)).strip())
    return out


def _colspans(row_html: str) -> list[tuple[str, int]]:
    out = []
    for attrs, inner in re.findall(r"(?is)<th([^>]*)>(.*?)</th>", row_html):
        span = re.search(r'colspan="?(\d+)', attrs)
        text = re.sub(r"[\s\xa0]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inner))).strip()
        out.append((text, int(span.group(1)) if span else 1))
    return out


_NUM = re.compile(r"^\(?\$?\s*-?[\d,]+(\.\d+)?\)?%?$")


def _number(s: str) -> float | None:
    s = s.strip()
    if not s or s in {"", "—", "–", "-"} or not _NUM.match(s):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


# 값이 비어 있는 행은 두 가지다. 세그먼트·축 블록을 여는 머리행(다음 행들의
# 맥락이 된다)과, 그냥 소제목인 행. 구분 규칙은 꼬리표다 — 소제목은 콜론으로
# 끝나고("Revenue:"), XBRL 추상행은 대괄호 꼬리를 단다("... [Line Items]").
_NOT_CONTEXT = re.compile(r":$|\[(Line Items|Abstract|Roll Forward|Member)\]$", re.I)

# 금액이 아닌 행 — 표 머리의 단위를 곱하면 안 된다
_UNITLESS = re.compile(r"\(in (shares|USD per share|segment)\)|per share|shares\)$|"
                       r"shares outstanding|interest rate|number of", re.I)


def filings(refresh: bool = False) -> list[dict]:
    """정기공시 목록 — 최근 것부터. (form, period, accession)"""
    raw = _cached("sec_submissions", lambda: json.loads(_get(SUBMISSIONS, json_accept=True)), refresh)
    recent = raw["filings"]["recent"]
    out = []
    for form, filed, period, acc in zip(recent["form"], recent["filingDate"],
                                        recent["reportDate"], recent["accessionNumber"]):
        if form not in ("10-Q", "10-K"):
            continue
        out.append({"form": form, "filed": date.fromisoformat(filed),
                    "period": date.fromisoformat(period), "acc": acc.replace("-", "")})
    return out


def rfile(acc: str, pattern: str, refresh: bool = False) -> Table:
    """공시 하나의 R파일을 이름으로 찾아 표로 돌려준다.

    pattern은 FilingSummary.xml의 ShortName에 걸리는 정규식이다. R번호는
    공시마다 달라지므로 번호로 찾지 않는다. 못 찾으면 바로 터뜨린다 — 조용히
    빈 표를 돌려주면 차트가 거짓말을 하게 된다.
    """
    summary = _cached(f"summary_{acc}.xml",
                      lambda: _get(f"{ARCHIVE}/{acc}/FilingSummary.xml").decode("utf-8", "replace"),
                      refresh, text=True)
    want = re.compile(pattern, re.I)
    target = None
    for block in re.findall(r"(?is)<Report[^>]*>(.*?)</Report>", summary):
        name = re.search(r"(?is)<ShortName>(.*?)</ShortName>", block)
        fn = re.search(r"(?is)<HtmlFileName>(.*?)</HtmlFileName>", block)
        if name and fn and want.search(html.unescape(name.group(1))):
            target = (fn.group(1), html.unescape(name.group(1)))
            break
    if target is None:
        raise LookupError(f"{acc}: '{pattern}' 에 맞는 R파일이 없다")

    fn, short = target
    raw = _cached(f"rfile_{acc}_{fn}",
                  lambda: _get(f"{ARCHIVE}/{acc}/{fn}").decode("utf-8", "replace"),
                  refresh, text=True)

    rows_html = re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", raw)
    if not rows_html:
        raise ValueError(f"{acc}/{fn}: 표가 비어 있다")

    title = _cells(rows_html[0])[0] if rows_html else short
    scale = 1.0
    if "in Thousands" in title:
        scale = 1e3
    elif "in Millions" in title:
        scale = 1e6
    elif "in Billions" in title:
        scale = 1e9

    # 머리 2행: 기간 그룹(colspan)과 날짜. 그룹이 없는 잔액 표도 있다.
    groups: list[tuple[str, list[date]]] = []
    header_dates: list[date] = []
    body_start = 0
    for i, rh in enumerate(rows_html[:3]):
        dates = [d for d in (_parse_date(c) for c in _cells(rh)) if d]
        if dates:
            header_dates = dates
            body_start = i + 1
            break
    spans = [(t, n) for t, n in _colspans(rows_html[0])[1:]] if rows_html else []
    if spans and sum(n for _, n in spans) == len(header_dates):
        off = 0
        for name, n in spans:
            groups.append((name, header_dates[off:off + n]))
            off += n
    else:
        groups.append(("", header_dates))

    rows: list[tuple[str, str, list[float | None]]] = []
    context = ""
    for rh in rows_html[body_start:]:
        cells = _cells(rh)
        if not cells:
            continue
        label, rest = cells[0], cells[1:]
        values = [_number(c) for c in rest]
        if label and all(v is None for v in values):
            if not _NOT_CONTEXT.search(label):
                context = label
            continue
        # 금액에만 단위를 곱한다. 퍼센트·주식수·주당금액은 표 머리의
        # '$ in Millions' 와 무관하다 — 곱하면 3.87% 가 387만이 되고,
        # 가중평균 주식수 3.99억이 3.99경이 된다.
        unitless = bool(_UNITLESS.search(label))
        scaled = [None if v is None else (v if unitless or "%" in raw else v * scale)
                  for raw, v in zip(rest, values)]
        rows.append((context, label, scaled))
    return Table(title=title, groups=groups, rows=rows)


# --------------------------------------------------------------- 분기 매출

def fiscal_quarter(period_end: date) -> Quarter:
    """기간말 → (회계연도, 분기). IREN은 6월 결산이다."""
    fy = period_end.year + 1 if period_end.month >= 7 else period_end.year
    q = {9: 1, 12: 2, 3: 3, 6: 4}.get(period_end.month)
    if q is None:
        raise ValueError(f"분기말이 아니다: {period_end}")
    return (fy, q)


def quarter_end(q: Quarter) -> date:
    fy, n = q
    return {1: date(fy - 1, 9, 30), 2: date(fy - 1, 12, 31),
            3: date(fy, 3, 31), 4: date(fy, 6, 30)}[n]


def prev_quarter(q: Quarter) -> Quarter:
    return (q[0] - 1, 4) if q[1] == 1 else (q[0], q[1] - 1)


@dataclass
class Revenue:
    quarter: Quarter
    total: float
    mining: float | None = None
    ai_cloud: float | None = None
    ai_services: float | None = None     # GPU 시간당 과금 (ASC 606)
    ai_lease: float | None = None        # 코로케이션 임대 (ASC 842)
    source: str = ""
    own_period: bool = False             # 그 분기를 당기로 보고한 공시에서 왔는가

    @property
    def end(self) -> date:
        return quarter_end(self.quarter)


# 손익계산서 본문의 세그먼트 블록 이름은 공시마다 조금씩 다르다.
_MINING_CTX = ("bitcoin mining", "bitcoin mining revenue")
_CLOUD_CTX = ("ai cloud", "ai cloud services")


def _segment_from_ops(t: Table, col: int) -> tuple[float | None, float | None]:
    """손익계산서 R파일에서 (채굴, AI클라우드) 매출을 뽑는다.

    두 가지 표기를 모두 받는다.
      FY2027Q1 이후: 본문에 'AI Cloud Revenue' / 'Bitcoin Mining revenue' 두 줄
      그 이전:       본문 아래에 세그먼트 블록이 붙고 각 블록에 'Total revenue'
    """
    mining = t.value("Bitcoin Mining revenue", col)
    cloud = t.value("AI Cloud Revenue", col)
    if mining is None:
        for ctx in _MINING_CTX:
            mining = mining or t.value("Total revenue", col, ctx)
    if cloud is None:
        for ctx in _CLOUD_CTX:
            cloud = cloud or t.value("Total revenue", col, ctx)
    return mining, cloud


def quarterly_revenue(refresh: bool = False) -> list[Revenue]:
    """FY2025Q1 이후 모든 분기의 세그먼트 매출. 분기말 순서."""
    out: dict[Quarter, Revenue] = {}
    annual: dict[int, tuple[float, float | None, float | None]] = {}

    for f in filings(refresh):
        if f["form"] == "10-Q":
            t = rfile(f["acc"], r"Statements of Operations and Comprehensive", refresh)
            for d in next((ds for name, ds in t.groups if "3 month" in name.lower()),
                          t.groups[0][1]):
                col = t.column("3 Month", d)
                if col is None:
                    continue
                total = t.value("Total revenue", col)
                if total is None:
                    continue
                mining, cloud = _segment_from_ops(t, col)
                q = fiscal_quarter(d)
                # 한 분기가 두 공시에 나온다 — 당기 보고서와, 다음 해 같은 분기
                # 보고서의 전년 동기 열. 당기 쪽을 쓴다. FY2027Q1부터 회사가
                # 반올림 단위를 천 → 백만으로 바꿨으므로, 전년 동기 열을 쓰면
                # FY2026Q1이 $240.3M 대신 $240M 이 되고 그 오차가 연간에서
                # 역산하는 4분기로 전가된다.
                own = d == f["period"]
                if q not in out or (own and not out[q].own_period):
                    out[q] = Revenue(q, total, mining, cloud, source=f["acc"], own_period=own)
        else:
            t = rfile(f["acc"], r"Statements of Operations and Comprehensive", refresh)
            for d in next((ds for name, ds in t.groups if "12 month" in name.lower()),
                          t.groups[0][1]):
                col = t.column("12 Month", d)
                if col is None:
                    continue
                total = t.value("Total revenue", col)
                if total is None:
                    continue
                mining, cloud = _segment_from_ops(t, col)
                annual.setdefault(d.year, (total, mining, cloud))

    # 4분기는 공시되지 않는다. 연간에서 1~3분기를 뺀다.
    for fy, (total, mining, cloud) in annual.items():
        q4 = (fy, 4)
        first3 = [out.get((fy, n)) for n in (1, 2, 3)]
        if q4 in out or any(r is None for r in first3):
            continue
        out[q4] = Revenue(
            q4,
            total - sum(r.total for r in first3),
            mining - sum(r.mining for r in first3) if mining is not None
            and all(r.mining is not None for r in first3) else None,
            cloud - sum(r.ai_cloud for r in first3) if cloud is not None
            and all(r.ai_cloud is not None for r in first3) else None,
            source=f"FY{fy} 연간 − 1~3분기",
        )

    # AI 클라우드 내부 분해(서비스/임대)는 매출 주석에만 있다. 최신 분기만 필요하다.
    latest = max(out)
    try:
        t = rfile(out[latest].source, r"Disaggregation of Revenue", refresh)
        col = t.column("3 Month", quarter_end(latest)) or 0
        out[latest].ai_services = t.value("Total AI Cloud revenue", col, "AI Cloud Services")
        out[latest].ai_lease = t.value("Total AI Cloud revenue", col, "AI Cloud Lease")
    except (LookupError, ValueError):
        pass

    return [out[q] for q in sorted(out)]


def quarterly_concept(tag: str, refresh: bool = False,
                      taxonomy: str = "us-gaap") -> dict[Quarter, float]:
    """XBRL 태그 하나의 분기값. 세그먼트 차원이 없는 항목은 이 API가 더 깔끔하다.

    companyconcept은 기간 길이를 섞어 돌려준다 (3개월·6개월·9개월·연간). 85~95일
    구간만 남겨 3개월짜리를 고른다. 같은 분기가 여러 공시에 나오면 나중 공시가
    정정본이므로 뒤에 온 값을 쓴다.
    """
    def go():
        return json.loads(_get(CONCEPT.format(cik=CIK, taxonomy=taxonomy, tag=tag),
                               json_accept=True))

    raw = _cached(f"concept_{taxonomy}_{tag.lower()}", go, refresh)
    out: dict[Quarter, float] = {}
    for unit in raw["units"].values():
        for row in sorted(unit, key=lambda r: r.get("filed", "")):
            if "start" not in row:
                continue
            start, end = date.fromisoformat(row["start"]), date.fromisoformat(row["end"])
            if not 85 <= (end - start).days <= 95:
                continue
            try:
                out[fiscal_quarter(end)] = float(row["val"])
            except ValueError:
                continue   # 분기말이 아닌 구간
    return out


def quarterly_line(pattern: str, label: str, context: str = "",
                   refresh: bool = False) -> dict[Quarter, float]:
    """주석 R파일의 한 줄을 분기 시계열로. companyconcept이 빠뜨리는 항목에 쓴다.

    10-Q 하나가 당기와 전년 동기를 같이 담으므로, 10-Q 네 개면 8개 분기가 찬다.
    주식보상처럼 손익계산서 본문에 없고 주석에만 있는 항목이 그런 경우다.
    """
    out: dict[Quarter, float] = {}
    for f in filings(refresh):
        try:
            t = rfile(f["acc"], pattern, refresh)
        except (LookupError, ValueError):
            continue
        dates = next((ds for name, ds in t.groups if "3 month" in name.lower()), [])
        for d in dates:
            col = t.column("3 Month", d)
            if col is None:
                continue
            v = t.value(label, col, context)
            if v is None:
                continue
            q = fiscal_quarter(d)
            if q not in out or d == f["period"]:
                out[q] = v
    return out


def annual_revenue(refresh: bool = False) -> dict[int, tuple[float, float | None, float | None]]:
    """회계연도 → (총매출, 채굴, AI클라우드). 10-K 두 개가 FY2023까지 덮는다."""
    out: dict[int, tuple[float, float | None, float | None]] = {}
    for f in filings(refresh):
        if f["form"] != "10-K":
            continue
        t = rfile(f["acc"], r"Statements of Operations and Comprehensive", refresh)
        dates = next((ds for name, ds in t.groups if "12 month" in name.lower()), t.groups[0][1])
        for d in dates:
            col = t.column("12 Month", d)
            total = t.value("Total revenue", col) if col is not None else None
            if total is None:
                continue
            mining, cloud = _segment_from_ops(t, col)
            out.setdefault(d.year, (total, mining, cloud))
    return out


# --------------------------------------------------------------- 수주잔고

@dataclass
class Backlog:
    as_of: date
    rpo: float               # ASC 606 잔여 수행의무 (AI 클라우드 서비스)
    leases: float            # ASC 842 계약 임대 총액 (개시 전 포함)
    lease_payments: dict[str, float]   # 개시된 임대의 회계연도별 최소 수취액
    rpo_next_12m: float | None = None
    rpo_following_12m: float | None = None

    @property
    def total(self) -> float:
        return self.rpo + self.leases


def backlog(refresh: bool = False) -> Backlog:
    """수주잔고의 두 다리를 공시에서 직접 읽는다.

    IREN이 보도자료에 쓰는 'revenue backlog'는 성격이 다른 두 수치의 합이다.
      ASC 606 잔여 수행의무 — GPU 시간당 과금 계약
      ASC 842 계약 임대     — 코로케이션. 개시 전 계약까지 포함한 총액
    둘을 더한 값만 보도자료에 나오므로, 다리별 수치는 10-Q 주석에서 읽는다.
    """
    f = next(x for x in filings(refresh) if x["form"] in ("10-Q", "10-K"))
    t = rfile(f["acc"], r"Revenue - Narrative", refresh)
    col = 0
    rpo = t.value("Revenue, remaining performance obligation, amount", col)
    leases = t.value("Remaining aggregate contracted value of lease arrangements, "
                     "including leases not yet commenced", col)

    # 시점별 인식 예정액은 축(Axis) 블록으로 쪼개져 들어온다
    buckets = [v for ctx, lab, vals in t.rows
               if "remaining performance obligation, amount" in lab.lower()
               for v in [vals[col] if col < len(vals) else None] if v]
    nxt = buckets[1] if len(buckets) > 1 else None
    following = buckets[2] if len(buckets) > 2 else None

    lp = rfile(f["acc"], r"Minimum Lease Payments", refresh)
    payments = {lab: vals[0] for _, lab, vals in lp.rows
                if vals and vals[0] is not None and re.search(r"Year|Thereafter|Total|Remainder", lab)}
    return Backlog(f["period"], rpo or 0.0, leases or 0.0, payments, nxt, following)


# --------------------------------------------------------------- 부채·현금

@dataclass
class Debt:
    name: str
    principal: float
    rate: float | None
    kind: str      # "전환사채" | "GPU 담보" | "비소구" | "기타"


def debt_stack(refresh: bool = False) -> tuple[date, list[Debt]]:
    """차입 항목별 원금과 실효금리. 전환사채와 자산담보를 구분한다."""
    f = next(x for x in filings(refresh) if x["form"] in ("10-Q", "10-K"))
    t = rfile(f["acc"], r"Schedule of Debt Obligations", refresh)

    # 이 표는 항목을 '증서 | 성격 | 소구여부' 축 조합으로 적는다. 같은 증서가
    # 소구 축이 붙은 행과 안 붙은 행으로 두 번 나오므로 증서 이름으로 묶는다.
    # 축이 하나도 없는 행은 합계·조정행이라 버린다.
    by_name: dict[str, Debt] = {}
    rates: dict[str, float] = {}
    for ctx, label, vals in t.rows:
        if not ctx or "|" not in ctx and ctx.lower().endswith("recourse debt"):
            continue
        name = re.sub(r"\s*\[Member\]", "", ctx.split("|")[0]).strip()
        if label.lower().startswith("effective interest"):
            if vals and vals[0]:
                rates[name] = vals[0]
            continue
        if label.lower().startswith("total principal of debt") and vals and vals[0]:
            kind = ("전환사채" if "convertible" in ctx.lower()
                    else "비소구" if "non-recourse" in ctx.lower()
                    else "GPU 담보" if "gpu" in name.lower()
                    else "기타")
            by_name[name] = Debt(name, vals[0], None, kind)
    items = [Debt(d.name, d.principal, rates.get(d.name), d.kind) for d in by_name.values()]
    return f["period"], items


def debt_maturities(refresh: bool = False) -> dict[str, float]:
    """회계연도별 차입 원금 상환 예정액."""
    f = next(x for x in filings(refresh) if x["form"] in ("10-Q", "10-K"))
    t = rfile(f["acc"], r"Future Principal Payments", refresh)
    return {lab: vals[0] for _, lab, vals in t.rows
            if vals and vals[0] and re.search(r"Year|Thereafter|Total|Remainder", lab)}


def balance_sheet(refresh: bool = False) -> dict[str, float]:
    """최신 분기 재무상태표에서 밸류에이션에 쓰는 줄만."""
    f = next(x for x in filings(refresh) if x["form"] in ("10-Q", "10-K"))
    t = rfile(f["acc"], r"Balance Sheets$", refresh)
    want = {
        "cash": "Cash and cash equivalents",
        "restricted_current": "Restricted cash, current portion",
        "restricted_noncurrent": "Restricted cash, less current portion",
        "receivables": "Accounts receivable, net",
        "ppe": "Property, plant and equipment, net",
        "total_assets": "Total assets",
        "debt_current": "Debt, current portion",
        "debt_noncurrent": "Debt, less current portion",
        "finance_lease_current": "Finance lease liability, current portion",
        "finance_lease_noncurrent": "Finance lease liability, less current portion",
        "deferred_revenue_current": "Deferred revenue, current portion",
        "deferred_revenue_noncurrent": "Deferred revenue, less current portion",
        "equity": "Total stockholders’ equity",
        "total_liabilities": "Total liabilities",
    }
    out: dict[str, float] = {}
    for key, label in want.items():
        for ctx, lab, vals in t.rows:
            if lab == label and vals and vals[0] is not None:
                out[key] = vals[0]
                break
    out["as_of"] = f["period"]
    out["cash_total"] = (out.get("cash", 0) + out.get("restricted_current", 0)
                         + out.get("restricted_noncurrent", 0))
    out["debt_total"] = (out.get("debt_current", 0) + out.get("debt_noncurrent", 0)
                         + out.get("finance_lease_current", 0)
                         + out.get("finance_lease_noncurrent", 0))
    out["net_debt"] = out["debt_total"] - out["cash_total"]
    return out


def shares_outstanding(refresh: bool = False) -> Series:
    """(공시일, 표지 주식수). 시가총액에는 가중평균이 아니라 시점 주식수를 쓴다.

    dei companyconcept API는 복수 클래스를 가진 분기를 빼먹는다 (IREN은 B클래스가
    2주 있다). 그래서 각 공시 표지 R파일을 직접 읽고 클래스를 합산한다. 표지의
    기준일은 공시일 며칠 전이지만 R파일에 찍히지 않아 공시일을 쓴다 — 시가총액
    계산에서 분기말 주가와 맞물릴 때 며칠 차이는 무해하다.
    """
    out: Series = []
    for f in filings(refresh):
        try:
            t = rfile(f["acc"], r"^Cover|Document And Entity Information", refresh)
        except LookupError:
            continue
        total, when = 0.0, None
        dates = [d for _, ds in t.groups for d in ds]
        for _, lab, vals in t.rows:
            if not lab.lower().startswith("entity common stock, shares outstanding"):
                continue
            # 표지는 기간 열과 주식수 기준일 열을 같이 들고 있다. 값이 들어 있는
            # 열의 머리 날짜가 주식수 기준일이다.
            for i, v in enumerate(vals):
                if v:
                    total += v
                    if i < len(dates):
                        when = dates[i]
        if total:
            out.append((when or f["filed"], total))
    out.sort()
    return out


def dilution(refresh: bool = False) -> dict[str, float]:
    """희석 가능 주식수 — 스톡옵션·RSU·투자권리·전환사채."""
    f = next(x for x in filings(refresh) if x["form"] in ("10-Q", "10-K"))
    t = rfile(f["acc"], r"Antidilutive Securities", refresh)
    out: dict[str, float] = {}
    for ctx, lab, vals in t.rows:
        if not vals or not vals[0]:
            continue
        out["합계" if not ctx else ctx] = vals[0]
    # 전환사채는 축으로 쪼개지지 않는 해가 있다. 합계와 항목 합의 차이로 메운다.
    named = sum(v for k, v in out.items() if k != "합계")
    gap = out.get("합계", 0) - named
    if gap > 0:
        out["Convertible notes"] = out.get("Convertible notes", 0) + gap
    return out


# --------------------------------------------------------------- 시장 데이터

def _yahoo(ticker: str, refresh: bool = False, years: int = 5) -> Series:
    def go():
        r = requests.get(YAHOO.format(ticker=ticker), timeout=60,
                         headers={"User-Agent": SEC_UA},
                         params={"range": f"{years}y", "interval": "1d"})
        r.raise_for_status()
        return r.json()

    payload = _cached(f"price_{ticker.lower()}", go, refresh)
    result = payload["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    out: Series = []
    for stamp, close in zip(result["timestamp"], closes):
        if close is None:
            continue
        out.append((datetime.fromtimestamp(int(stamp), tz=timezone.utc).date(), float(close)))
    out.sort()
    return out


def price(refresh: bool = False) -> Series:
    return _yahoo(TICKER, refresh)


def btc_price(refresh: bool = False) -> Series:
    return _yahoo("BTC-USD", refresh)


def on_or_before(series: Series, when: date) -> float | None:
    """해당 날짜까지의 마지막 값. 주말·휴장일을 건너뛴다."""
    found = None
    for d, v in series:
        if d <= when:
            found = v
        else:
            break
    return found


def latest(series: Series) -> tuple[date, float]:
    return series[-1]


if __name__ == "__main__":
    print(f"=== 분기 매출 (단위 $M) · {TICKER}")
    print(f"{'분기':>10} {'총매출':>9} {'채굴':>9} {'AI클라우드':>11}  출처")
    for r in quarterly_revenue():
        fy, q = r.quarter
        m = f"{r.mining/1e6:9.1f}" if r.mining is not None else " " * 9
        c = f"{r.ai_cloud/1e6:11.1f}" if r.ai_cloud is not None else " " * 11
        print(f"FY{fy}Q{q:<6} {r.total/1e6:9.1f} {m} {c}  {r.source}")

    b = backlog()
    print(f"\n=== 수주잔고 ({b.as_of})")
    print(f"  ASC 606 잔여 수행의무 : ${b.rpo/1e9:5.2f}B")
    print(f"  ASC 842 계약 임대     : ${b.leases/1e9:5.2f}B")
    print(f"  합계                  : ${b.total/1e9:5.2f}B")

    as_of, items = debt_stack()
    print(f"\n=== 차입 ({as_of})")
    for d in sorted(items, key=lambda x: -x.principal):
        rate = f"{d.rate:5.2f}%" if d.rate else "    —"
        print(f"  {d.name:34} {d.principal/1e9:6.2f}B {rate}  {d.kind}")
    print(f"  {'합계':34} {sum(d.principal for d in items)/1e9:6.2f}B")

    d, p = latest(price())
    sh = shares_outstanding()[-1]
    print(f"\n=== 시장 ({d})")
    print(f"  주가        ${p:,.2f}")
    print(f"  주식수      {sh[1]/1e6:,.1f}M ({sh[0]})")
    print(f"  시가총액    ${p * sh[1]/1e9:,.2f}B")
    print(f"  희석 가능   {dilution().get('합계', 0)/1e6:,.1f}M")
