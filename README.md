# 💧 London Fountain Map

**Real-time map of kids' water play fountains & splash pads across London.**

Live status (open/closed/no data) sourced from community reports on [bablands.com/fountainwatch](https://bablands.com/fountainwatch/).

---

## 🚀 Deploy 

### Step 1 — Create a GitHub account
[github.com](https://github.com) → Sign up (free)

### Step 2 — Create a new repository
- Click **+** → **New repository**
- Name: `london-fountain-map`
- Visibility: **Public**
- Click **Create repository**

### Step 3 — Upload the files
Drag and drop all project files into the repo via the GitHub web UI, preserving folder structure:
```
london-fountain-map/
├── .github/workflows/update-data.yml
├── docs/
│   ├── index.html
│   └── data.json
├── scripts/
│   ├── scrape.py
│   ├── geocode_google.py
│   ├── requirements.txt
│   └── fountain_coords.json
└── README.md
```

### Step 4 — Enable GitHub Pages
**Settings → Pages → Source: main branch, /docs folder → Save**

Your site will be live at `https://YOUR_USERNAME.github.io/london-fountain-map/`

### Step 5 — Run the first data update
**Actions tab → "Update fountain data" → Run workflow**

The scraper runs automatically every 30 minutes from then on.

---

## 📍 Improving coordinates (optional but recommended)

The included `fountain_coords.json` has manually-researched coordinates. For maximum precision, run the Google Geocoding script once:

### Get a free Google Geocoding API key
1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create a project → Enable **Geocoding API**
3. Create an API key (free tier covers 40,000 geocodes/month)
4. Restrict the key to "Geocoding API" only for safety

### Run the geocoder
```bash
pip install requests
export GOOGLE_GEOCODING_API_KEY="your_key_here"
python scripts/geocode_google.py
```

This updates `fountain_coords.json` with precise coordinates and prints anything that moved >50m from the manual estimate. Commit the result.

---

## 🛠 How it works

```
Every 30 minutes (GitHub Actions):
  scrape.py runs
    → GET bablands.com/fountainwatch/ (fountain name list)
    → GET bablands.com/fountainwatch-live/ (live status table)
    → Extracts wpDataTables table_id + nonce from page JS
    → POSTs to wp-admin/admin-ajax.php, paginating through ALL rows
      (75+ rows across 8 pages — gets them all)
    → Picks newest status per fountain by timestamp
    → Normalises curly apostrophes to straight (website uses King's,
      coords file uses King's — must match)
    → Merges with fountain_coords.json
    → Writes docs/data.json
    → Commits & pushes to GitHub

Visitor loads index.html
  → Fetches data.json
  → Leaflet map: green=open, red=closed, grey=no data
  → Auto-refreshes every 10 minutes
```

---

## 🗺 Adding a new fountain

If bablands.com adds a fountain not yet in `fountain_coords.json`:
1. Check `data.json` — it will appear with `"lat": null` (invisible on map)
2. Add an entry to `fountain_coords.json`:
```json
{"name": "New Fountain Name, Area", "lat": 51.5123, "lon": -0.1234}
```
3. Commit and push — next scrape run will pick it up

---

## 📜 Credits
- Fountain data: [bablands.com](https://bablands.com) by Emmy Watts
- Map: [Leaflet.js](https://leafletjs.com) + [OpenStreetMap](https://www.openstreetmap.org)
- Hosting & automation: [GitHub Pages](https://pages.github.com) + [GitHub Actions](https://github.com/features/actions) (both free)
