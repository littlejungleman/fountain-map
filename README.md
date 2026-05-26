[README.md](https://github.com/user-attachments/files/28259423/README.md)
# 💧 London Fountain Map

**Real-time map of kids' water play fountains & splash pads across London.**

Live status (open/closed/no data) sourced from community reports on [bablands.com/fountainwatch](https://bablands.com/fountainwatch/).

---

## 🚀 How to deploy (free, ~5 minutes)

### Step 1 — Create a GitHub account (if you don't have one)
Go to [github.com](https://github.com) and sign up. It's free.

### Step 2 — Create a new repository
1. Click the **+** button → **New repository**
2. Name it: `london-fountain-map`
3. Set it to **Public**
4. Click **Create repository**

### Step 3 — Upload the files

Either use the GitHub web interface to drag and drop the files, or use Git:

```bash
git clone https://github.com/YOUR_USERNAME/london-fountain-map
cd london-fountain-map

# Copy all the project files into this folder, then:
git add .
git commit -m "Initial commit"
git push
```

The folder structure should look like:
```
london-fountain-map/
├── .github/
│   └── workflows/
│       └── update-data.yml
├── docs/
│   ├── index.html
│   └── data.json
├── scripts/
│   ├── scrape.py
│   ├── requirements.txt
│   └── fountain_coords.json
└── README.md
```

### Step 4 — Enable GitHub Pages
1. Go to your repo → **Settings** → **Pages** (left sidebar)
2. Under **Source**, select **Deploy from a branch**
3. Branch: **main**, Folder: **/docs**
4. Click **Save**

Your site will be live at:
`https://YOUR_USERNAME.github.io/london-fountain-map/`

(Takes ~1 minute to deploy for the first time.)

### Step 5 — Trigger the first data update
1. Go to your repo → **Actions** tab
2. Click **Update fountain data** in the left sidebar
3. Click **Run workflow** → **Run workflow**

This runs the scraper and updates `docs/data.json` with fresh data from bablands.com.

After that, the scraper runs **automatically every 30 minutes**.

---

## 📁 File guide

| File | Purpose |
|------|---------|
| `docs/index.html` | The website — map + sidebar + search |
| `docs/data.json` | Auto-generated data file (fountain list + statuses) |
| `scripts/scrape.py` | Python scraper — run by GitHub Actions |
| `scripts/fountain_coords.json` | Hardcoded lat/lon for all ~95 fountains |
| `.github/workflows/update-data.yml` | Automation: runs scraper every 30 min |

---

## 🛠 Keeping fountain coordinates up to date

If bablands.com adds new fountains, you'll see them in the list sidebar with "No data" and they'll appear at coordinates `null` (invisible on map). To fix:

1. Check `docs/data.json` — fountains with `"lat": null` need coordinates
2. Look them up on [openstreetmap.org](https://www.openstreetmap.org)
3. Add them to `scripts/fountain_coords.json`

---

## 💡 How it works

```
Every 30 minutes:
  GitHub Actions runs scrape.py
    → Fetches bablands.com/fountainwatch/ (fountain list)
    → Fetches bablands.com/fountainwatch-live/ (status table)
    → Merges with fountain_coords.json (lat/lon)
    → Writes docs/data.json
    → Commits & pushes to GitHub

Website visitor loads index.html
  → Fetches data.json
  → Renders Leaflet map with colour-coded markers
  → Auto-refreshes every 10 minutes
```

---

## 🎨 Customisation

- **Change refresh rate**: Edit `cron` in `.github/workflows/update-data.yml` (minimum free tier: every 5 min)
- **Change map default view**: Edit `center` and `zoom` in `index.html`
- **Add a fountain**: Add coordinates to `scripts/fountain_coords.json`

---

## 📜 Credits

- Fountain data: [bablands.com](https://bablands.com) by Emmy Watts
- Map tiles: [OpenStreetMap](https://www.openstreetmap.org)
- Mapping library: [Leaflet.js](https://leafletjs.com)
- Hosting: [GitHub Pages](https://pages.github.com) (free)
- Automation: [GitHub Actions](https://github.com/features/actions) (free)
