#!/usr/bin/env python3
"""
CMIplus Intelligence Cockpit - Weekly Scan
Runs every Monday 06:00 UTC via GitHub Actions.

Sources are configured in sources.json - no code changes needed to add/remove/reprioritise.

Produces:
  - briefing.json         : structured weekly briefing (market/thought/competitors)
  - flagship-analyses.json: deep analyses of 4 flagship reports
"""

import os, json, base64, urllib.request, urllib.error, datetime, re, time

GEMINI_API_KEY  = os.environ.get("GEMINI_KEY", "")
FLASH_MODEL     = "gemini-2.5-flash"
FALLBACK_MODEL  = "gemini-2.5-flash-lite"
GEMINI_URL      = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
REPORTS_DIR    = os.path.join(os.path.dirname(__file__), "reports")
SOURCES_FILE   = os.path.join(os.path.dirname(__file__), "sources.json")

FLAGSHIP_REPORTS = [
    {"id":"ey_four_trends",       "title":"EY Four Trends Redefining Cash Management",  "year":"2025",    "source":"pdf",  "file":"ey-gl-four-trends-redefining-cash-management-08-2025.pdf",   "report_url":"https://phoefer.github.io/cmiplus-cockpit/reports/ey-gl-four-trends-redefining-cash-management-08-2025.pdf"},
    {"id":"mckinsey_payments",    "title":"McKinsey Global Payments Report",             "year":"2025",    "source":"pdf",  "file":"the-2025-mckinsey-global-payments-report.pdf",                "report_url":"https://phoefer.github.io/cmiplus-cockpit/reports/the-2025-mckinsey-global-payments-report.pdf"},
    {"id":"journeys_to_treasury", "title":"Journeys to Treasury",                        "year":"2025/26", "source":"pdf",  "file":"Journeys to Treasury 2025-26.pdf",                            "report_url":"https://phoefer.github.io/cmiplus-cockpit/reports/Journeys%20to%20Treasury%202025-26.pdf"},
    {"id":"pwc_treasury_survey",  "title":"PwC Global Treasury Survey",                 "year":"2025",    "source":"web",  "url":"https://www.pwc.com/us/en/services/consulting/business-transformation/library/2025-global-treasury-survey.html", "report_url":"https://www.pwc.com/us/en/services/consulting/business-transformation/library/2025-global-treasury-survey.html"},
]

# ---------------------------------------------------------------------------
# Load sources.json
# ---------------------------------------------------------------------------

def load_sources():
    """Load and validate sources from sources.json."""
    try:
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"sources.json loaded (updated: {data.get('meta',{}).get('last_updated','?')})", flush=True)
        return data
    except Exception as e:
        print(f"WARNING: Could not load sources.json: {e} - using fallback sources", flush=True)
        return None

def get_active_sources(sources_data, section_key):
    """Return active sources for a section, sorted by priority."""
    if not sources_data:
        return []
    sources = sources_data.get(section_key, [])
    active  = [s for s in sources if s.get("active", True)]
    active.sort(key=lambda x: x.get("priority", 2))
    return active

def get_scan_config(sources_data):
    """Return scan_config from sources.json with defaults."""
    defaults = {
        "items_priority_1": 3,
        "items_priority_2": 2,
        "items_priority_3": 1,
        "language": "English",
        "context": "CMIplus is RBI's corporate cash management platform for large corporates in CEE.",
    }
    if sources_data and "scan_config" in sources_data:
        defaults.update(sources_data["scan_config"])
    return defaults

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

def gemini_call(parts, max_tokens=8000, model=None):
    """Call Gemini. On 503 overload, retry with exponential backoff then fallback model."""
    models_to_try = [model or FLASH_MODEL, FALLBACK_MODEL]
    tried_models = set()
    for m in models_to_try:
        if m in tried_models:
            continue
        tried_models.add(m)
        url = GEMINI_URL.format(model=m, key=GEMINI_API_KEY)
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
        }
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        for attempt in range(2):
            if attempt == 1:
                print(f"      503 on {m} - waiting 15s before retry...", flush=True)
                time.sleep(15)
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    if m != (model or FLASH_MODEL):
                        print(f"      Used fallback model: {m}", flush=True)
                    return result["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                if e.code == 503:
                    continue
                raise RuntimeError(f"Gemini HTTP {e.code}: {body[:300]}")
            except Exception as e:
                raise RuntimeError(f"Gemini call failed: {e}")
        print(f"      {m} exhausted - trying fallback model...", flush=True)
    raise RuntimeError("All Gemini models exhausted")

def fetch_url_text(url, max_bytes=150_000, timeout=45):
    # Handle multiple URLs separated by " / "
    urls = [u.strip() for u in url.split(" / ") if u.strip().startswith("http")]
    primary_url = urls[0] if urls else url

    req = urllib.request.Request(primary_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes).decode("utf-8", errors="replace")
        text = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.DOTALL|re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>",   " ", text, flags=re.DOTALL|re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text[:50_000]
    except Exception as e:
        return f"[FETCH_ERROR: {e}]"

def load_pdf_base64(filename):
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def parse_json_loose(raw):
    clean = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE)
    clean = re.sub(r"\n?```$", "", clean.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except:
        pass
    start = clean.find("{")
    if start == -1:
        raise ValueError("No JSON found")
    depth, end = 0, start
    for i, ch in enumerate(clean[start:], start):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: end = i; break
    return json.loads(clean[start:end+1])

def normalize_relevance(r):
    r = str(r).lower()
    if r in ("high", "urgent"): return "urgent"
    if r in ("medium", "watch"): return "watch"
    return "fyi"

def boost_score(score, priority):
    boost = {1: 2, 2: 1, 3: 0}
    return min(10, int(score) + boost.get(priority, 0))

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

MARKET_PROMPT = """
You are an intelligence analyst for RBI Cash Management (CMIplus platform, CEE focus).
Extract the top {n_items} most relevant NEWS items from this source.

Source: {source_name} ({source_url})
Source focus: {focus}
Content:
{content}

Today: {scan_date}
Context: {context}

Focus on: payment regulations, instant payments, ISO 20022, VoP, EBICS, Open Banking,
PSD3, treasury technology, CEE/European banking, fraud prevention, SEPA.

Look back up to {lookback_days} days for relevant content. Include older items if they are
highly relevant to CMIplus topics - regulatory deadlines, major product launches, standards changes.

IMPORTANT: Translate any non-English content to English in your response.

For EACH item produce:
- title: Compelling English headline max 12 words
- summary_short: 2 sentences - what happened
- summary_detail: 5-7 sentences - full context, regulatory details, timeline, industry impact
- key_points: Array of 4 specific facts, numbers or quotes
- rbi_cash_management: 2-3 sentences - what this means for RBI Cash Management and CMIplus
- url: Direct article URL if found in content, else "{source_url}"
- source: "{source_name}"
- source_url: "{source_url}"
- relevance_score: 1-10 (10 = most critical for CMIplus/RBI)
- relevance: "urgent" if >=8, "watch" if >=5, "fyi" otherwise
- tags: Array of 2-4 tags from: {tags}
- date: "{scan_date}"
- article_date: Best estimate of when this article/item was published (YYYY-MM-DD format).
  Use date clues from content (e.g. "March 2026", "last week", "Q1 2026"). If unknown use "{scan_date}".

Respond ONLY with valid JSON:
{{"source":"{source_name}","items":[/* exactly {n_items} items */]}}
"""

THOUGHT_PROMPT = """
You are an intelligence analyst for RBI Cash Management (CMIplus platform, CEE focus).
Extract the top {n_items} most relevant THOUGHT LEADERSHIP insights from this source.

Source: {source_name} ({source_url})
Source focus: {focus}
Content:
{content}

Today: {scan_date}
Context: {context}

Focus: treasury strategy, AI in banking, cash management trends, payment transformation,
digital banking, corporate banking evolution, Open Banking, real-time treasury.

Look back up to {lookback_months} months for relevant content. Include recent reports and
research publications even if published several months ago.

For EACH item produce:
- title: Strategic English headline max 12 words
- summary_short: 2 sentences - core finding
- summary_detail: 5-7 sentences - full strategic context, methodology, key data, implications
- key_points: Array of 4 specific insights or statistics
- rbi_cash_management: 2-3 sentences - strategic implication for RBI Cash Management and CMIplus roadmap
- url: Direct article URL if found, else "{source_url}"
- source: "{source_name}"
- source_url: "{source_url}"
- relevance_score: 1-10
- relevance: "urgent" if >=8, "watch" if >=5, "fyi" otherwise
- tags: Array of 2-4 tags from: {tags}
- date: "{scan_date}"
- article_date: Best estimate of publication date (YYYY-MM-DD). Use content clues. If unknown use "{scan_date}".

Respond ONLY with valid JSON:
{{"source":"{source_name}","items":[/* exactly {n_items} items */]}}
"""

COMPETITOR_PROMPT = """
You are an intelligence analyst for RBI Cash Management (CMIplus platform, CEE focus).
Analyse {competitor}'s latest moves in corporate/transaction banking.

Source: {source_name} ({source_url})
Source focus: {focus}
Content:
{content}

Today: {scan_date}
Context: {context}

Focus: cash management products, CEE expansion, payment capabilities, API/digital banking,
treasury solutions, EBICS offerings, instant payments, partnership deals.

If specific news is not found, produce items based on known strategic directions
of {competitor} in European corporate banking - mark these as inferred.

For EACH item produce:
- title: Headline max 12 words
- summary_short: 2 sentences
- summary_detail: 4-6 sentences - context, product details, strategic rationale, CEE relevance
- key_points: Array of 3 specific facts or observations
- rbi_cash_management: 2 sentences - competitive implication for CMIplus
- url: Direct URL if found, else "{source_url}"
- source: "{source_name}"
- source_url: "{source_url}"
- competitor: "{competitor}"
- relevance_score: 1-10
- relevance: "urgent" if >=8, "watch" if >=5, "fyi" otherwise
- tags: Array of 2-4 tags from: {tags}
- date: "{scan_date}"
- inferred: true if based on inference, false if actual news
- article_date: Best estimate of publication date (YYYY-MM-DD). Use content clues. If unknown use "{scan_date}".

Respond ONLY with valid JSON:
{{"source":"{source_name}","competitor":"{competitor}","items":[/* exactly {n_items} items */]}}
"""

# ---------------------------------------------------------------------------
# Per-source extraction
# ---------------------------------------------------------------------------

def extract_source(src, prompt_template, scan_date, config, extra=None):
    name   = src["name"]
    url    = src["url"]
    prio   = src.get("priority", 2)
    focus  = src.get("focus", "treasury, payments, cash management")
    tags   = ", ".join(config.get("tags", ["ISO20022","CEE","EBICS","AI","InstantPayments"]))
    context = config.get("context", "CMIplus is RBI's cash management platform.")

    # Items count based on priority
    n_map = {
        1: config.get("items_priority_1", 3),
        2: config.get("items_priority_2", 2),
        3: config.get("items_priority_3", 1),
    }
    n_items = n_map.get(prio, 2)

    print(f"  [P{prio}] {name} (->{n_items} items): fetching...", flush=True)
    text = fetch_url_text(url)

    # Retry fetch once on timeout/error
    if text.startswith("[FETCH_ERROR"):
        print(f"      FAILED (attempt 1): {text[:60]} -- retrying...", flush=True)
        time.sleep(3)
        text = fetch_url_text(url)
        if text.startswith("[FETCH_ERROR"):
            print(f"      FAILED (attempt 2): {text[:60]}", flush=True)
            return []
        print(f"      Retry succeeded: {len(text):,} chars", flush=True)

    # Minimum content check - avoid hallucinated items from near-empty pages
    if len(text.strip()) < 500:
        print(f"      SKIPPED: only {len(text)} chars (too little content)", flush=True)
        return []

    print(f"      {len(text):,} chars -> Gemini...", flush=True)

    lookback_days   = config.get("market_lookback_days", 56)
    lookback_months = config.get("thought_lookback_months", 8)

    kwargs = {
        "source_name":    name,
        "source_url":     url.split(" / ")[0],
        "content":        text[:18_000],
        "scan_date":      scan_date,
        "focus":          focus,
        "context":        context,
        "tags":           tags,
        "n_items":        n_items,
        "lookback_days":  lookback_days,
        "lookback_months":lookback_months,
    }
    if extra:
        kwargs.update(extra)

    prompt = prompt_template.format(**kwargs)

    def _process_items(items_raw):
        for item in items_raw:
            raw_score               = item.get("relevance_score", 5)
            item["relevance_score"] = boost_score(raw_score, prio)
            if   item["relevance_score"] >= 8: item["relevance"] = "urgent"
            elif item["relevance_score"] >= 5: item["relevance"] = "watch"
            else:                              item["relevance"] = "fyi"
            item["source"]          = name
            item["source_url"]      = url.split(" / ")[0]
            item["priority"]        = prio
            item["article_date"]    = item.get("article_date", scan_date)
            if extra and "competitor" in extra:
                item["competitor"] = extra["competitor"]
        return items_raw

    # gemini_call handles 503 retries + fallback internally
    # Outer retry handles JSON parse errors (can happen after 503 recovery)
    for parse_attempt in range(2):
        try:
            raw    = gemini_call([{"text": prompt}], max_tokens=6000)
            result = parse_json_loose(raw)
            items  = result.get("items", [])
            items  = _process_items(items)
            print(f"      OK: {len(items)} items, scores: {[i['relevance_score'] for i in items]}", flush=True)
            return items
        except (ValueError, KeyError) as e:
            if parse_attempt == 0:
                print(f"      JSON parse error: {e} -- retrying once...", flush=True)
                time.sleep(5)
            else:
                print(f"      JSON parse error on retry: {e} -- giving up.", flush=True)
                return []
        except Exception as e:
            print(f"      Gemini ERROR: {e} -- giving up.", flush=True)
            return []

# ---------------------------------------------------------------------------
# Weekly briefing
# ---------------------------------------------------------------------------

def run_weekly_briefing(scan_date, sources_data):
    config = get_scan_config(sources_data)

    # Merge tags from sources.json into config
    if sources_data and "tags" in sources_data:
        config["tags"] = sources_data["tags"]

    print("\n--- MARKET NEWS ---", flush=True)
    market_sources = get_active_sources(sources_data, "market_news")
    print(f"  {len(market_sources)} active sources", flush=True)
    all_market = []
    for src in market_sources:
        items = extract_source(src, MARKET_PROMPT, scan_date, config)
        all_market.extend(items)
        time.sleep(1)

    all_market.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    for i, item in enumerate(all_market):
        item["rank"] = i + 1

    print(f"\n  Total market: {len(all_market)} items from: {list(set(i['source'] for i in all_market))}", flush=True)

    print("\n--- THOUGHT LEADERSHIP ---", flush=True)
    thought_sources = get_active_sources(sources_data, "thought_leadership")
    print(f"  {len(thought_sources)} active sources", flush=True)
    all_thought = []
    for src in thought_sources:
        items = extract_source(src, THOUGHT_PROMPT, scan_date, config)
        all_thought.extend(items)
        time.sleep(1)

    all_thought.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    for i, item in enumerate(all_thought):
        item["rank"] = i + 1

    print(f"\n  Total thought: {len(all_thought)} items", flush=True)

    print("\n--- COMPETITORS ---", flush=True)
    comp_sources = get_active_sources(sources_data, "competitors")
    print(f"  {len(comp_sources)} active sources", flush=True)
    all_competitors = []
    for src in comp_sources:
        competitor = src.get("name", src.get("competitor", "Unknown"))
        items = extract_source(src, COMPETITOR_PROMPT, scan_date, config,
                               extra={"competitor": competitor})
        all_competitors.extend(items)
        time.sleep(1)

    all_competitors.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    for i, item in enumerate(all_competitors):
        item["rank"] = i + 1

    print(f"\n  Total competitors: {len(all_competitors)} items", flush=True)

    # Executive summary
    print("\n--- EXECUTIVE SUMMARY ---", flush=True)
    top = (all_market[:3] + all_thought[:2] + all_competitors[:2])
    top_list = [{"title": i["title"], "summary_short": i.get("summary_short", "")} for i in top]
    top_json = json.dumps(top_list, indent=2)
    exec_prompt = (
        "You are a senior analyst for Raiffeisen Bank International. "
        "Write a comprehensive 5-6 sentence executive summary of the most important "
        "market developments, competitive moves and strategic trends for RBI Cash Management "
        "and CMIplus this week. Be specific - name regulations, companies, deadlines and figures. "
        "Focus on what requires attention or action. Based on:\n\n"
        + top_json
        + f"\n\nToday: {scan_date}\nReturn ONLY the summary text, no preamble, no JSON."
    )
    try:
        exec_summary = gemini_call([{"text": exec_prompt}], max_tokens=600).strip()
    except Exception as e:
        exec_summary = f"Scan complete: {len(all_market)} market, {len(all_thought)} thought, {len(all_competitors)} competitor items."

    return {
        "scan_date":         scan_date,
        "week_label":        f"Week of {scan_date}",
        "executive_summary": exec_summary,
        "market":            all_market,
        "thought":           all_thought,
        "competitors":       all_competitors,
        "source_stats": {
            "market_sources_used":      list(set(i["source"] for i in all_market)),
            "thought_sources_used":     list(set(i["source"] for i in all_thought)),
            "competitor_sources_used":  list(set(i["source"] for i in all_competitors)),
            "market_sources_all":       [s["name"] for s in get_active_sources(sources_data, "market_news")],
            "thought_sources_all":      [s["name"] for s in get_active_sources(sources_data, "thought_leadership")],
            "competitor_sources_all":   [s["name"] for s in get_active_sources(sources_data, "competitors")],
        }
    }

# ---------------------------------------------------------------------------
# Flagship analyses
# ---------------------------------------------------------------------------

FLAGSHIP_PROMPT = """
You are a senior analyst for RBI's CMIplus cash management platform.
Produce a comprehensive strategic analysis of this report.

Context: {context}
Report: "{title}" ({year})

Produce:
1. executive_summary: 4-5 sentences
2. key_stats: Array of 6-8 most important statistics
3. themes: Array of 5-6 themes, each: name, description (3-4 sentences), key_stat
4. key_actions: Array of 3-4 actions, each: action, urgency (HIGH/MEDIUM/LOW), rationale, timeline
5. competitive_implications: 2-3 sentences
6. case_studies: Corporate case studies from the report (if any), each:
   company, headline, key_achievement, lesson

Respond ONLY with valid JSON:
{{
  "report_id":"{report_id}","report_title":"{title}","report_year":"{year}","report_url":"{report_url}",
  "executive_summary":"...","key_stats":[],"themes":[],"key_actions":[],
  "competitive_implications":"...","case_studies":[],"scan_date":"{scan_date}"
}}
"""

def analyse_flagship_pdf(report, scan_date, context):
    print(f"  PDF: {report['file']} ...", flush=True)
    try:
        pdf_b64 = load_pdf_base64(report["file"])
    except FileNotFoundError:
        return _error_entry(report, scan_date, "PDF not found")

    prompt = FLAGSHIP_PROMPT.format(
        context=context, title=report["title"], year=report["year"],
        report_id=report["id"], report_url=report.get("report_url",""), scan_date=scan_date,
    )
    try:
        raw = gemini_call([
            {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
            {"text": prompt}
        ], max_tokens=16000)
        result = parse_json_loose(raw)
        result["report_url"] = report.get("report_url", "")
        print(f"      OK: {len(result.get('themes',[]))} themes, {len(result.get('case_studies',[]))} cases", flush=True)
        return result
    except Exception as e:
        print(f"      ERROR: {e}", flush=True)
        return _error_entry(report, scan_date, str(e))

def analyse_flagship_web(report, scan_date, context):
    print(f"  Web: {report['url']} ...", flush=True)
    page_text = fetch_url_text(report["url"])
    prompt = FLAGSHIP_PROMPT.format(
        context=context, title=report["title"], year=report["year"],
        report_id=report["id"], report_url=report.get("report_url",""), scan_date=scan_date,
    ) + f"\n\nContent:\n{page_text}"
    try:
        raw = gemini_call([{"text": prompt}], max_tokens=16000)
        result = parse_json_loose(raw)
        result["report_url"] = report.get("report_url", "")
        return result
    except Exception as e:
        print(f"      ERROR: {e}", flush=True)
        return _error_entry(report, scan_date, str(e))

def _error_entry(report, scan_date, error):
    return {
        "report_id": report["id"], "report_title": report["title"],
        "report_year": report["year"], "report_url": report.get("report_url",""),
        "executive_summary": f"Error: {error}", "key_stats": [], "themes": [],
        "key_actions": [], "competitive_implications": "", "case_studies": [],
        "scan_date": scan_date, "error": error,
    }

def run_flagship_analyses(scan_date, context):
    results = []
    for report in FLAGSHIP_REPORTS:
        r = analyse_flagship_pdf(report, scan_date, context) if report["source"]=="pdf" \
            else analyse_flagship_web(report, scan_date, context)
        results.append(r)
        time.sleep(2)
    return results

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_KEY environment variable not set")

    scan_date    = datetime.date.today().isoformat()
    sources_data = load_sources()
    config       = get_scan_config(sources_data)
    context      = config.get("context", "CMIplus is RBI's corporate cash management platform.")

    print(f"\n{'='*60}\nCMIplus Intelligence Cockpit - Scan {scan_date}\n{'='*60}", flush=True)

    print("\n=== WEEKLY BRIEFING ===", flush=True)
    briefing = run_weekly_briefing(scan_date, sources_data)
    with open("briefing.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    stats = briefing.get("source_stats", {})
    print(f"\nbriefing.json written:")
    print(f"  Market:     {len(briefing['market'])} items from {stats.get('market_sources_used',[])}")
    print(f"  Thought:    {len(briefing['thought'])} items from {stats.get('thought_sources_used',[])}")
    print(f"  Competitors:{len(briefing['competitors'])} items from {stats.get('competitor_sources_used',[])}")

    print("\n=== FLAGSHIP ANALYSES ===", flush=True)
    analyses = run_flagship_analyses(scan_date, context)
    with open("flagship-analyses.json", "w", encoding="utf-8") as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)
    print(f"flagship-analyses.json written ({len(analyses)} reports)", flush=True)
    print(f"\nScan complete. {scan_date}", flush=True)

if __name__ == "__main__":
    main()
