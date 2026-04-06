#!/usr/bin/env python3
"""
CMIplus Weekly Intelligence Cockpit — Weekly Scan Script v3
Robust JSON parsing with multiple fallback strategies.
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
    total = len(p1) * n1 + len(p2) * n2
    p1_str = ", ".join([s["name"] for s in p1])
    p2_str = ", ".join([s["name"] for s in p2]) if p2 else "none"

    return f"""You are a strategic intelligence analyst for RBI's CMIplus cash management platform.
Context: {context}

Search for MARKET NEWS from the last 7 days ({week}).
Priority sources ({n1} items each): {p1_str}
Secondary sources ({n2} item each): {p2_str}
Topics: ISO 20022, SEPA, instant payments, VoP, eBAM, EBICS, corporate treasury, CEE banking, PSD3, open banking

Available tags: {tags}

Respond with a JSON array of exactly {total} objects. Each object must have these exact fields:
- title: string
- summary: string (2-3 sentences)
- sowhat: string (1-2 sentences about CMIplus implications)
- relevance: one of "urgent", "watch", "fyi"
- tags: array of 1-3 strings from the available tags list
- source: string
- date: string
- url: string

Example of one item:
{{"title": "EBA publishes VoP reporting guidelines", "summary": "The EBA released...", "sowhat": "CMIplus needs to...", "relevance": "urgent", "tags": ["VoP", "Compliance"], "source": "EBA", "date": "Apr 2026", "url": "https://eba.europa.eu/..."}}

Return ONLY the JSON array, starting with [ and ending with ]. No other text."""


def build_thought_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = ", ".join(sources["tags"])
    active = [s for s in sources["thought_leadership"] if s["active"]]
    names = ", ".join([s["name"] for s in active])
    n = len(active) * 2

    return f"""You are a strategic intelligence analyst for RBI's CMIplus cash management platform.
Context: {context}

Search for strategic THOUGHT LEADERSHIP content from the last 12 months from: {names}
Look for: reports, whitepapers, research papers, annual outlooks, industry surveys, deep analyses.
Topics: cash management strategy, treasury transformation, open banking, API banking, payments innovation, CEE banking

Available tags: {tags}

Respond with a JSON array of exactly {n} objects. Each object must have these exact fields:
- title: string
- key_insight: string (2-3 sentences: the most important strategic insight)
- implications: string (2-3 sentences: what this means for CMIplus strategy or roadmap)
- relevance: one of "urgent", "watch", "fyi"
- tags: array of 1-3 strings from the available tags list
- source: string
- published: string (Month Year)
- url: string

Example of one item:
{{"title": "McKinsey: Transaction Banking in 2026", "key_insight": "Banks that invest in API-first...", "implications": "CMIplus should prioritize...", "relevance": "watch", "tags": ["OpenBanking", "AI"], "source": "McKinsey", "published": "Mar 2026", "url": "https://mckinsey.com/..."}}

Return ONLY the JSON array, starting with [ and ending with ]. No other text."""


def build_competitor_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    tags = ", ".join(sources["tags"])
    active = [s for s in sources["competitors"] if s["active"]]
    names = ", ".join([s["name"] for s in active])
    n = len(active) * 2

    return f"""You are a strategic intelligence analyst for RBI's CMIplus cash management platform.
Context: {context}

Search for recent news (last 4 weeks) from these competitors in cash management: {names}
Focus: cash management launches, API banking, corporate banking innovations, CEE expansion, VoP, instant payments.

Available tags: {tags}

Respond with a JSON array of exactly {n} objects covering as many different competitors as possible. Each object must have these exact fields:
- title: string
- competitor: string (exact bank name from the list above)
- summary: string (2-3 sentences)
- sowhat: string (1-2 sentences: threat, opportunity or benchmark for CMIplus)
- relevance: one of "urgent", "watch", "fyi"
- tags: array of 1-3 strings from the available tags list
- source: string
- date: string
- url: string

Example of one item:
{{"title": "Deutsche Bank launches CB Connect 2.0", "competitor": "Deutsche Bank", "summary": "Deutsche Bank expanded...", "sowhat": "This directly challenges CMIplus's...", "relevance": "urgent", "tags": ["OpenBanking", "CEE"], "source": "Deutsche Bank", "date": "Apr 2026", "url": "https://..."}}

Return ONLY the JSON array, starting with [ and ending with ]. No other text."""


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


def parse_json_robust(text):
    """Try multiple strategies to extract valid JSON from model output."""
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    if "```" in text:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    # Strategy 3: find JSON array
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Strategy 4: find JSON object with items array
    match = re.search(r'\{[\s\S]*"items"[\s\S]*\}', text)
    if match:
        try:
            obj = json.loads(match.group(0))
            return obj.get("items", obj)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response (length {len(text)}): {text[:300]}")


def safe_call(prompt, label):
    print(f"  Calling Gemini for {label}...")
    try:
        response = call_gemini(prompt)
        text = extract_text(response)
        result = parse_json_robust(text)
        # Result should be a list directly
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            items = result.get("items", [])
        else:
            items = []
        print(f"  OK {label}: {len(items)} items")
        return items
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        print(f"  FAIL {label} API {e.code}: {body}", file=sys.stderr)
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

The summary must name 2-3 key themes, state the most urgent action for CMIplus, and highlight the most relevant competitor move.
Return ONLY plain text. No JSON. No markdown. No bullet points."""

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
