# ph-heatmap

Daily snapshot of the top-50 Most Viewed Pornstars on Pornhub, visualized as a heatmap of day-over-day percentage growth in cumulative `Video Views`.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run once

```bash
./venv/bin/python run.py
```

Creates / updates `data.db` (SQLite) and `heatmap.html` (open in a browser).

## Schedule via cron

Add to `crontab -e`:

```
0 4 * * * cd /absolute/path/to/ph-heatmap && ./venv/bin/python run.py >> run.log 2>&1
```

This runs daily at 04:00 local time. The first run produces a heatmap with no colored cells (no prior day to diff against). The second run is the first useful one.

## Tests

```bash
./venv/bin/pytest -v
```

## Troubleshooting

- **403 / blank top list:** Cloudflare is rejecting the TLS fingerprint. Try a different `impersonate` value in `scraper.py` (`chrome116`, `chrome119`, `chrome120`).
- **Profile parser raises `Could not find 'Video Views'`:** the site changed its layout. Fetch one profile manually, inspect, and update `_extract_video_views` in `scraper.py`.
- **Empty heatmap after several days:** check `run.log` for `WARN: skipping ...` lines — those actresses are being filtered out before insert.

## Layout

| File | Responsibility |
|------|----------------|
| `run.py` | Orchestration |
| `scraper.py` | HTTP + parsing |
| `db.py` | SQLite read/write |
| `heatmap.py` | Delta math + Plotly render |
