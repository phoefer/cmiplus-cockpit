#!/usr/bin/env python3
"""
CMIplus Intelligence Cockpit — Weekly Scan
Runs every Monday 06:00 UTC via GitHub Actions.

Produces:
  - briefing.json         : structured weekly briefing (market/thought/competitors)
  - flagship-analyses.json: CMIplus positioning vs. 4 flagship reports
"""

import os
import json
import base64
import urllib.request
import urllib.error
import datetime
import re

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_KEY", "")
FLASH_MODEL    = "gemini-2.5-flash"
PRO_MODEL      = "gemini-2.5-pro"
GEMINI_URL     = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")

FLAGSHIP_REPORTS = [
    {
        "id":     "ey_four_trends",
        "title":  "EY Four Trends Redefining Cash Management",
        "year":   "2025",
        "source": "pdf",
        "file":   "ey-gl-four-trends-redefining-cash-management-08-2025.pdf",
    },
    {
        "id":     "mckinsey_payments",
        "title":  "McKinsey Global Payments Report",
        "year":   "2025",
        "source": "pdf",
        "file":   "the-2025-mckinsey-global-payments-report.pdf",
    },
    {
        "id":     "journeys_to_treasury",
        "title":  "Journeys to Treasury",
        "year":   "2025/26",
        "source": "pdf",
        "file":   "Journeys to Treasury 2025-26.pdf",
    },
    {
        "id":     "pwc_treasury_survey",
        "title":  "PwC Global Treasury Survey",
        "year":   "2025",
        "source": "web",
        "url":    "https://www.pwc.com/us/en/services/consulting/business-transformation/library/2025-global-treasury-survey.html",
    },
]

WEEKLY_SOURCES = [
    {"url": "https://www.mckinsey.com/industries/financial-services/our-insights", "weight": 2},
    {"url": "https://www.bcg.com/industries/financial-institutions/insights",       "weight": 2},
    {"url": "https://www.ey.com/en_gl/insights/financial-services",                 "weight": 1},
    {"url": "https://www.pwc.com/gx/en/industries/financial-services/publications.html", "weight": 1},
    {"url": "https://www.swift.com/news-events/news",                               "weight": 1},
    {"url": "https://www.treasurytoday.com/news",                                   "weight": 1},
    {"url": "https://www.finextra.com/newshub/fintech",                             "weight": 1},
    {"url": "https://www.ecb.europa.eu/press/pr/date/html/index.en.html",           "weight": 1},
    {"url": "https://www.eba.europa.eu/newsroom/news",                              "weight": 1},
]

CMIPLUS_CONTEXT = """
CMIplus is Raiffeisen Bank International's (RBI) corporate cash management platform
serving large international corporates across CEE (Central & Eastern Europe).
Key facts:
- Channels: EBICS v2.5 + v3, H2H, SWIFT, Web, Mobile, Open API
- Network banks: Austria, CZ, HR, RS, XK, AL, RO, SK, HU and other CEE markets
- ~1,700 customers technically migrated (Q1 2026)
- VoP (Verification of Payee): live since October 2025, web channel fully compliant
- eBAM: resuming focus on Account Maintenance (acmt.015, acmt.017)
- Open API: scaling initiative, UNIFI format expected Q3/2026
- Payment formats: XCT/CGI, ISO 20022 pain.001, native formats per country
- AI Cash Flow Forecasting: planned Q4/2026
- Key competitors in CEE corporate banking: UniCredit, Erste Bank, Citi, Deutsche Bank, ING
- Key strength: CEE network coverage, EBICS expertise, multi-currency support
"""

# ---------------------------------------------------------------------------
# Gemini API helpers
# ---------------------------------------------------------------------------

def gemini_call(model: str, parts: list, max_tokens: int = 16000) -> str:
    url = GEMINI_URL.format(model=model, key=GEMINI_API_KEY)
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
    }
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {e.code}: {body[:400]}")


def fetch_url_text(url: str, max_bytes: int = 200_000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CMIplus-Cockpit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(max_bytes).decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text[:60_000]
    except Exception as e:
        return f"[Error fetching {url}: {e}]"


def load_pdf_base64(filename: str) -> str:
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def parse_json_loose(raw: str) -> dict:
    """Strip markdown fences and parse JSON with bracket-counting fallback."""
    clean = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE)
    clean = re.sub(r"\n?```$", "", clean.strip(), flags=re.MULTILINE)
    clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    start = clean.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")
    depth = 0
    end = start
    for i, ch in enumerate(clean[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    return json.loads(clean[start : end + 1])


# ---------------------------------------------------------------------------
# Weekly briefing — correct output format for index.html
# ---------------------------------------------------------------------------

BRIEFING_PROMPT = """
You are an intelligence analyst for RBI's CMIplus corporate cash management platform.
Scan the web content below and produce a structured weekly intelligence briefing.

Context about CMIplus:
{context}

Web content from sources:
{content}

Today's date: {scan_date}

Produce items across THREE sections:
1. market (4 items): Breaking news, regulatory updates, market moves directly affecting payments/cash management
2. thought (4 items): Strategic insights, research findings, industry trends from McKinsey, BCG, EY, PwC — prioritise these heavily
3. competitors (2 items): Moves by UniCredit, Erste, Citi, Deutsche Bank, ING or other banks competing in CEE corporate banking

For EACH item use this EXACT field structure:
- title: Short headline max 10 words
- summary: 2-3 sentences on what happened and why it matters
- sowhat: One sentence — direct implication for CMIplus product or strategy
- source: Source name (e.g. "McKinsey", "ECB", "Finextra")
- relevance: MUST be exactly one of: urgent / watch / fyi
- tags: Array of 1-3 short topic tags e.g. ["ISO20022", "AI", "EBICS"]
- date: Today's date {scan_date}

For competitor items also add:
- competitor: Name of the competitor bank (e.g. "UniCredit", "Erste Bank")

Also produce:
- executive_summary: 3-4 sentence overview of the week's most important developments for CMIplus
- week_label: "Week of {scan_date}"

Respond ONLY with valid JSON, no markdown, no preamble:
{{
  "scan_date": "{scan_date}",
  "week_label": "Week of {scan_date}",
  "executive_summary": "...",
  "market": [ /* 4 items */ ],
  "thought": [ /* 4 items */ ],
  "competitors": [ /* 2 items */ ]
}}
"""


def run_weekly_briefing(scan_date: str) -> dict:
    print("Fetching weekly sources...")
    content_parts = []
    for src in WEEKLY_SOURCES:
        url    = src["url"]
        weight = src["weight"]
        print(f"  Fetching: {url}")
        text = fetch_url_text(url, max_bytes=100_000)
        for _ in range(weight):
            content_parts.append(f"=== SOURCE: {url} ===\n{text[:8_000]}\n")

    combined = "\n".join(content_parts)[:120_000]
    prompt = BRIEFING_PROMPT.format(
        context=CMIPLUS_CONTEXT,
        content=combined,
        scan_date=scan_date,
    )

    print("Calling Gemini Flash for weekly briefing...")
    try:
        raw    = gemini_call(FLASH_MODEL, [{"text": prompt}], max_tokens=16000)
        result = parse_json_loose(raw)
        # Normalize relevance values to lowercase
        for section in ["market", "thought", "competitors"]:
            for item in result.get(section, []):
                r = str(item.get("relevance", "fyi")).lower()
                if r in ("high", "urgent"):
                    item["relevance"] = "urgent"
                elif r in ("medium", "watch"):
                    item["relevance"] = "watch"
                else:
                    item["relevance"] = "fyi"
        print(f"  briefing.json: {len(result.get('market',[]))} market, {len(result.get('thought',[]))} thought, {len(result.get('competitors',[]))} competitors")
        return result
    except Exception as e:
        print(f"ERROR in weekly briefing: {e}")
        return {
            "scan_date":         scan_date,
            "week_label":        f"Week of {scan_date}",
            "executive_summary": f"Scan error: {e}",
            "market":            [],
            "thought":           [],
            "competitors":       [],
            "error":             str(e),
        }


# ---------------------------------------------------------------------------
# Flagship analyses
# ---------------------------------------------------------------------------

FLAGSHIP_PROMPT_TEMPLATE = """
You are an expert analyst for RBI's CMIplus platform. Analyse the provided report and produce a structured JSON analysis.

Context about CMIplus:
{context}

Report: "{title}" ({year})

Instructions:
1. Identify the 4-6 most important themes or trends from the report.
2. For each theme, assess CMIplus positioning: AHEAD / IN LINE / BEHIND.
3. Extract the most relevant key statistics or data points.
4. Identify 2-3 concrete action items for CMIplus based on the report findings.
5. Write a 2-3 sentence executive summary.

Respond ONLY with valid JSON, no markdown, no preamble. Use this exact structure:
{{
  "report_id": "{report_id}",
  "report_title": "{title}",
  "report_year": "{year}",
  "executive_summary": "...",
  "themes": [
    {{
      "name": "Theme name",
      "description": "2-3 sentences about this theme from the report",
      "cmiplus_positioning": "AHEAD|IN LINE|BEHIND",
      "positioning_rationale": "Why CMIplus is positioned this way",
      "key_stat": "Most relevant number or quote from report (optional)"
    }}
  ],
  "key_actions": [
    {{
      "action": "Concrete action for CMIplus",
      "urgency": "HIGH|MEDIUM|LOW",
      "rationale": "Why this action matters based on report findings"
    }}
  ],
  "scan_date": "{scan_date}"
}}
"""


def analyse_flagship_pdf(report: dict, scan_date: str) -> dict:
    print(f"  Analysing PDF: {report['file']} ...")
    try:
        pdf_b64 = load_pdf_base64(report["file"])
    except FileNotFoundError:
        print(f"  WARNING: PDF not found: {report['file']}")
        return _error_entry(report, scan_date, "PDF file not found in reports/")

    prompt = FLAGSHIP_PROMPT_TEMPLATE.format(
        context=CMIPLUS_CONTEXT,
        title=report["title"],
        year=report["year"],
        report_id=report["id"],
        scan_date=scan_date,
    )
    parts = [
        {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
        {"text": prompt},
    ]
    try:
        raw = gemini_call(PRO_MODEL, parts, max_tokens=16000)
        return parse_json_loose(raw)
    except Exception as e:
        print(f"  ERROR analysing {report['id']}: {e}")
        return _error_entry(report, scan_date, str(e))


def analyse_flagship_web(report: dict, scan_date: str) -> dict:
    print(f"  Analysing web: {report['url']} ...")
    page_text = fetch_url_text(report["url"])
    prompt = FLAGSHIP_PROMPT_TEMPLATE.format(
        context=CMIPLUS_CONTEXT,
        title=report["title"],
        year=report["year"],
        report_id=report["id"],
        scan_date=scan_date,
    ) + f"\n\nWebpage content:\n{page_text}"

    try:
        raw = gemini_call(FLASH_MODEL, [{"text": prompt}], max_tokens=16000)
        return parse_json_loose(raw)
    except Exception as e:
        print(f"  ERROR analysing {report['id']}: {e}")
        return _error_entry(report, scan_date, str(e))


def _error_entry(report: dict, scan_date: str, error: str) -> dict:
    return {
        "report_id":         report["id"],
        "report_title":      report["title"],
        "report_year":       report["year"],
        "executive_summary": f"Analysis unavailable: {error}",
        "themes":            [],
        "key_actions":       [],
        "scan_date":         scan_date,
        "error":             error,
    }


def run_flagship_analyses(scan_date: str) -> list:
    results = []
    for report in FLAGSHIP_REPORTS:
        if report["source"] == "pdf":
            result = analyse_flagship_pdf(report, scan_date)
        else:
            result = analyse_flagship_web(report, scan_date)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_KEY environment variable not set")

    scan_date = datetime.date.today().isoformat()
    print(f"\n{'='*60}")
    print(f"CMIplus Intelligence Cockpit — Scan {scan_date}")
    print(f"{'='*60}\n")

    # 1. Weekly briefing
    print("=== WEEKLY BRIEFING ===")
    briefing = run_weekly_briefing(scan_date)
    with open("briefing.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    print(f"  briefing.json written")

    # 2. Flagship analyses
    print("\n=== FLAGSHIP ANALYSES ===")
    analyses = run_flagship_analyses(scan_date)
    with open("flagship-analyses.json", "w", encoding="utf-8") as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)
    print(f"  flagship-analyses.json written ({len(analyses)} reports)")

    print(f"\nScan complete. Date: {scan_date}")


if __name__ == "__main__":
    main()
