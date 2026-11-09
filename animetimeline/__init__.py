"""AnimeTimeline：从 bangumi-data + bgm.tv 生成番剧播出日历与 Markdown 年度表。"""
from .scraper import BangumiScraper, resolve_data_dir, run

__version__ = "0.1.0"
__all__ = ["BangumiScraper", "resolve_data_dir", "run", "__version__"]
