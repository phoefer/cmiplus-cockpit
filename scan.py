#!/usr/bin/env python3
"""
CMIplus Weekly Intelligence Cockpit — Weekly Scan Script
Runs via GitHub Actions every Monday at 07:00 CET.
Uses Google Gemini API (free tier) with Google Search grounding.
Writes briefing.json which GitHub Pages serves to the cockpit UI.
"""

import json
import os
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.error

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.0-flash"
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


def build_prompt(sources):
    cfg = sources["scan_config"]
    context = cfg["context"]
    n = cfg["items_per_section"]

    market_focus     = "; ".join([f"{s['name']} ({s['focus']})" for s in sources["market_news"]        if s["active"]])
    thought_focus    = "; ".join([f"{s['name']} ({s['focus']})" for s in sources["thought_leadership"]  if s["active"]])
    competitor_focus = "; ".join([f"{s['name']} ({s['focus']})" for s in sources["competitors"]         if s["active"]])

    week    = get_week_label()
    now_iso = datetime.now(timezone.utc).isoformat()

    return f"""You are a strategic intelligence analyst for Philipp Hoefer, Group Product Owner Cash Management at RBI (Raiffeisen Bank International).
Context: {context}

Use Google Search to find the most relevant news and developments for {week}.

Search across these three categories:

MARKET NEWS: {market_focus}
Focus: ISO 20022, SEPA, instant payments, VoP, eBAM, EBICS, H2H, corporate treasury, CEE banking regulation, PSD3

THOUGHT LEADERSHIP: {thought_focus}
Focus: cash management strategy, treasury transformation, open banking, API banking, payments innovation

COMPETITORS: {competitor_focus}
Focus: cash management launches, corporate banking innovations, CEE expansion, API banking, transaction banking

Return ONLY this JSON structure, raw, no markdown fences, no explanation:

{{
  "generated_at": "{now_iso}",
  "week_label": "{week}",
  "executive_summary": "3-4 sentence strategic overview of the most important themes this week for CMIplus",
  "market": [
    {{
      "title": "Short specific headline",
      "summary": "2-3 sentence factual summary",
      "sowhat": "1-2 sentences: concrete implication for CMIplus product strategy or roadmap",
      "relevance": "urgent",
      "source": "Source name",
      "date": "Date",
      "url": "https://..."
    }}
  ],
  "thought": [
    {{
      "title": "Short specific headline",
      "summary": "2-3 sentence factual summary",
      "sowhat": "1-2 sentences: concrete implication for CMIplus",
      "relevance": "watch",
      "source": "Source name",
      "date": "Date",
      "url": "https://..."
    }}
  ],
  "competitors": [
    {{
      "title": "Short specific headline",
      "summary": "2-3 sentence factual summary",
      "sowhat": "1-2 sentences: concrete implication for CMIplus",
      "relevance": "fyi",
      "source": "Source name",
      "date": "Date",
      "url": "https://..."
    }}
  ]
}}

Return exactly {n} items per section.
Relevance: urgent = action needed now, watch = monitor next 1-3 months, fyi = background awareness.
RAW JSON ONLY. No markdown. No code fences. No text before or after the JSON."""


def call_gemini(prompt):
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}
    }
    url  = f"{API_URL}?key={GEMINI_API_KEY}"
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_json(response):
    try:
        text = response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected response structure: {e}\n{json.dumps(response)[:500]}")
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end   = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text  = "\n".join(lines[1:end]).strip()
    return json.loads(text)


def main():
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    print("Loading sources...")
    sources = load_sources()

    print("Building prompt...")
    prompt = build_prompt(sources)

    print(f"Calling Gemini ({MODEL}) with Google Search grounding...")
    try:
        response = call_gemini(prompt)
    except urllib.error.HTTPError as e:
        print(f"API Error {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)

    print("Parsing response...")
    try:
        briefing = extract_json(response)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Parse error: {e}", file=sys.stderr)
        with open("briefing_raw_error.json", "w") as f:
            json.dump(response, f, indent=2)
        sys.exit(1)

    with open("briefing.json", "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2, ensure_ascii=False)

    print(f"Done: {briefing.get('week_label','?')} | "
          f"market={len(briefing.get('market',[]))} "
          f"thought={len(briefing.get('thought',[]))} "
          f"competitors={len(briefing.get('competitors',[]))}")


if __name__ == "__main__":
    main()
