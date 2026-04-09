<!DOCTYPE html><html><head><meta charset="UTF-8"><title>scan.py</title>
<style>body{background:#1e1e1e;color:#d4d4d4;font-family:monospace;padding:20px;}pre{white-space:pre-wrap;font-size:13px;line-height:1.5;}button{position:fixed;top:20px;right:20px;background:#0066cc;color:white;border:none;padding:10px 20px;border-radius:6px;cursor:pointer;font-size:14px;}</style></head>
<body><button onclick="navigator.clipboard.writeText(document.getElementById('c').textContent).then(()=>this.textContent='Copied!').catch(()=>this.textContent='Select all + Ctrl+C')">Copy all</button>
<pre id="c">#!/usr/bin/env python3
&quot;&quot;&quot;
CMIplus Intelligence Cockpit - Weekly Scan
Runs every Monday 06:00 UTC via GitHub Actions.

Sources are configured in sources.json - no code changes needed to add/remove/reprioritise.

Produces:
  - briefing.json         : structured weekly briefing (market/thought/competitors)
  - flagship-analyses.json: deep analyses of 4 flagship reports
&quot;&quot;&quot;

import os, json, base64, urllib.request, urllib.error, datetime, re, time

GEMINI_API_KEY = os.environ.get(&quot;GEMINI_KEY&quot;, &quot;&quot;)
FLASH_MODEL    = &quot;gemini-2.5-flash&quot;
GEMINI_URL     = &quot;https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}&quot;
REPORTS_DIR    = os.path.join(os.path.dirname(__file__), &quot;reports&quot;)
SOURCES_FILE   = os.path.join(os.path.dirname(__file__), &quot;sources.json&quot;)

FLAGSHIP_REPORTS = [
    {&quot;id&quot;:&quot;ey_four_trends&quot;,       &quot;title&quot;:&quot;EY Four Trends Redefining Cash Management&quot;,  &quot;year&quot;:&quot;2025&quot;,    &quot;source&quot;:&quot;pdf&quot;,  &quot;file&quot;:&quot;ey-gl-four-trends-redefining-cash-management-08-2025.pdf&quot;,   &quot;report_url&quot;:&quot;https://phoefer.github.io/cmiplus-cockpit/reports/ey-gl-four-trends-redefining-cash-management-08-2025.pdf&quot;},
    {&quot;id&quot;:&quot;mckinsey_payments&quot;,    &quot;title&quot;:&quot;McKinsey Global Payments Report&quot;,             &quot;year&quot;:&quot;2025&quot;,    &quot;source&quot;:&quot;pdf&quot;,  &quot;file&quot;:&quot;the-2025-mckinsey-global-payments-report.pdf&quot;,                &quot;report_url&quot;:&quot;https://phoefer.github.io/cmiplus-cockpit/reports/the-2025-mckinsey-global-payments-report.pdf&quot;},
    {&quot;id&quot;:&quot;journeys_to_treasury&quot;, &quot;title&quot;:&quot;Journeys to Treasury&quot;,                        &quot;year&quot;:&quot;2025/26&quot;, &quot;source&quot;:&quot;pdf&quot;,  &quot;file&quot;:&quot;Journeys to Treasury 2025-26.pdf&quot;,                            &quot;report_url&quot;:&quot;https://phoefer.github.io/cmiplus-cockpit/reports/Journeys%20to%20Treasury%202025-26.pdf&quot;},
    {&quot;id&quot;:&quot;pwc_treasury_survey&quot;,  &quot;title&quot;:&quot;PwC Global Treasury Survey&quot;,                 &quot;year&quot;:&quot;2025&quot;,    &quot;source&quot;:&quot;web&quot;,  &quot;url&quot;:&quot;https://www.pwc.com/us/en/services/consulting/business-transformation/library/2025-global-treasury-survey.html&quot;, &quot;report_url&quot;:&quot;https://www.pwc.com/us/en/services/consulting/business-transformation/library/2025-global-treasury-survey.html&quot;},
]

# ---------------------------------------------------------------------------
# Load sources.json
# ---------------------------------------------------------------------------

def load_sources():
    &quot;&quot;&quot;Load and validate sources from sources.json.&quot;&quot;&quot;
    try:
        with open(SOURCES_FILE, &quot;r&quot;, encoding=&quot;utf-8&quot;) as f:
            data = json.load(f)
        print(f&quot;sources.json loaded (updated: {data.get(&#x27;meta&#x27;,{}).get(&#x27;last_updated&#x27;,&#x27;?&#x27;)})&quot;, flush=True)
        return data
    except Exception as e:
        print(f&quot;WARNING: Could not load sources.json: {e} - using fallback sources&quot;, flush=True)
        return None

def get_active_sources(sources_data, section_key):
    &quot;&quot;&quot;Return active sources for a section, sorted by priority.&quot;&quot;&quot;
    if not sources_data:
        return []
    sources = sources_data.get(section_key, [])
    active  = [s for s in sources if s.get(&quot;active&quot;, True)]
    active.sort(key=lambda x: x.get(&quot;priority&quot;, 2))
    return active

def get_scan_config(sources_data):
    &quot;&quot;&quot;Return scan_config from sources.json with defaults.&quot;&quot;&quot;
    defaults = {
        &quot;items_priority_1&quot;: 3,
        &quot;items_priority_2&quot;: 2,
        &quot;items_priority_3&quot;: 1,
        &quot;language&quot;: &quot;English&quot;,
        &quot;context&quot;: &quot;CMIplus is RBI&#x27;s corporate cash management platform for large corporates in CEE.&quot;,
    }
    if sources_data and &quot;scan_config&quot; in sources_data:
        defaults.update(sources_data[&quot;scan_config&quot;])
    return defaults

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HEADERS = {
    &quot;User-Agent&quot;: &quot;Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36&quot;,
    &quot;Accept&quot;: &quot;text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8&quot;,
    &quot;Accept-Language&quot;: &quot;en-US,en;q=0.9,de;q=0.8&quot;,
    &quot;Accept-Encoding&quot;: &quot;identity&quot;,
    &quot;Connection&quot;: &quot;keep-alive&quot;,
}

def gemini_call(parts, max_tokens=8000):
    url = GEMINI_URL.format(model=FLASH_MODEL, key=GEMINI_API_KEY)
    payload = {
        &quot;contents&quot;: [{&quot;parts&quot;: parts}],
        &quot;generationConfig&quot;: {&quot;maxOutputTokens&quot;: max_tokens, &quot;temperature&quot;: 0.3},
    }
    data = json.dumps(payload).encode(&quot;utf-8&quot;)
    req  = urllib.request.Request(url, data=data, headers={&quot;Content-Type&quot;: &quot;application/json&quot;})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode(&quot;utf-8&quot;))
            return result[&quot;candidates&quot;][0][&quot;content&quot;][&quot;parts&quot;][0][&quot;text&quot;]
    except urllib.error.HTTPError as e:
        body = e.read().decode(&quot;utf-8&quot;, errors=&quot;replace&quot;)
        raise RuntimeError(f&quot;Gemini HTTP {e.code}: {body[:300]}&quot;)

def fetch_url_text(url, max_bytes=150_000, timeout=45):
    # Handle multiple URLs separated by &quot; / &quot;
    urls = [u.strip() for u in url.split(&quot; / &quot;) if u.strip().startswith(&quot;http&quot;)]
    primary_url = urls[0] if urls else url

    req = urllib.request.Request(primary_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes).decode(&quot;utf-8&quot;, errors=&quot;replace&quot;)
        text = re.sub(r&quot;&lt;script[^&gt;]*&gt;.*?&lt;/script&gt;&quot;, &quot; &quot;, raw, flags=re.DOTALL|re.IGNORECASE)
        text = re.sub(r&quot;&lt;style[^&gt;]*&gt;.*?&lt;/style&gt;&quot;,   &quot; &quot;, text, flags=re.DOTALL|re.IGNORECASE)
        text = re.sub(r&quot;&lt;[^&gt;]+&gt;&quot;, &quot; &quot;, text)
        text = re.sub(r&quot;\s{3,}&quot;, &quot;\n\n&quot;, text)
        return text[:50_000]
    except Exception as e:
        return f&quot;[FETCH_ERROR: {e}]&quot;

def load_pdf_base64(filename):
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, &quot;rb&quot;) as f:
        return base64.b64encode(f.read()).decode(&quot;utf-8&quot;)

def parse_json_loose(raw):
    clean = re.sub(r&quot;^```[a-z]*\n?&quot;, &quot;&quot;, raw.strip(), flags=re.MULTILINE)
    clean = re.sub(r&quot;\n?```$&quot;, &quot;&quot;, clean.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except:
        pass
    start = clean.find(&quot;{&quot;)
    if start == -1:
        raise ValueError(&quot;No JSON found&quot;)
    depth, end = 0, start
    for i, ch in enumerate(clean[start:], start):
        if ch == &quot;{&quot;: depth += 1
        elif ch == &quot;}&quot;:
            depth -= 1
            if depth == 0: end = i; break
    return json.loads(clean[start:end+1])

def normalize_relevance(r):
    r = str(r).lower()
    if r in (&quot;high&quot;, &quot;urgent&quot;): return &quot;urgent&quot;
    if r in (&quot;medium&quot;, &quot;watch&quot;): return &quot;watch&quot;
    return &quot;fyi&quot;

def boost_score(score, priority):
    boost = {1: 2, 2: 1, 3: 0}
    return min(10, int(score) + boost.get(priority, 0))

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

MARKET_PROMPT = &quot;&quot;&quot;
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
- url: Direct article URL if found in content, else &quot;{source_url}&quot;
- source: &quot;{source_name}&quot;
- source_url: &quot;{source_url}&quot;
- relevance_score: 1-10 (10 = most critical for CMIplus/RBI)
- relevance: &quot;urgent&quot; if &gt;=8, &quot;watch&quot; if &gt;=5, &quot;fyi&quot; otherwise
- tags: Array of 2-4 tags from: {tags}
- date: &quot;{scan_date}&quot;
- article_date: Best estimate of when this article/item was published (YYYY-MM-DD format).
  Use date clues from content (e.g. &quot;March 2026&quot;, &quot;last week&quot;, &quot;Q1 2026&quot;). If unknown use &quot;{scan_date}&quot;.

Respond ONLY with valid JSON:
{{&quot;source&quot;:&quot;{source_name}&quot;,&quot;items&quot;:[/* exactly {n_items} items */]}}
&quot;&quot;&quot;

THOUGHT_PROMPT = &quot;&quot;&quot;
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
- url: Direct article URL if found, else &quot;{source_url}&quot;
- source: &quot;{source_name}&quot;
- source_url: &quot;{source_url}&quot;
- relevance_score: 1-10
- relevance: &quot;urgent&quot; if &gt;=8, &quot;watch&quot; if &gt;=5, &quot;fyi&quot; otherwise
- tags: Array of 2-4 tags from: {tags}
- date: &quot;{scan_date}&quot;
- article_date: Best estimate of publication date (YYYY-MM-DD). Use content clues. If unknown use &quot;{scan_date}&quot;.

Respond ONLY with valid JSON:
{{&quot;source&quot;:&quot;{source_name}&quot;,&quot;items&quot;:[/* exactly {n_items} items */]}}
&quot;&quot;&quot;

COMPETITOR_PROMPT = &quot;&quot;&quot;
You are an intelligence analyst for RBI Cash Management (CMIplus platform, CEE focus).
Analyse {competitor}&#x27;s latest moves in corporate/transaction banking.

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
- url: Direct URL if found, else &quot;{source_url}&quot;
- source: &quot;{source_name}&quot;
- source_url: &quot;{source_url}&quot;
- competitor: &quot;{competitor}&quot;
- relevance_score: 1-10
- relevance: &quot;urgent&quot; if &gt;=8, &quot;watch&quot; if &gt;=5, &quot;fyi&quot; otherwise
- tags: Array of 2-4 tags from: {tags}
- date: &quot;{scan_date}&quot;
- inferred: true if based on inference, false if actual news
- article_date: Best estimate of publication date (YYYY-MM-DD). Use content clues. If unknown use &quot;{scan_date}&quot;.

Respond ONLY with valid JSON:
{{&quot;source&quot;:&quot;{source_name}&quot;,&quot;competitor&quot;:&quot;{competitor}&quot;,&quot;items&quot;:[/* exactly {n_items} items */]}}
&quot;&quot;&quot;

# ---------------------------------------------------------------------------
# Per-source extraction
# ---------------------------------------------------------------------------

def extract_source(src, prompt_template, scan_date, config, extra=None):
    name   = src[&quot;name&quot;]
    url    = src[&quot;url&quot;]
    prio   = src.get(&quot;priority&quot;, 2)
    focus  = src.get(&quot;focus&quot;, &quot;treasury, payments, cash management&quot;)
    tags   = &quot;, &quot;.join(config.get(&quot;tags&quot;, [&quot;ISO20022&quot;,&quot;CEE&quot;,&quot;EBICS&quot;,&quot;AI&quot;,&quot;InstantPayments&quot;]))
    context = config.get(&quot;context&quot;, &quot;CMIplus is RBI&#x27;s cash management platform.&quot;)

    # Items count based on priority
    n_map = {
        1: config.get(&quot;items_priority_1&quot;, 3),
        2: config.get(&quot;items_priority_2&quot;, 2),
        3: config.get(&quot;items_priority_3&quot;, 1),
    }
    n_items = n_map.get(prio, 2)

    print(f&quot;  [P{prio}] {name} (-&gt;{n_items} items): fetching...&quot;, flush=True)
    text = fetch_url_text(url)

    # Retry fetch once on timeout/error
    if text.startswith(&quot;[FETCH_ERROR&quot;):
        print(f&quot;      FAILED (attempt 1): {text[:60]} -- retrying...&quot;, flush=True)
        time.sleep(3)
        text = fetch_url_text(url)
        if text.startswith(&quot;[FETCH_ERROR&quot;):
            print(f&quot;      FAILED (attempt 2): {text[:60]}&quot;, flush=True)
            return []
        print(f&quot;      Retry succeeded: {len(text):,} chars&quot;, flush=True)

    # Minimum content check - avoid hallucinated items from near-empty pages
    if len(text.strip()) &lt; 500:
        print(f&quot;      SKIPPED: only {len(text)} chars (too little content)&quot;, flush=True)
        return []

    print(f&quot;      {len(text):,} chars -&gt; Gemini...&quot;, flush=True)

    lookback_days   = config.get(&quot;market_lookback_days&quot;, 56)
    lookback_months = config.get(&quot;thought_lookback_months&quot;, 8)

    kwargs = {
        &quot;source_name&quot;:    name,
        &quot;source_url&quot;:     url.split(&quot; / &quot;)[0],
        &quot;content&quot;:        text[:18_000],
        &quot;scan_date&quot;:      scan_date,
        &quot;focus&quot;:          focus,
        &quot;context&quot;:        context,
        &quot;tags&quot;:           tags,
        &quot;n_items&quot;:        n_items,
        &quot;lookback_days&quot;:  lookback_days,
        &quot;lookback_months&quot;:lookback_months,
    }
    if extra:
        kwargs.update(extra)

    prompt = prompt_template.format(**kwargs)

    def _process_items(items_raw):
        for item in items_raw:
            raw_score               = item.get(&quot;relevance_score&quot;, 5)
            item[&quot;relevance_score&quot;] = boost_score(raw_score, prio)
            if   item[&quot;relevance_score&quot;] &gt;= 8: item[&quot;relevance&quot;] = &quot;urgent&quot;
            elif item[&quot;relevance_score&quot;] &gt;= 5: item[&quot;relevance&quot;] = &quot;watch&quot;
            else:                              item[&quot;relevance&quot;] = &quot;fyi&quot;
            item[&quot;source&quot;]          = name
            item[&quot;source_url&quot;]      = url.split(&quot; / &quot;)[0]
            item[&quot;priority&quot;]        = prio
            item[&quot;article_date&quot;]    = item.get(&quot;article_date&quot;, scan_date)
            if extra and &quot;competitor&quot; in extra:
                item[&quot;competitor&quot;] = extra[&quot;competitor&quot;]
        return items_raw

    for attempt in range(2):
        try:
            raw    = gemini_call([{&quot;text&quot;: prompt}], max_tokens=6000)
            result = parse_json_loose(raw)
            items  = result.get(&quot;items&quot;, [])
            items  = _process_items(items)
            print(f&quot;      OK: {len(items)} items, scores: {[i[&#x27;relevance_score&#x27;] for i in items]}&quot;, flush=True)
            return items
        except Exception as e:
            if attempt == 0:
                print(f&quot;      Gemini ERROR (attempt 1): {e} -- retrying in 5s...&quot;, flush=True)
                time.sleep(5)
            else:
                print(f&quot;      Gemini ERROR (attempt 2): {e} -- giving up.&quot;, flush=True)
                return []

# ---------------------------------------------------------------------------
# Weekly briefing
# ---------------------------------------------------------------------------

def run_weekly_briefing(scan_date, sources_data):
    config = get_scan_config(sources_data)

    # Merge tags from sources.json into config
    if sources_data and &quot;tags&quot; in sources_data:
        config[&quot;tags&quot;] = sources_data[&quot;tags&quot;]

    print(&quot;\n--- MARKET NEWS ---&quot;, flush=True)
    market_sources = get_active_sources(sources_data, &quot;market_news&quot;)
    print(f&quot;  {len(market_sources)} active sources&quot;, flush=True)
    all_market = []
    for src in market_sources:
        items = extract_source(src, MARKET_PROMPT, scan_date, config)
        all_market.extend(items)
        time.sleep(1)

    all_market.sort(key=lambda x: x.get(&quot;relevance_score&quot;, 0), reverse=True)
    for i, item in enumerate(all_market):
        item[&quot;rank&quot;] = i + 1

    print(f&quot;\n  Total market: {len(all_market)} items from: {list(set(i[&#x27;source&#x27;] for i in all_market))}&quot;, flush=True)

    print(&quot;\n--- THOUGHT LEADERSHIP ---&quot;, flush=True)
    thought_sources = get_active_sources(sources_data, &quot;thought_leadership&quot;)
    print(f&quot;  {len(thought_sources)} active sources&quot;, flush=True)
    all_thought = []
    for src in thought_sources:
        items = extract_source(src, THOUGHT_PROMPT, scan_date, config)
        all_thought.extend(items)
        time.sleep(1)

    all_thought.sort(key=lambda x: x.get(&quot;relevance_score&quot;, 0), reverse=True)
    for i, item in enumerate(all_thought):
        item[&quot;rank&quot;] = i + 1

    print(f&quot;\n  Total thought: {len(all_thought)} items&quot;, flush=True)

    print(&quot;\n--- COMPETITORS ---&quot;, flush=True)
    comp_sources = get_active_sources(sources_data, &quot;competitors&quot;)
    print(f&quot;  {len(comp_sources)} active sources&quot;, flush=True)
    all_competitors = []
    for src in comp_sources:
        competitor = src.get(&quot;name&quot;, src.get(&quot;competitor&quot;, &quot;Unknown&quot;))
        items = extract_source(src, COMPETITOR_PROMPT, scan_date, config,
                               extra={&quot;competitor&quot;: competitor})
        all_competitors.extend(items)
        time.sleep(1)

    all_competitors.sort(key=lambda x: x.get(&quot;relevance_score&quot;, 0), reverse=True)
    for i, item in enumerate(all_competitors):
        item[&quot;rank&quot;] = i + 1

    print(f&quot;\n  Total competitors: {len(all_competitors)} items&quot;, flush=True)

    # Executive summary
    print(&quot;\n--- EXECUTIVE SUMMARY ---&quot;, flush=True)
    top = (all_market[:3] + all_thought[:2] + all_competitors[:2])
    top_list = [{&quot;title&quot;: i[&quot;title&quot;], &quot;summary_short&quot;: i.get(&quot;summary_short&quot;, &quot;&quot;)} for i in top]
    top_json = json.dumps(top_list, indent=2)
    exec_prompt = (
        &quot;You are a senior analyst for Raiffeisen Bank International. &quot;
        &quot;Write a comprehensive 5-6 sentence executive summary of the most important &quot;
        &quot;market developments, competitive moves and strategic trends for RBI Cash Management &quot;
        &quot;and CMIplus this week. Be specific - name regulations, companies, deadlines and figures. &quot;
        &quot;Focus on what requires attention or action. Based on:\n\n&quot;
        + top_json
        + f&quot;\n\nToday: {scan_date}\nReturn ONLY the summary text, no preamble, no JSON.&quot;
    )
    try:
        exec_summary = gemini_call([{&quot;text&quot;: exec_prompt}], max_tokens=600).strip()
    except Exception as e:
        exec_summary = f&quot;Scan complete: {len(all_market)} market, {len(all_thought)} thought, {len(all_competitors)} competitor items.&quot;

    return {
        &quot;scan_date&quot;:         scan_date,
        &quot;week_label&quot;:        f&quot;Week of {scan_date}&quot;,
        &quot;executive_summary&quot;: exec_summary,
        &quot;market&quot;:            all_market,
        &quot;thought&quot;:           all_thought,
        &quot;competitors&quot;:       all_competitors,
        &quot;source_stats&quot;: {
            &quot;market_sources_used&quot;:      list(set(i[&quot;source&quot;] for i in all_market)),
            &quot;thought_sources_used&quot;:     list(set(i[&quot;source&quot;] for i in all_thought)),
            &quot;competitor_sources_used&quot;:  list(set(i[&quot;source&quot;] for i in all_competitors)),
            &quot;market_sources_all&quot;:       [s[&quot;name&quot;] for s in get_active_sources(sources_data, &quot;market_news&quot;)],
            &quot;thought_sources_all&quot;:      [s[&quot;name&quot;] for s in get_active_sources(sources_data, &quot;thought_leadership&quot;)],
            &quot;competitor_sources_all&quot;:   [s[&quot;name&quot;] for s in get_active_sources(sources_data, &quot;competitors&quot;)],
        }
    }

# ---------------------------------------------------------------------------
# Flagship analyses
# ---------------------------------------------------------------------------

FLAGSHIP_PROMPT = &quot;&quot;&quot;
You are a senior analyst for RBI&#x27;s CMIplus cash management platform.
Produce a comprehensive strategic analysis of this report.

Context: {context}
Report: &quot;{title}&quot; ({year})

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
  &quot;report_id&quot;:&quot;{report_id}&quot;,&quot;report_title&quot;:&quot;{title}&quot;,&quot;report_year&quot;:&quot;{year}&quot;,&quot;report_url&quot;:&quot;{report_url}&quot;,
  &quot;executive_summary&quot;:&quot;...&quot;,&quot;key_stats&quot;:[],&quot;themes&quot;:[],&quot;key_actions&quot;:[],
  &quot;competitive_implications&quot;:&quot;...&quot;,&quot;case_studies&quot;:[],&quot;scan_date&quot;:&quot;{scan_date}&quot;
}}
&quot;&quot;&quot;

def analyse_flagship_pdf(report, scan_date, context):
    print(f&quot;  PDF: {report[&#x27;file&#x27;]} ...&quot;, flush=True)
    try:
        pdf_b64 = load_pdf_base64(report[&quot;file&quot;])
    except FileNotFoundError:
        return _error_entry(report, scan_date, &quot;PDF not found&quot;)

    prompt = FLAGSHIP_PROMPT.format(
        context=context, title=report[&quot;title&quot;], year=report[&quot;year&quot;],
        report_id=report[&quot;id&quot;], report_url=report.get(&quot;report_url&quot;,&quot;&quot;), scan_date=scan_date,
    )
    try:
        raw = gemini_call([
            {&quot;inline_data&quot;: {&quot;mime_type&quot;: &quot;application/pdf&quot;, &quot;data&quot;: pdf_b64}},
            {&quot;text&quot;: prompt}
        ], max_tokens=16000)
        result = parse_json_loose(raw)
        result[&quot;report_url&quot;] = report.get(&quot;report_url&quot;, &quot;&quot;)
        print(f&quot;      OK: {len(result.get(&#x27;themes&#x27;,[]))} themes, {len(result.get(&#x27;case_studies&#x27;,[]))} cases&quot;, flush=True)
        return result
    except Exception as e:
        print(f&quot;      ERROR: {e}&quot;, flush=True)
        return _error_entry(report, scan_date, str(e))

def analyse_flagship_web(report, scan_date, context):
    print(f&quot;  Web: {report[&#x27;url&#x27;]} ...&quot;, flush=True)
    page_text = fetch_url_text(report[&quot;url&quot;])
    prompt = FLAGSHIP_PROMPT.format(
        context=context, title=report[&quot;title&quot;], year=report[&quot;year&quot;],
        report_id=report[&quot;id&quot;], report_url=report.get(&quot;report_url&quot;,&quot;&quot;), scan_date=scan_date,
    ) + f&quot;\n\nContent:\n{page_text}&quot;
    try:
        raw = gemini_call([{&quot;text&quot;: prompt}], max_tokens=16000)
        result = parse_json_loose(raw)
        result[&quot;report_url&quot;] = report.get(&quot;report_url&quot;, &quot;&quot;)
        return result
    except Exception as e:
        print(f&quot;      ERROR: {e}&quot;, flush=True)
        return _error_entry(report, scan_date, str(e))

def _error_entry(report, scan_date, error):
    return {
        &quot;report_id&quot;: report[&quot;id&quot;], &quot;report_title&quot;: report[&quot;title&quot;],
        &quot;report_year&quot;: report[&quot;year&quot;], &quot;report_url&quot;: report.get(&quot;report_url&quot;,&quot;&quot;),
        &quot;executive_summary&quot;: f&quot;Error: {error}&quot;, &quot;key_stats&quot;: [], &quot;themes&quot;: [],
        &quot;key_actions&quot;: [], &quot;competitive_implications&quot;: &quot;&quot;, &quot;case_studies&quot;: [],
        &quot;scan_date&quot;: scan_date, &quot;error&quot;: error,
    }

def run_flagship_analyses(scan_date, context):
    results = []
    for report in FLAGSHIP_REPORTS:
        r = analyse_flagship_pdf(report, scan_date, context) if report[&quot;source&quot;]==&quot;pdf&quot; \
            else analyse_flagship_web(report, scan_date, context)
        results.append(r)
        time.sleep(2)
    return results

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not GEMINI_API_KEY:
        raise RuntimeError(&quot;GEMINI_KEY environment variable not set&quot;)

    scan_date    = datetime.date.today().isoformat()
    sources_data = load_sources()
    config       = get_scan_config(sources_data)
    context      = config.get(&quot;context&quot;, &quot;CMIplus is RBI&#x27;s corporate cash management platform.&quot;)

    print(f&quot;\n{&#x27;=&#x27;*60}\nCMIplus Intelligence Cockpit - Scan {scan_date}\n{&#x27;=&#x27;*60}&quot;, flush=True)

    print(&quot;\n=== WEEKLY BRIEFING ===&quot;, flush=True)
    briefing = run_weekly_briefing(scan_date, sources_data)
    with open(&quot;briefing.json&quot;, &quot;w&quot;, encoding=&quot;utf-8&quot;) as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)
    stats = briefing.get(&quot;source_stats&quot;, {})
    print(f&quot;\nbriefing.json written:&quot;)
    print(f&quot;  Market:     {len(briefing[&#x27;market&#x27;])} items from {stats.get(&#x27;market_sources_used&#x27;,[])}&quot;)
    print(f&quot;  Thought:    {len(briefing[&#x27;thought&#x27;])} items from {stats.get(&#x27;thought_sources_used&#x27;,[])}&quot;)
    print(f&quot;  Competitors:{len(briefing[&#x27;competitors&#x27;])} items from {stats.get(&#x27;competitor_sources_used&#x27;,[])}&quot;)

    print(&quot;\n=== FLAGSHIP ANALYSES ===&quot;, flush=True)
    analyses = run_flagship_analyses(scan_date, context)
    with open(&quot;flagship-analyses.json&quot;, &quot;w&quot;, encoding=&quot;utf-8&quot;) as f:
        json.dump(analyses, f, ensure_ascii=False, indent=2)
    print(f&quot;flagship-analyses.json written ({len(analyses)} reports)&quot;, flush=True)
    print(f&quot;\nScan complete. {scan_date}&quot;, flush=True)

if __name__ == &quot;__main__&quot;:
    main()
</pre></body></html>
