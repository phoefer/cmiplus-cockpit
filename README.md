# CMIplus Intelligence Cockpit

Weekly intelligence briefing for RBI Cash Management — automatically scanning market news, thought leadership, competitor moves and flagship industry reports every Monday morning.

**Live:** [phoefer.github.io/cmiplus-cockpit](https://phoefer.github.io/cmiplus-cockpit/)

---

## What it does

Every Monday at 06:00 UTC, a GitHub Actions workflow runs `scan.py` which:

1. Fetches and analyses **10 market news sources** for the latest payments, treasury and regulatory developments
2. Fetches and analyses **7 thought leadership sources** (McKinsey, BCG, Oliver Wyman, EY, PwC, EACT, Deloitte)
3. Fetches and analyses **7 competitor sources** for moves by Deutsche Bank, UniCredit, Erste Group, BNP Paribas, HSBC, ING and Intesa Sanpaolo
4. Performs deep PDF analysis of **4 flagship annual reports** (EY, McKinsey, Journeys to Treasury, PwC)
5. Ranks all items by relevance score and generates an executive summary
6. Commits `briefing.json` and `flagship-analyses.json` to the repo
7. GitHub Pages serves the updated cockpit automatically

---

## Architecture

```
sources.json          <- Source configuration (edit here to add/remove/pause sources)
scan.py               <- Weekly scan script (runs on GitHub Actions)
briefing.json         <- Output: weekly intelligence items (auto-generated)
flagship-analyses.json <- Output: flagship report deep analyses (auto-generated)
index.html            <- Frontend (served via GitHub Pages)
reports/              <- PDF files for flagship report analysis
  ey-gl-four-trends-redefining-cash-management-08-2025.pdf
  the-2025-mckinsey-global-payments-report.pdf
  Journeys to Treasury 2025-26.pdf
.github/workflows/
  weekly-scan.yml     <- GitHub Actions schedule (Monday 06:00 UTC)
```

---

## Intelligence sections

### Market news
10 sources, ranked by relevance score. Each item includes:
- Full summary (5-7 sentences with context, timeline and regulatory detail)
- Key facts & data points (4 bullet points)
- "So what for RBI Cash Management" implication
- Direct article link
- Tags and urgency level (urgent / watch / fyi)

**Sources (priority 1):** Der Treasurer, The Global Treasurer, Strategic Treasurer, ECB/EBA, SWIFT News
**Sources (priority 2):** Finextra, The Paypers, Treasury Today
**Sources (priority 3):** Global Finance, Payments Dive

### Thought leadership
7 sources, ranked by relevance score. Strategic insights and research from:

**Priority 1:** McKinsey Financial Services, BCG, Oliver Wyman, EY, PwC
**Priority 2:** EACT, Deloitte

### Competitors
7 competitor banks monitored for product launches, CEE expansion, API/digital banking moves and treasury solutions:

**Priority 1:** Deutsche Bank, UniCredit, Erste Group, BNP Paribas
**Priority 2:** HSBC, ING
**Priority 3:** Intesa Sanpaolo

Competitor items are grouped by bank with filter buttons. Items inferred from strategic trends are marked as "inferred".

### Flagship reports
4 annual reports with deep PDF analysis:

| Report | Publisher | Focus |
|--------|-----------|-------|
| Four Trends Redefining Cash Management | EY | Treasury automation, data-driven services, digital assets |
| Global Payments Report | McKinsey | Payments revenues, instant payments, CEE trends |
| Journeys to Treasury 2025/26 | BNP Paribas / PwC / SAP / EACT | CEE treasury, VoP, ISO 20022, 7 corporate case studies |
| Global Treasury Survey | PwC | TMS adoption, API banking, AI in treasury, 350+ treasurers |

Each flagship deep dive includes:
- Executive summary
- 6-8 key statistics
- 5-6 theme analyses
- 3-4 action items with urgency and timeline
- Corporate case studies (where available)
- Competitive implications

---

## UI features

- **Sidebar navigation** with item counts per section
- **Collapsible cards** — click title to expand full detail. Default shows title + 2-line preview
- **Left border color-coding** — red (urgent), amber (watch), green (fyi)
- **Rank numbers** — items ranked #01 to #N by relevance score across all sources
- **Overview dashboard** — 3-column preview (market / thought / competitors) with executive summary and KPI counts
- **Deep dive modal** — full summary, key facts, RBI implication, article link. Closes on Escape key
- **Flagship deep dive** — themes, statistics, action items, case studies loaded from pre-generated JSON
- **Tag filters** — filter by topic tag within each section
- **Urgency filters** — All / Urgent / Watch / FYI
- **Competitor filter** — filter competitor tab by individual bank
- **Full-text search** — searches across all sections including summary, key points and tags

---

## Source configuration

All sources are configured in `sources.json`. No code changes needed to add, remove or reprioritise sources.

```json
{
  "market_news": [
    { "name": "Der Treasurer", "url": "...", "focus": "...", "priority": 1, "active": true }
  ],
  "thought_leadership": [...],
  "flagship_reports": [...],
  "competitors": [...],
  "scan_config": {
    "items_priority_1": 3,
    "items_priority_2": 2,
    "items_priority_3": 1
  }
}
```

**Priority system:**
- `priority: 1` — 3 items extracted, relevance score boosted by +2
- `priority: 2` — 2 items extracted, relevance score boosted by +1
- `priority: 3` — 1 item extracted, no boost
- `active: false` — source paused, skipped during scan

---

## Setup

### Requirements
- GitHub repository with Pages enabled (branch: `main`, folder: `root`)
- Google Cloud project with Generative Language API enabled
- Gemini API key stored as GitHub Secret `GEMINI_API_KEY`

### GitHub Actions secret
```
Settings -> Secrets and variables -> Actions -> New repository secret
Name: GEMINI_API_KEY
Value: your-gemini-api-key
```

### Manual trigger
```
Actions -> Weekly Intelligence Scan -> Run workflow
```

### Schedule
Runs automatically every Monday at 06:00 UTC via cron: `0 6 * * 1`

---

## Gemini models used

| Task | Model | Why |
|------|-------|-----|
| Weekly briefing (all sources) | `gemini-2.5-flash` | Fast, stable, no 503 errors |
| Flagship PDF analysis | `gemini-2.5-flash` | Handles large PDFs reliably |
| Executive summary | `gemini-2.5-flash` | Short generation, fast |

---

## Cost

Using Google Cloud credits. API costs are minimal — approximately 20-30 Gemini Flash calls per weekly scan (10 market + 7 thought + 7 competitor sources + 4 flagship analyses + 1 executive summary).

---

## Relevance scoring

Each item receives a relevance score (1-10) from Gemini based on how directly it impacts CMIplus / RBI Cash Management strategy. Priority boosts are applied on top:

```
final_score = gemini_score + priority_boost
priority_boost: P1=+2, P2=+1, P3=+0
urgency: score >= 8 -> urgent | score >= 5 -> watch | else -> fyi
```

Items are then sorted by final score descending and assigned rank numbers (`#01`, `#02`, ...).

---

## Context passed to Gemini

Every Gemini call includes this CMIplus context from `scan_config.context` in `sources.json`:

> CMIplus is RBI's (Raiffeisen Bank International) corporate cash management platform for large international corporates in CEE. Key topics: EBICS, H2H, ISO 20022, SEPA, instant payments, VoP, eBAM, Open Banking APIs, corporate treasury, multi-currency payments. Channels: EBICS v2.5+v3, H2H, SWIFT, Web, Mobile, Open API. Network banks across Austria, CZ, HR, RS, XK, AL, RO, SK, HU. Product Owner: Philipp Höfer.

---
