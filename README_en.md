# AnimeTimeline

A Python tool for crawling and organizing anime broadcast information, supporting retrieval of anime information by year and month, and saving in Markdown format.

## Features

- Support crawling anime information by year or month
- Automatically fetch anime titles, Japanese titles, episode count, broadcast dates, ratings, and more
- Support incremental updates to avoid duplicate data
- Organize by date and generate clear Markdown documents
- Automatic handling of network exceptions with retry support
- Support batch crawling of data for specified year ranges

## Installation

1. Clone the project locally
```bash
git clone https://github.com/yourusername/AnimeTimeline.git
cd AnimeTimeline
```

2. Create and activate virtual environment (optional)
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

## Usage

1. Run the crawler program
```bash
python pull.py
```

2. Enter the year to crawl as prompted
   - Support single year, e.g.: 2024
   - Support year range, e.g.: 2000-2024

3. Enter the month to crawl (optional)
   - Enter a number 1-12 to crawl a specific month
   - Press Enter directly to crawl the entire year

## Data Storage

- Data is stored in corresponding folders by year and month
- Anime information for each date is stored in separate Markdown files
- Markdown files contain the following information:
  - Anime title (Chinese)
  - Japanese title
  - Episode count
  - Broadcast date
  - Rating
  - Number of ratings
  - Play link
  - Cover image link

## Project Structure

```
AnimeTimeline/
├── pull.py          # Main program file
├── requirements.txt  # Project dependencies
├── README.md        # Project documentation
├── SECURITY.md      # Security policy
└── .github/         # GitHub configuration
    └── workflows/   # GitHub Actions workflows
```

## Notes

1. Please control crawling frequency reasonably to avoid pressure on the target website
2. It is recommended to run the project in a virtual environment to avoid dependency conflicts
3. In case of network issues, the program will automatically retry
4. Data updates will automatically deduplicate to avoid repeated content

## Contributing

1. Fork this repository
2. Create a new feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Create a Pull Request

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details

## Security

If you discover any security vulnerabilities, please review our [Security Policy](SECURITY.md) for reporting procedures.