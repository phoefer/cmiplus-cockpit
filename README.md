# CMIplus Intelligence Cockpit

Weekly strategic intelligence briefing for CMIplus / Cash Management at RBI.
Auto-scans market news, thought leadership and competitor activity every Monday at 07:00 CET.

---

## Setup (15 minutes)

### 1. Create a GitHub repository

1. Go to [github.com](https://github.com) and sign in
2. Click **New repository**
3. Name it `cmiplus-cockpit`
4. Set to **Private** (recommended) or Public
5. Click **Create repository**

### 2. Upload the files

Upload all files from this folder to your repository:
- `index.html`
- `briefing.json`
- `sources.json`
- `scan.py`
- `.github/workflows/weekly-scan.yml`

You can drag-and-drop them via the GitHub web UI, or use git:

```bash
git init
git add .
git commit -m "Initial setup"
git remote add origin https://github.com/YOUR_USERNAME/cmiplus-cockpit.git
git push -u origin main
```

### 3. Add your Anthropic API Key

1. In your repository, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your Anthropic API key (starts with `sk-ant-...`)
5. Click **Add secret**

> Get your API key at [console.anthropic.com](https://console.anthropic.com)

### 4. Enable GitHub Pages

1. Go to **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / `/ (root)`
4. Click **Save**
5. Your cockpit will be live at `https://YOUR_USERNAME.github.io/cmiplus-cockpit`

### 5. Run your first scan

1. Go to **Actions → Weekly Intelligence Scan**
2. Click **Run workflow**
3. Wait ~2-3 minutes
4. Refresh your GitHub Pages URL

---

## Weekly automation

The scan runs automatically every **Monday at 07:00 CET** (06:00 UTC).

The GitHub Action:
1. Calls Claude API with web search
2. Scans all active sources in `sources.json`
3. Writes results to `briefing.json`
4. Commits and pushes — GitHub Pages updates automatically

---

## Customising sources

Edit `sources.json` directly on GitHub. No code changes needed.

**Add a source:**
```json
{ "name": "New Source", "url": "https://...", "focus": "what to look for", "active": true }
```

**Pause a source temporarily:**
```json
{ "name": "Source Name", ..., "active": false }
```

**Change scan depth** — edit `items_per_section` in `scan_config`:
```json
"items_per_section": 6
```

---

## Files

| File | Purpose |
|------|---------|
| `index.html` | The cockpit UI — hosted on GitHub Pages |
| `briefing.json` | Latest briefing output — updated by the scan |
| `sources.json` | Source configuration — edit to add/change sources |
| `scan.py` | The scan script — called by GitHub Actions |
| `.github/workflows/weekly-scan.yml` | Automation — runs every Monday 07:00 CET |
