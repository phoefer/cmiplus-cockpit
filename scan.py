#!/usr/bin/env python3
"""
CMIplus Weekly Intelligence Cockpit — Weekly Scan Script v5
Fixed: increased maxOutputTokens, reduced item counts, better truncation handling.
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
MAX_TOKENS = 16000  # increased from 8192


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
    p1_str = ", ".join([s["name"] for s in p1])
    p2_str = ", ".join([s["name"] for s in p2]) if p2 else "none"
    # Keep item count small to avoid truncation
    total = 6

    return f"""You are a strategic intelligence analyst for RBI CMIplus.
Context: {context}

Use Google Search to find MARKET NEWS from last 7 days ({week}).
Sources: {p1_str}, {p2_str}
Topics: ISO 20022, SEPA, instant payments, VoP, eBAM, EBICS, corporate treasury, CEE banking

Tags: {tags}

CRITICAL URL RULE: Only include the exact URL that Google Search returned for each article.
Never construct, guess or hallucinate a URL. If you are not 100% certain of the exact URL, use "" for the url field.

Return a JSON array of exactly {total} items. Keep each field concise (max 2 sentences per field).
Each item: title, summary, sowhat, relevance (urgent/watch/fyi), tags (array max 2), source, date, url

Start with [ end with ]. No markdown. No explanation. JSON only."""


def build_thought_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = ", ".join(sources["tags"])
    active = [s for s in sources["thought_leadership"] if s["active"]]
    names = ", ".join([s["name"] for s in active])
    n = 6  # fixed small number

    return f"""You are a strategic intelligence analyst for RBI CMIplus.
Context: {context}

Use Google Search to find THOUGHT LEADERSHIP reports from last 12 months from: {names}
Topics: cash management, treasury transformation, open banking, payments, CEE

Tags: {tags}

CRITICAL URL RULE: Only include the exact URL that Google Search returned for each article.
Never construct, guess or hallucinate a URL. If you are not 100% certain of the exact URL, use "" for the url field.

Return a JSON array of exactly {n} items. Keep each field concise (max 2 sentences).
Each item: title, key_insight, implications, relevance (urgent/watch/fyi), tags (array max 2), source, published, url

Start with [ end with ]. No markdown. No explanation. JSON only."""


def build_competitor_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = ", ".join(sources["tags"])
    active = [s for s in sources["competitors"] if s["active"]]
    names = ", ".join([s["name"] for s in active])
    n = 6  # fixed small number

    return f"""You are a strategic intelligence analyst for RBI CMIplus.
Context: {context}

Use Google Search to find news (last 4 weeks) from: {names}
Focus: cash management, API banking, corporate banking, CEE, VoP, instant payments.

Tags: {tags}

CRITICAL URL RULE: Only include the exact URL that Google Search returned for each article.
Never construct, guess or hallucinate a URL. If you are not 100% certain of the exact URL, use "" for the url field.

Return a JSON array of exactly {n} items covering different competitors. Keep each field concise (max 2 sentences).
Each item: title, competitor, summary, sowhat, relevance (urgent/watch/fyi), tags (array max 2), source, date, url

Start with [ end with ]. No markdown. No explanation. JSON only."""


def call_gemini(prompt):
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": MAX_TOKENS,
            "responseMimeType": "text/plain"
        }
    }
    url = f"{API_URL}?key={GEMINI_API_KEY}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_text(response):
    try:
        parts = response["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError) as e:
        raise ValueError(f"Bad response structure: {e}")


def parse_json_array(text):
    """Extract JSON array robustly from model output."""
    text = text.strip()

    # Strip markdown fences
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?\s*```\s*$', '', text)
    text = text.strip()

    # Find first [
    start = text.find('[')
    if start == -1:
        raise ValueError(f"No '[' found. Preview: {text[:300]}")

    # Find matching ] using bracket counting
    depth = 0
    in_string = False
    escape_next = False
    end = -1

    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
            continue
        if c == '\\' and in_string:
            escape_next = True
            continue
        if c == '"':
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
        # Try to repair truncated JSON by finding last complete object
        print(f"  Warning: truncated response ({len(text)} chars), attempting repair...", file=sys.stderr)
        # Find all complete {...} objects
        objects = []
        obj_depth = 0
        obj_start = -1
        in_str = False
        esc = False
        for i in range(start + 1, len(text)):
            c = text[i]
            if esc:
                esc = False
                continue
            if c == '\\' and in_str:
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == '{':
                if obj_depth == 0:
                    obj_start = i
                obj_depth += 1
            elif c == '}':
                obj_depth -= 1
                if obj_depth == 0 and obj_start != -1:
                    try:
                        obj_text = text[obj_start:i+1]
                        obj = json.loads(obj_text)
                        objects.append(obj)
                    except json.JSONDecodeError:
                        pass
                    obj_start = -1
        if objects:
            print(f"  Repaired: extracted {len(objects)} complete objects", file=sys.stderr)
            return objects
        raise ValueError(f"Could not parse JSON. Text length: {len(text)}")

    json_str = text[start:end+1]

    # Clean control characters
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', json_str)
    # Remove trailing commas
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

    return json.loads(json_str)


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
    m = "; ".join([i.get("title", "") for i in market[:4]])
    t = "; ".join([i.get("title", "") for i in thought[:3]])
    c = "; ".join([f"{i.get('competitor','')}: {i.get('title','')}" for i in competitors[:4]])

    prompt = f"""Write a 4-sentence executive summary for {week}.
Context: {context}
Market: {m}
Thought leadership: {t}
Competitors: {c}

Cover: 2 key themes, most urgent CMIplus action, most relevant competitor move.
Plain text only. No JSON. No markdown. No bullets."""

    try:
        response = call_gemini(prompt)
        text = extract_text(response)
        if text.startswith("[") or text.startswith("{"):
            return "Weekly scan complete. See sections below."
        return text
    except Exception as e:
        print(f"  Executive summary error: {e}", file=sys.stderr)
        return "Weekly scan complete. See sections below."


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
    executive_summary = generate_executive_summary(
        market, thought, competitors, week, sources)

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
