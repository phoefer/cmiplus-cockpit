#!/usr/bin/env python3
"""
CMIplus Weekly Intelligence Cockpit — Weekly Scan Script v2
Improvements:
- Thought leadership: 12-month lookback, deeper analysis format
- Tagging: items tagged with CM taxonomy categories
- Source priority: priority 1 sources get more items
- Competitor grouping: each item tagged with competitor name
- Separate executive summary call
Uses Google Gemini API with Google Search grounding.
"""

import json
import os
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.error

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def load_sources():
    with open("sources.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_week_label():
    now = datetime.now(timezone.utc)
    day = now.weekday()
    delta = now.day - day
    try:
        monday = now.replace(day=delta, hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        import calendar
        prev_month = now.month - 1 or 12
        prev_year = now.year if now.month > 1 else now.year - 1
        days_in_prev = calendar.monthrange(prev_year, prev_month)[1]
        monday = now.replace(year=prev_year, month=prev_month,
                             day=days_in_prev + delta, hour=0, minute=0, second=0, microsecond=0)
    sunday_day = monday.day + 6
    try:
        sunday = monday.replace(day=sunday_day)
    except ValueError:
        import calendar
        days_in_month = calendar.monthrange(monday.year, monday.month)[1]
        overflow = sunday_day - days_in_month
        next_month = monday.month + 1 if monday.month < 12 else 1
        next_year = monday.year if monday.month < 12 else monday.year + 1
        sunday = monday.replace(year=next_year, month=next_month, day=overflow)
    fmt = lambda d: d.strftime("%-d %b")
    return f"Week of {fmt(monday)} - {fmt(sunday)} {now.year}"


def build_market_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = sources["tags"]
    week = get_week_label()
    now_iso = datetime.now(timezone.utc).isoformat()
    p1_sources = [s for s in sources["market_news"] if s["active"] and s["priority"] == 1]
    p2_sources = [s for s in sources["market_news"] if s["active"] and s["priority"] == 2]
    p1_items = cfg.get("items_priority_1", 3)
    p2_items = cfg.get("items_priority_2", 1)
    total = len(p1_sources) * p1_items + len(p2_sources) * p2_items
    p1_focus = "; ".join([f"{s['name']} ({s['focus']})" for s in p1_sources])
    p2_focus = "; ".join([f"{s['name']} ({s['focus']})" for s in p2_sources]) if p2_sources else "none"
    tags_str = ", ".join(tags)

    return f"""You are a strategic intelligence analyst for a cash management platform product owner at RBI (Raiffeisen Bank International).
Context: {context}

Search for MARKET NEWS published in the LAST 7 DAYS ({week}).

HIGH PRIORITY sources (find {p1_items} items each): {p1_focus}
MEDIUM PRIORITY sources (find {p2_items} item each): {p2_focus}

Focus: ISO 20022, SEPA, instant payments, VoP, eBAM, EBICS, H2H, corporate treasury, CEE banking, PSD3, open banking APIs

For each item assign 1-3 tags from: {tags_str}

Return ONLY raw JSON, no markdown fences, exactly {total} items:

{{"generated_at":"{now_iso}","week_label":"{week}","items":[{{"title":"headline","summary":"2-3 sentence factual summary","sowhat":"1-2 sentences implication for CMIplus","relevance":"urgent|watch|fyi","tags":["tag1"],"source":"name","date":"date","url":"https://..."}}]}}

RAW JSON ONLY."""


def build_thought_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = sources["tags"]
    now_iso = datetime.now(timezone.utc).isoformat()
    week = get_week_label()
    active = [s for s in sources["thought_leadership"] if s["active"]]
    focus = "; ".join([f"{s['name']} ({s['focus']})" for s in active])
    tags_str = ", ".join(tags)
    n = len(active) * 2

    return f"""You are a strategic intelligence analyst for a cash management platform product owner at RBI (Raiffeisen Bank International).
Context: {context}

Search for THOUGHT LEADERSHIP content published in the LAST 12 MONTHS from: {focus}

Look for: strategic reports, whitepapers, research papers, annual outlooks, industry surveys, deep-dive analyses. NOT daily news.

Focus: cash management strategy, treasury transformation, open banking, API banking, payments innovation, digital banking, CEE banking

For each item assign 1-3 tags from: {tags_str}

Return ONLY raw JSON, no markdown fences, exactly {n} items:

{{"generated_at":"{now_iso}","week_label":"{week}","items":[{{"title":"headline","key_insight":"2-3 sentence most important strategic insight","implications":"2-3 sentences what this means for CMIplus strategy or roadmap","relevance":"urgent|watch|fyi","tags":["tag1"],"source":"name","published":"Month Year","url":"https://..."}}]}}

RAW JSON ONLY."""


def build_competitor_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = sources["tags"]
    now_iso = datetime.now(timezone.utc).isoformat()
    week = get_week_label()
    active = [s for s in sources["competitors"] if s["active"]]
    tags_str = ", ".join(tags)
    n = len(active) * 2
    competitor_list = "\n".join([f"- {s['name']}: {s['focus']}" for s in active])

    return f"""You are a strategic intelligence analyst for a cash management platform product owner at RBI (Raiffeisen Bank International).
Context: {context}

Search for news from these COMPETITORS in cash management (last 4 weeks):
{competitor_list}

Focus: cash management launches, API banking, corporate banking innovations, CEE expansion, VoP, instant payments.

For each item assign 1-3 tags from: {tags_str}
Each item MUST have a "competitor" field with the exact bank name.

Return ONLY raw JSON, no markdown fences, exactly {n} items covering as many different competitors as possible:

{{"generated_at":"{now_iso}","week_label":"{week}","items":[{{"title":"headline","competitor":"Bank Name","summary":"2-3 sentence factual summary","sowhat":"1-2 sentences implication for CMIplus — threat, opportunity or benchmark","relevance":"urgent|watch|fyi","tags":["tag1"],"source":"name","date":"date","url":"https://..."}}]}}

RAW JSON ONLY."""


def call_gemini(prompt):
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}
    }
    url = f"{API_URL}?key={GEMINI_API_KEY}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_text(response):
    try:
        parts = response["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError) as e:
        raise ValueError(f"Bad response structure: {e}\n{json.dumps(response)[:300]}")


def extract_json(response):
    text = extract_text(response)
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()
    return json.loads(text)


def safe_call(prompt, label):
    print(f"  Calling Gemini for {label}...")
    try:
        response = call_gemini(prompt)
        result = extract_json(response)
        items = result.get("items", [])
        print(f"  OK {label}: {len(items)} items")
        return items
    except urllib.error.HTTPError as e:
        print(f"  FAIL {label} API {e.code}: {e.read().decode()[:300]}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  FAIL {label}: {e}", file=sys.stderr)
        return []


def generate_executive_summary(market, thought, competitors, week, sources):
    context = sources["scan_config"]["context"]
    m_titles = "; ".join([i.get("title","") for i in market[:5]])
    t_titles = "; ".join([i.get("title","") for i in thought[:3]])
    c_titles = "; ".join([f"{i.get('competitor','')}: {i.get('title','')}" for i in competitors[:5]])

    prompt = f"""You are a strategic intelligence analyst.
Context: {context}

Write a 4-5 sentence executive summary for {week} based on:
Market news: {m_titles}
Thought leadership: {t_titles}
Competitor moves: {c_titles}

The summary must: name 2-3 key themes, state the most urgent action for CMIplus, highlight the most relevant competitor move.
Return ONLY plain text. No JSON. No markdown. No bullet points."""

    try:
        response = call_gemini(prompt)
        text = extract_text(response)
        if text.startswith("{"):
            return "Weekly scan complete — see sections below."
        return text
    except Exception as e:
        print(f"  Executive summary error: {e}", file=sys.stderr)
        return "Weekly scan complete — see sections below."


def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    print("Loading sources...")
    sources = load_sources()
    week = get_week_label()
    now_iso = datetime.now(timezone.utc).isoformat()

    print("Scanning market news (last 7 days)...")
    market = safe_call(build_market_prompt(sources), "market")

    print("Scanning thought leadership (last 12 months)...")
    thought = safe_call(build_thought_prompt(sources), "thought")

    print("Scanning competitors (last 4 weeks)...")
    competitors = safe_call(build_competitor_prompt(sources), "competitors")

    print("Generating executive summary...")
    executive_summary = generate_executive_summary(market, thought, competitors, week, sources)

    briefing = {
        "generated_at": now_iso,
        "week_label": week,
        "executive_summary": executive_summary,
        "market": market,
        "thought": thought,
        "competitors": competitors
    }

    with open("briefing.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)

    print(f"\nDone: {week}")
    print(f"  Market:      {len(market)} items")
    print(f"  Thought:     {len(thought)} items")
    print(f"  Competitors: {len(competitors)} items")


if __name__ == "__main__":
    main()
