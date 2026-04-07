#!/usr/bin/env python3
"""
CMIplus Intelligence Cockpit — Weekly Scan
Runs every Monday 06:00 UTC via GitHub Actions.

Produces:
  - briefing.json         : structured weekly briefing
  - flagship-analyses.json: CMIplus positioning vs. 4 flagship reports
"""

import os, json, base64, urllib.request, urllib.error, datetime, re

GEMINI_API_KEY = os.environ.get("GEMINI_KEY", "")
FLASH_MODEL    = "gemini-2.5-flash"
GEMINI_URL     = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
REPORTS_DIR    = os.path.join(os.path.dirname(__file__), "reports")

# ---------------------------------------------------------------------------
# Sources — per type
# ---------------------------------------------------------------------------

MARKET_SOURCES = [
    {"name": "ECB",           "url": "https://www.ecb.europa.eu/press/pr/date/html/index.en.html"},
    {"name": "EBA",           "url": "https://www.eba.europa.eu/newsroom/news"},
    {"name": "SWIFT",         "url": "https://www.swift.com/news-events/news"},
    {"name": "Finextra",      "url": "https://www.finextra.com/newshub/fintech"},
    {"name": "Treasury Today","url": "https://www.treasurytoday.com/news"},
    {"name": "The Paypers",   "url": "https://thepaypers.com/"},
    {"name": "Payments Dive", "url": "https://www.paymentsdive.com/"},
]

THOUGHT_SOURCES = [
    {"name": "McKinsey",      "url": "https://www.mckinsey.com/industries/financial-services/our-insights"},
    {"name": "BCG",           "url": "https://www.bcg.com/industries/financial-institutions/insights"},
    {"name": "EY",            "url": "https://www.ey.com/en_gl/insights/financial-services"},
    {"name": "PwC",           "url": "https://www.pwc.com/gx/en/industries/financial-services/publications.html"},
    {"name": "Deloitte",      "url": "https://www2.deloitte.com/global/en/insights/industry/financial-services.html"},
]

COMPETITOR_SOURCES = [
    {"name": "UniCredit",     "url": "https://www.unicredit.eu/en/newsroom.html",         "competitor": "UniCredit"},
    {"name": "Erste Bank",    "url": "https://www.erstegroup.com/en/news-media/press-releases", "competitor": "Erste Bank"},
    {"name": "Deutsche Bank", "url": "https://www.db.com/news/index.htm",                 "competitor": "Deutsche Bank"},
    {"name": "ING",           "url": "https://www.ing.com/Newsroom.htm",                  "competitor": "ING"},
    {"name": "Citi",          "url": "https://www.citigroup.com/global/news/",            "competitor": "Citi"},
]

FLAGSHIP_REPORTS = [
    {"id":"ey_four_trends",      "title":"EY Four Trends Redefining Cash Management",   "year":"2025",    "source":"pdf",  "file":"ey-gl-four-trends-redefining-cash-management-08-2025.pdf",    "report_url":"https://phoefer.github.io/cmiplus-cockpit/reports/ey-gl-four-trends-redefining-cash-management-08-2025.pdf"},
    {"id":"mckinsey_payments",   "title":"McKinsey Global Payments Report",              "year":"2025",    "source":"pdf",  "file":"the-2025-mckinsey-global-payments-report.pdf",                 "report_url":"https://phoefer.github.io/cmiplus-cockpit/reports/the-2025-mckinsey-global-payments-report.pdf"},
    {"id":"journeys_to_treasury","title":"Journeys to Treasury",                         "year":"2025/26", "source":"pdf",  "file":"Journeys to Treasury 2025-26.pdf",                             "report_url":"https://phoefer.github.io/cmiplus-cockpit/reports/Journeys%20to%20Treasury%202025-26.pdf"},
    {"id":"pwc_treasury_survey", "title":"PwC Global Treasury Survey",                  "year":"2025",    "source":"web",  "url":"https://www.pwc.com/us/en/services/consulting/business-transformation/library/2025-global-treasury-survey.html", "report_url":"https://www.pwc.com/us/en/services/consulting/business-transformation/library/2025-global-treasury-survey.html"},
]

CMIPLUS_CONTEXT = """
CMIplus is Raiffeisen Bank International's (RBI) corporate cash management platform
serving large international corporates across CEE (Central & Eastern Europe).
- Channels: EBICS v2.5+v3, H2H, SWIFT, Web, Mobile, Open API
- Network banks: Austria, CZ, HR, RS, XK, AL, RO, SK, HU and other CEE markets
- ~1,700 customers migrated (Q1 2026)
- VoP live Oct 2025, eBAM resuming, Open API Q3/26, AI Forecasting Q4/26
- Competitors: UniCredit, Erste Bank, Citi, Deutsche Bank, ING
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def gemini_call(parts, max_tokens=8000):
    url = GEMINI_URL.format(model=FLASH_MODEL, key=GEMINI_API_KEY)
    payload = {"contents":[{"parts":parts}],"generationConfig":{"maxOutputTokens":max_tokens,"temperature":0.3}}
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {e.code}: {body[:400]}")

def fetch_url_text(url, max_bytes=150_000):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 CMIplus-Cockpit/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read(max_bytes).decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text[:60_000]
    except Exception as e:
        return f"[Error fetching {url}: {e}]"

def load_pdf_base64(filename):
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def parse_json_loose(raw):
    clean = re.sub(r"^```[a-z]*\n?","",raw.strip(),flags=re.MULTILINE)
    clean = re.sub(r"\n?```$","",clean.strip(),flags=re.MULTILINE).strip()
    try: return json.loads(clean)
    except: pass
    start = clean.find("{")
    if start == -1: raise ValueError("No JSON found")
    depth,end = 0,start
    for i,ch in enumerate(clean[start:],start):
        if ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0: end=i; break
    return json.loads(clean[start:end+1])

def normalize_relevance(r):
    r = str(r).lower()
    if r in ("high","urgent"): return "urgent"
    if r in ("medium","watch"): return "watch"
    return "fyi"

# ---------------------------------------------------------------------------
# Per-source extraction prompts
# ---------------------------------------------------------------------------

MARKET_PROMPT = """
You are an intelligence analyst for RBI Cash Management (CMIplus platform, CEE focus).
Extract the top 3 most relevant NEWS items from this source for cash management professionals.

Source: {source_name} ({source_url})
Content:
{content}

Today's date: {scan_date}

Focus on: payment regulations, instant payments, ISO 20022, VoP, EBICS, Open Banking,
PSD3, treasury technology, CEE banking, fraud prevention, cross-border payments.

For EACH of the 3 items produce EXACTLY these fields:
- title: Compelling headline max 12 words
- summary_short: 2 sentences — what happened
- summary_detail: 5-7 sentences — full context, background, regulatory details, timeline, industry impact
- key_points: Array of 4 specific facts, data points or quotes from the article
- rbi_cash_management: 2-3 sentences — what this means specifically for RBI Cash Management and CMIplus customers
- url: Direct article URL if visible in content, otherwise use source URL "{source_url}"
- source: "{source_name}"
- source_url: "{source_url}"
- relevance_score: Integer 1-10 (10 = most critical for CMIplus/RBI)
- relevance: "urgent" if score>=8, "watch" if score>=5, "fyi" otherwise
- tags: Array of 2-4 tags e.g. ["ISO20022","InstantPayments","CEE","EBICS"]
- date: "{scan_date}"

Respond ONLY with valid JSON:
{{"source":"{source_name}","items":[/* exactly 3 */]}}
"""

THOUGHT_PROMPT = """
You are an intelligence analyst for RBI Cash Management (CMIplus platform, CEE focus).
Extract the top 3 most relevant THOUGHT LEADERSHIP insights from this source.

Source: {source_name} ({source_url})
Content:
{content}

Today's date: {scan_date}

Focus on: treasury strategy, AI in banking, cash management trends, payment transformation,
digital banking innovation, corporate banking evolution, CEE market trends.

For EACH of the 3 items produce EXACTLY these fields:
- title: Strategic headline max 12 words
- summary_short: 2 sentences — core finding or argument
- summary_detail: 5-7 sentences — full strategic context, methodology, key data, implications for corporate banking
- key_points: Array of 4 specific insights, statistics or strategic conclusions
- rbi_cash_management: 2-3 sentences — strategic implication for RBI Cash Management positioning and CMIplus roadmap
- url: Direct article URL if visible in content, otherwise use source URL "{source_url}"
- source: "{source_name}"
- source_url: "{source_url}"
- relevance_score: Integer 1-10
- relevance: "urgent" if score>=8, "watch" if score>=5, "fyi" otherwise
- tags: Array of 2-4 tags
- date: "{scan_date}"

Respond ONLY with valid JSON:
{{"source":"{source_name}","items":[/* exactly 3 */]}}
"""

COMPETITOR_PROMPT = """
You are an intelligence analyst for RBI Cash Management (CMIplus platform, CEE focus).
Extract the top 3 most relevant items about {competitor} from this source.

Source: {source_name} ({source_url})
Content:
{content}

Today's date: {scan_date}

Focus on: product launches, CEE expansion, cash management features, payment capabilities,
API/digital banking announcements, treasury solutions, partnership deals.

If no specific news is found, infer likely strategic moves based on industry trends and
what you know about {competitor}'s cash management strategy.

For EACH of the 3 items produce EXACTLY these fields:
- title: Headline max 12 words
- summary_short: 2 sentences — what happened or what is inferred
- summary_detail: 4-6 sentences — full context, product details, strategic rationale, CEE relevance
- key_points: Array of 3-4 specific facts or strategic observations
- rbi_cash_management: 2 sentences — competitive implication for RBI CMIplus
- url: Direct article URL if visible, otherwise use source URL "{source_url}"
- source: "{source_name}"
- source_url: "{source_url}"
- competitor: "{competitor}"
- relevance_score: Integer 1-10
- relevance: "urgent" if score>=8, "watch" if score>=5, "fyi" otherwise
- tags: Array of 2-4 tags
- date: "{scan_date}"
- inferred: true if based on inference rather than actual news, false otherwise

Respond ONLY with valid JSON:
{{"source":"{source_name}","competitor":"{competitor}","items":[/* exactly 3 */]}}
"""

# ---------------------------------------------------------------------------
# Per-source extraction
# ---------------------------------------------------------------------------

def extract_from_source(src, prompt_template, scan_date, extra=None):
    print(f"  → {src['name']}: fetching...")
    text = fetch_url_text(src["url"])
    if text.startswith("[Error"):
        print(f"    FAILED: {text[:80]}")
        return {"source": src["name"], "items": []}

    kwargs = {
        "source_name": src["name"],
        "source_url":  src["url"],
        "content":     text[:15_000],
        "scan_date":   scan_date,
    }
    if extra:
        kwargs.update(extra)

    prompt = prompt_template.format(**kwargs)
    try:
        raw    = gemini_call([{"text": prompt}], max_tokens=8000)
        result = parse_json_loose(raw)
        items  = result.get("items", [])
        for item in items:
            item["relevance"]       = normalize_relevance(item.get("relevance", "fyi"))
            item["relevance_score"] = int(item.get("relevance_score", 5))
            item["source"]          = src["name"]
            item["source_url"]      = src["url"]
            if extra and "competitor" in extra:
                item["competitor"] = extra["competitor"]
        print(f"    OK: {len(items)} items (scores: {[i['relevance_score'] for i in items]})")
        return {"source": src["name"], "items": items}
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"source": src["name"], "items": []}

# ---------------------------------------------------------------------------
# Weekly briefing
# ---------------------------------------------------------------------------

def run_weekly_briefing(scan_date):
    print("\n--- MARKET NEWS ---")
    all_market = []
    for src in MARKET_SOURCES:
        result = extract_from_source(src, MARKET_PROMPT, scan_date)
        for item in result["items"]:
            item["_source_group"] = src["name"]
        all_market.extend(result["items"])

    # Sort by relevance_score descending → ranked list
    all_market.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    for i, item in enumerate(all_market):
        item["rank"] = i + 1

    print(f"\n  Total market items: {len(all_market)}")

    print("\n--- THOUGHT LEADERSHIP ---")
    all_thought = []
    for src in THOUGHT_SOURCES:
        result = extract_from_source(src, THOUGHT_PROMPT, scan_date)
        for item in result["items"]:
            item["_source_group"] = src["name"]
        all_thought.extend(result["items"])

    all_thought.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    for i, item in enumerate(all_thought):
        item["rank"] = i + 1

    print(f"\n  Total thought items: {len(all_thought)}")

    print("\n--- COMPETITORS ---")
    all_competitors = []
    for src in COMPETITOR_SOURCES:
        result = extract_from_source(
            src, COMPETITOR_PROMPT, scan_date,
            extra={"competitor": src["competitor"]}
        )
        for item in result["items"]:
            item["_source_group"] = src["competitor"]
        all_competitors.extend(result["items"])

    all_competitors.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    for i, item in enumerate(all_competitors):
        item["rank"] = i + 1

    print(f"\n  Total competitor items: {len(all_competitors)}")

    # Executive summary
    print("\n--- EXECUTIVE SUMMARY ---")
    top_items = (all_market[:3] + all_thought[:3] + all_competitors[:2])
    exec_prompt = f"""
Based on these top intelligence items for RBI Cash Management this week,
write a 4-5 sentence executive summary of the most important developments
and their strategic implications for CMIplus.

Items:
{json.dumps([{"title":i["title"],"summary_short":i["summary_short"]} for i in top_items], indent=2)}

Today: {scan_date}

Return ONLY the summary text, no JSON, no preamble.
"""
    try:
        exec_summary = gemini_call([{"text": exec_prompt}], max_tokens=500).strip()
    except Exception as e:
        exec_summary = f"Weekly scan completed. {len(all_market)} market, {len(all_thought)} thought leadership, {len(all_competitors)} competitor items collected."

    return {
        "scan_date":         scan_date,
        "week_label":        f"Week of {scan_date}",
        "executive_summary": exec_summary,
        "market":            all_market,
        "thought":           all_thought,
        "competitors":       all_competitors,
    }

# ---------------------------------------------------------------------------
# Flagship analyses
# ---------------------------------------------------------------------------

FLAGSHIP_PROMPT = """
You are a senior analyst for RBI's CMIplus platform.
Produce a comprehensive strategic analysis of this report.

Context: {context}
Report: "{title}" ({year})

Produce a DETAILED analysis:
1. executive_summary: 4-5 sentences — coverage, methodology, main conclusions
2. key_stats: Array of 6-8 most important statistics from the report
3. themes: Array of 5-6 themes, each with:
   - name, description (3-4 sentences), key_stat
4. key_actions: Array of 3-4 actions for CMIplus, each with:
   - action, urgency (HIGH/MEDIUM/LOW), rationale (2 sentences), timeline
5. competitive_implications: 2-3 sentences
6. case_studies: Array of corporate case studies from the report (if any), each with:
   - company, headline (1 sentence summary of their treasury journey),
     key_achievement (most impressive result), lesson (main takeaway for CMIplus customers)

Respond ONLY with valid JSON:
{{
  "report_id":"{report_id}","report_title":"{title}","report_year":"{year}","report_url":"{report_url}",
  "executive_summary":"...","key_stats":[],"themes":[],"key_actions":[],"competitive_implications":"...","case_studies":[],"scan_date":"{scan_date}"
}}
"""

def analyse_flagship_pdf(report, scan_date):
    print(f"  PDF: {report['file']} ...")
    try:
        pdf_b64 = load_pdf_base64(report["file"])
    except FileNotFoundError:
        return _error_entry(report, scan_date, "PDF not found")

    prompt = FLAGSHIP_PROMPT.format(
        context=CMIPLUS_CONTEXT, title=report["title"], year=report["year"],
        report_id=report["id"], report_url=report.get("report_url",""), scan_date=scan_date,
    )
    try:
        raw = gemini_call([{"inline_data":{"mime_type":"application/pdf","data":pdf_b64}},{"text":prompt}], max_tokens=16000)
        result = parse_json_loose(raw)
        result["report_url"] = report.get("report_url","")
        return result
    except Exception as e:
        print(f"  ERROR: {e}")
        return _error_entry(report, scan_date, str(e))

def analyse_flagship_web(report, scan_date):
    print(f"  Web: {report['url']} ...")
    page_text = fetch_url_text(report["url"])
    prompt = FLAGSHIP_PROMPT.format(
        context=CMIPLUS_CONTEXT, title=report["title"], year=report["year"],
        report_id=report["id"], report_url=report.get("report_url",""), scan_date=scan_date,
    ) + f"\n\nWebpage content:\n{page_text}"
    try:
        raw = gemini_call([{"text":prompt}], max_tokens=16000)
        result = parse_json_loose(raw)
        result["report_url"] = report.get("report_url","")
        return result
    except Exception as e:
        print(f"  ERROR: {e}")
        return _error_entry(report, scan_date, str(e))

def _error_entry(report, scan_date, error):
    return {"report_id":report["id"],"report_title":report["title"],"report_year":report["year"],
            "report_url":report.get("report_url",""),"executive_summary":f"Error: {error}",
            "key_stats":[],"themes":[],"key_actions":[],"competitive_implications":"","case_studies":[],"scan_date":scan_date,"error":error}

def run_flagship_analyses(scan_date):
    results = []
    for report in FLAGSHIP_REPORTS:
        r = analyse_flagship_pdf(report, scan_date) if report["source"]=="pdf" else analyse_flagship_web(report, scan_date)
        results.append(r)
    return results

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_KEY environment variable not set")
    scan_date = datetime.date.today().isoformat()
    print(f"\n{'='*60}\nCMIplus Intelligence Cockpit — Scan {scan_date}\n{'='*60}")

    print("\n=== WEEKLY BRIEFING ===")
    briefing = run_weekly_briefing(scan_date)
    with open("briefing.json","w",encoding="utf-8") as f:
        json.dump(briefing,f,ensure_ascii=False,indent=2)
    print(f"\nbriefing.json written: {len(briefing['market'])} market, {len(briefing['thought'])} thought, {len(briefing['competitors'])} competitors")

    print("\n=== FLAGSHIP ANALYSES ===")
    analyses = run_flagship_analyses(scan_date)
    with open("flagship-analyses.json","w",encoding="utf-8") as f:
        json.dump(analyses,f,ensure_ascii=False,indent=2)
    print(f"flagship-analyses.json written ({len(analyses)} reports)")

    print(f"\nScan complete. {scan_date}")

if __name__ == "__main__":
    main()
