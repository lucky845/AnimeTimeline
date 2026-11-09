# AnimeTimeline

[中文版](README_zh.md)

A Python tool for crawling and organizing anime broadcast information, supporting retrieval of anime information by year and month, and saving in Markdown format. Includes automated update workflows for daily synchronization of the latest anime data.

## Features

- 📅 Dual-mode operation: supports both interactive command line and automated script modes
- ⚡ Smart updates: automatically synchronizes the latest anime data daily (8:00 AM Beijing time)
- 📈 Incremental updates: automatically merges new and old data with intelligent deduplication
- 🕰️ Time range: supports year ranges (e.g., 2010-2024) and month ranges (e.g., 4-7)
- 📦 Data export: split by year to avoid GitHub preview size limits
- 🔁 Failure retry: automatically handles network exceptions with 3 retry attempts
- 🤖 Automatic archiving: creates versioned Pull Requests through GitHub Actions
- 🛡️ Security control: configurable concurrent request limit (default: 3 concurrent requests)

## Data Source

> ⚠️ **Important change**: Bangumi.tv now requires login to browse `/anime/browser/airtime/*` pages, so HTML scraping no longer works in CI environments without authentication.

Since Nov 2026, this project uses [bangumi-data](https://github.com/bangumi-data/bangumi-data) as the data source:

- Source: `https://raw.githubusercontent.com/bangumi-data/bangumi-data/master/data/items/{year}/{month}.json`
- Publicly accessible, no login/cookies/proxy needed
- Includes air dates, Chinese/Japanese titles, episode counts, and Bangumi subject links

### Field differences vs old scraper

| Field | Old scraper | New (bangumi-data) |
| --- | --- | --- |
| Air date | ✅ | ✅ |
| Chinese title | ✅ | ✅ (`titleTranslate.zh-Hans`) |
| Japanese title | ✅ | ✅ |
| Episode count | ✅ | ✅ (`eps`) |
| Rating / votes | ✅ | ✅ (backfilled via `api.bgm.tv/v0/subjects/{id}`) |
| Cover image | ✅ | ✅ (backfilled via `api.bgm.tv`) |
| Weekly broadcast time | ❌ | ✅ (`broadcast` ISO-8601 repeat rule) |

Missing values are **never written over existing real data** — if the metadata API fails, the merge layer keeps the previous value instead of overwriting it with `-`.

## 📅 Calendar Subscription (new)

Beyond the Markdown tables, the project generates a real **weekly broadcast calendar**:

- Weekly schedule derived from bangumi-data's `broadcast` rule (`R/2026-10-07T15:00:00.000Z/P7D`), corrected by per-episode `airdate` from bgm.tv
- `data/calendar/{year}.ics` — subscribe it in any calendar app
- `docs/index.html` — static 7-day schedule page, deployed to GitHub Pages
- Live: **https://animetimeline.lucky845.top**
- Subscribe: **https://animetimeline.lucky845.top/calendar/2026.ics**

```bash
python scripts/build_calendar.py 2026 --weeks 16   # generate ICS + JSON
python scripts/check_calendar.py                   # validate structure / UID / RFC 5545 folding
python scripts/build_site.py                       # render docs/index.html
```

## ✅ Data quality guards

```bash
python scripts/check_data.py    # table shape, duplicate subjects, score format
python -m pytest -q             # unit tests
```

Both run in `pr-check.yml` and `update-anime.yml`; a failing guard blocks the auto-merge PR.

## Installation

1. Clone the project locally
   ```bash
   git clone https://github.com/yourusername/AnimeTimeline.git
   cd AnimeTimeline
   ```

2. Create and activate virtual environment (recommended)
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or
   .venv\Scripts\activate  # Windows
   ```

3. Install (either way)
   ```bash
   pip install -e "[dev]"   # development: editable install with pytest
   pip install animetimeline # once published: ready-to-use CLI
   ```

   The data directory defaults to the current working directory; override it with
   `--data-dir` or `ANIMETIMELINE_DATA_DIR`. No path is hard-coded inside the package.

## Usage

### Interactive Mode (Manual Operation)

```bash
python pull.py interactive
```

- Enter year range as prompted (e.g., 2010-2024)
- Enter month range (optional, only for single year)
- Data will be saved to [Bangumi_Anime.md](Bangumi_Anime.md)

### Automatic Mode (Script Call)

```bash
python pull.py auto --year 2024 --month 3
```

| Parameter | Description | Example |
| --- | --- | --- |
| --year | Target year (required) | 2024 |
| --month | Target month (optional) | 3 |
| --concurrent | Concurrency (default 3) | 5 |

### Automated Workflow

```yaml
# Scheduled tasks:
- Daily automatic updates for current month data
- Monthly supplementary updates for previous month on the 1st day
- Automatic generation of versioned Pull Requests

# Manual triggers:
- Support for manual updates through GitHub interface
```

## Data Storage

- 📂 Data file: [Bangumi_Anime.md](Bangumi_Anime.md) - Contains the complete anime timeline data
- 🗂️ Version control: Historical versions managed through Git branches
- 📊 Data structure:

```markdown
| Release Date | Cover | Chinese Title | Japanese Title | Episodes | Rating | Voters |
| --- | --- | --- | --- | --- | --- | --- |
| 2024-03 | ![](CoverURL) | [Title](DetailsPage) | Original Title | 12 | 8.9 | 1523 |
```

## Project Structure

```
AnimeTimeline/
├── .github/          # Automation configuration
│   └── workflows/
│       └── update-anime.yml  # Daily update workflow
├── pull.py           # Main program (supports dual mode)
├── requirements.txt  # Dependency configuration
├── Bangumi_Anime.md  # Generated data file
├── SECURITY.md       # Security policy
└── README.md         # This documentation
```

## Notes

### Network Requests

- Default concurrency is set to 3, to adjust set environment variable:
  ```bash
  export CONCURRENT_REQUESTS=5
  ```
- Avoid high-frequency requests, interval time ≥ 1 second

### Data Security

- Markdown files use UTF-8 encoding
- Automatic handling of illegal filename characters
- Regular commits of data changes recommended

### Exception Handling

- Network errors automatically retried 3 times
- Base year used automatically when date parsing fails
- Cover URL protocol headers automatically completed

## Contributing

### Code Contributions

1. Fork this repository
2. Create a feature branch
   ```bash
   git checkout -b feature/NewFeature
   ```
3. Commit code changes
   ```bash
   git commit -m 'feat: Add awesome feature'
   ```
4. Push branch
   ```bash
   git push origin feature/NewFeature
   ```
5. Create Pull Request

### Data Maintenance

- Participate in data validation through Pull Request reviews
- Report data anomalies in Issues
- Discuss data format improvements in Discussions

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details

## Security Policy

If you discover any security vulnerabilities, please review our security policy document for reporting procedures. We will respond promptly.