# 💧 London Fountain Map

**Real-time map of kids' water play fountains & splash pads across London.**

Live status (open/closed/no data) sourced from community reports on [bablands.com/fountainwatch](https://bablands.com/fountainwatch/).

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

## 📜 Credits
- Fountain data: [bablands.com](https://bablands.com) by Emmy Watts
- Map: [Leaflet.js](https://leafletjs.com) + [OpenStreetMap](https://www.openstreetmap.org)
- Hosting & automation: [GitHub Pages](https://pages.github.com) + [GitHub Actions](https://github.com/features/actions) (both free)
