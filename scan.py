#!/usr/bin/env python3
"""
CMIplus Weekly Intelligence Cockpit — Weekly Scan Script v4
Fixed: robust parsing of long responses with markdown fences.
"""

import json
import os
import re
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
    tags = ", ".join(sources["tags"])
    week = get_week_label()
    p1 = [s for s in sources["market_news"] if s["active"] and s["priority"] == 1]
    p2 = [s for s in sources["market_news"] if s["active"] and s["priority"] == 2]
    n1 = cfg.get("items_priority_1", 3)
    n2 = cfg.get("items_priority_2", 1)
    total = min(len(p1) * n1 + len(p2) * n2, 10)  # cap at 10
    p1_str = ", ".join([s["name"] for s in p1])
    p2_str = ", ".join([s["name"] for s in p2]) if p2 else "none"

    return f"""Strategic intelligence analyst for RBI CMIplus cash management platform.
Context: {context}

Search for MARKET NEWS from last 7 days ({week}).
Priority sources ({n1} items each): {p1_str}
Secondary sources ({n2} item each): {p2_str}
Topics: ISO 20022, SEPA, instant payments, VoP, eBAM, EBICS, corporate treasury, CEE banking, PSD3

Tags available: {tags}

Return a JSON array of {total} objects. Each object has EXACTLY these fields:
title, summary (2-3 sentences), sowhat (1-2 sentences CMIplus implication), relevance (urgent/watch/fyi), tags (array of 1-3 from available tags), source, date, url

IMPORTANT: Return ONLY the raw JSON array. Start your response with [ and end with ]. No markdown, no explanation."""


def build_thought_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = ", ".join(sources["tags"])
    active = [s for s in sources["thought_leadership"] if s["active"]]
    names = ", ".join([s["name"] for s in active])
    n = min(len(active) * 2, 10)  # cap at 10

    return f"""Strategic intelligence analyst for RBI CMIplus cash management platform.
Context: {context}

Search for THOUGHT LEADERSHIP reports/whitepapers/surveys from last 12 months from: {names}
Topics: cash management strategy, treasury transformation, open banking, payments, CEE banking

Tags available: {tags}

Return a JSON array of {n} objects. Each object has EXACTLY these fields:
title, key_insight (2-3 sentences), implications (2-3 sentences CMIplus strategy implication), relevance (urgent/watch/fyi), tags (array of 1-3), source, published (Month Year), url

IMPORTANT: Return ONLY the raw JSON array. Start your response with [ and end with ]. No markdown, no explanation."""


def build_competitor_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = ", ".join(sources["tags"])
    active = [s for s in sources["competitors"] if s["active"]]
    names = ", ".join([s["name"] for s in active])
    n = min(len(active) * 2, 14)  # cap at 14

    return f"""Strategic intelligence analyst for RBI CMIplus cash management platform.
Context: {context}

Search for recent news (last 4 weeks) from these competitors: {names}
Focus: cash management, API banking, corporate banking innovations, CEE expansion, VoP, instant payments.

Tags available: {tags}

Return a JSON array of {n} objects covering as many different competitors as possible. Each object has EXACTLY these fields:
title, competitor (exact bank name), summary (2-3 sentences), sowhat (1-2 sentences threat/opportunity for CMIplus), relevance (urgent/watch/fyi), tags (array of 1-3), source, date, url

IMPORTANT: Return ONLY the raw JSON array. Start your response with [ and end with ]. No markdown, no explanation."""


def call_gemini(prompt):
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192}
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
        raise ValueError(f"Bad response: {e}")


def parse_json_array(text):
    """Extract JSON array from text, handling markdown fences and extra content."""
    text = text.strip()

    # Remove markdown fences first
    if "```" in text:
        # Extract content between first ``` and last ```
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```\s*$', '', text)
        text = text.strip()

    # Now try to find the JSON array
    # Find the first [ and the matching last ]
    start = text.find('[')
    if start == -1:
        raise ValueError(f"No JSON array found in response. First 200 chars: {text[:200]}")

    # Find matching closing bracket by counting nesting
    depth = 0
    end = -1
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
            continue
        if c == '\\' and in_string:
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        raise ValueError(f"Could not find closing bracket. Text length: {len(text)}")

    json_str = text[start:end+1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Try to fix common issues: trailing commas, control characters
        json_str_clean = re.sub(r',\s*([}\]])', r'\1', json_str)  # remove trailing commas
        json_str_clean = re.sub(r'[\x00-\x1f\x7f]', ' ', json_str_clean)  # remove control chars
        try:
            return json.loads(json_str_clean)
        except json.JSONDecodeError:
            raise ValueError(f"JSON parse failed: {e}. First 300 chars of extracted: {json_str[:300]}")


def safe_call(prompt, label):
    print(f"  Calling Gemini for {label}...")
    try:
        response = call_gemini(prompt)
        text = extract_text(response)
        print(f"  Response length: {len(text)} chars")
        items = parse_json_array(text)
        if not isinstance(items, list):
            items = []
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
    m = "; ".join([i.get("title","") for i in market[:5]])
    t = "; ".join([i.get("title","") for i in thought[:3]])
    c = "; ".join([f"{i.get('competitor','')}: {i.get('title','')}" for i in competitors[:5]])

    prompt = f"""Write a 4-5 sentence executive summary for {week}.
Context: {context}
Market news: {m}
Thought leadership: {t}
Competitor moves: {c}

Name 2-3 key themes, state most urgent action for CMIplus, highlight most relevant competitor move.
Return ONLY plain text. No JSON. No markdown. No bullets."""

    try:
        response = call_gemini(prompt)
        text = extract_text(response)
        if text.startswith("[") or text.startswith("{"):
            return "Weekly scan complete. See sections below for details."
        return text
    except Exception as e:
        print(f"  Executive summary error: {e}", file=sys.stderr)
        return "Weekly scan complete. See sections below for details."


def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    print("Loading sources...")
    sources = load_sources()
    week = get_week_label()

    print("Scanning market news (last 7 days)...")
    market = safe_call(build_market_prompt(sources), "market")

    print("Scanning thought leadership (last 12 months)...")
    thought = safe_call(build_thought_prompt(sources), "thought")

    print("Scanning competitors (last 4 weeks)...")
    competitors = safe_call(build_competitor_prompt(sources), "competitors")

    print("Generating executive summary...")
    executive_summary = generate_executive_summary(market, thought, competitors, week, sources)

    briefing = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
