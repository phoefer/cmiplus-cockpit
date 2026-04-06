#!/usr/bin/env python3
"""
CMIplus Weekly Intelligence Cockpit — Weekly Scan Script
Runs via GitHub Actions every Monday at 07:00 CET.
Calls Claude API with web_search tool, writes briefing.json.
"""

import json
import os
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.error

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"


def load_sources():
    with open("sources.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_week_label():
    now = datetime.now(timezone.utc)
    day = now.weekday()
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = monday.replace(day=now.day - day)
    sunday = monday.replace(day=monday.day + 6)
    fmt = lambda d: d.strftime("%-d %b")
    return f"Week of {fmt(monday)} – {fmt(sunday)} {now.year}"


def build_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    n = cfg["items_per_section"]

    market_sources = [s["name"] for s in sources["market_news"] if s["active"]]
    thought_sources = [s["name"] for s in sources["thought_leadership"] if s["active"]]
    competitor_sources = [s["name"] for s in sources["competitors"] if s["active"]]

    market_focus = "; ".join([f"{s['name']} ({s['focus']})" for s in sources["market_news"] if s["active"]])
    thought_focus = "; ".join([f"{s['name']} ({s['focus']})" for s in sources["thought_leadership"] if s["active"]])
    competitor_focus = "; ".join([f"{s['name']} ({s['focus']})" for s in sources["competitors"] if s["active"]])

    week = get_week_label()

    return f"""You are a strategic intelligence analyst for Philipp Höfer, Group Product Owner Cash Management at RBI (Raiffeisen Bank International). 
Context: {context}

Scan for the most relevant news and developments for {week}.

Search across these three categories:

MARKET NEWS — search: {market_focus}
Focus topics: ISO 20022, SEPA, instant payments, VoP, eBAM, EBICS, H2H, corporate treasury, CEE banking regulation, PSD3

THOUGHT LEADERSHIP — search: {thought_focus}
Focus topics: cash management strategy, treasury transformation, open banking, API banking, payments innovation, digital banking

COMPETITORS — search: {competitor_focus}
Focus topics: cash management product launches, corporate banking innovations, CEE expansion, API/digital banking, transaction banking announcements

Return ONLY a valid JSON object with this exact structure (no markdown, no preamble, no trailing text):

{{
  "generated_at": "{datetime.now(timezone.utc).isoformat()}",
  "week_label": "{week}",
  "executive_summary": "3-4 sentence strategic overview of the most important themes this week for CMIplus product strategy",
  "market": [
    {{
      "title": "Short, specific headline",
      "summary": "2-3 sentence factual summary of the news",
      "sowhat": "1-2 sentences: concrete implication for CMIplus product strategy, roadmap or customer communication",
      "relevance": "urgent",
      "source": "Source name",
      "date": "Date or approximate",
      "url": "https://..."
    }}
  ],
  "thought": [
    {{
      "title": "Short, specific headline",
      "summary": "2-3 sentence factual summary",
      "sowhat": "1-2 sentences: concrete implication for CMIplus",
      "relevance": "watch",
      "source": "Source name",
      "date": "Date or approximate",
      "url": "https://..."
    }}
  ],
  "competitors": [
    {{
      "title": "Short, specific headline",
      "summary": "2-3 sentence factual summary",
      "sowhat": "1-2 sentences: concrete implication for CMIplus",
      "relevance": "fyi",
      "source": "Source name",
      "date": "Date or approximate",
      "url": "https://..."
    }}
  ]
}}

Return {n} items per section. Relevance: urgent = immediate action needed, watch = monitor in next 1-3 months, fyi = background awareness.
Return raw JSON only — no markdown code fences, no explanation."""


def call_claude(prompt):
    payload = {
        "model": MODEL,
        "max_tokens": 4000,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "system": "You are a strategic intelligence analyst. Always return valid JSON only. No markdown, no preamble.",
        "messages": [{"role": "user", "content": prompt}]
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "web-search-2025-03-05"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_json_from_response(response):
    content = response.get("content", [])
    text = ""
    for block in content:
        if block.get("type") == "text":
            text += block.get("text", "")

    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    return json.loads(text.strip())


def main():
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    print("Loading sources...")
    sources = load_sources()

    print("Building prompt...")
    prompt = build_prompt(sources)

    print("Calling Claude API with web search...")
    try:
        response = call_claude(prompt)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"API Error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)

    print("Parsing response...")
    try:
        briefing = extract_json_from_response(response)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        # Write raw response for debugging
        with open("briefing_raw_error.txt", "w") as f:
            json.dump(response, f, indent=2)
        sys.exit(1)

    # Write output
    output_path = "briefing.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)

    print(f"✓ Briefing written to {output_path}")
    print(f"  Week: {briefing.get('week_label', 'unknown')}")
    print(f"  Market items: {len(briefing.get('market', []))}")
    print(f"  Thought items: {len(briefing.get('thought', []))}")
    print(f"  Competitor items: {len(briefing.get('competitors', []))}")


if __name__ == "__main__":
    main()
