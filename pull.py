#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import os
import re
import time
import glob
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BANGUMI_DATA_URL = (
    "https://raw.githubusercontent.com/bangumi-data/bangumi-data/master/data/items/{year}/{month:02d}.json"
)
SUBJECT_API = "https://api.bgm.tv/v0/subjects/{subject_id}"
USER_AGENT = "lucky845/AnimeTimeline (https://github.com/lucky845/AnimeTimeline)"
JST = timezone(timedelta(hours=9))

DEFAULT_CONCURRENT = 3
MAX_CONCURRENT = int(os.environ.get("CONCURRENT_REQUESTS", DEFAULT_CONCURRENT))
CACHE_FILE = os.path.join("data", ".subject_cache.json")


class BangumiScraper:
    def __init__(self):
        self.current_year = time.localtime().tm_year
        self.current_month = time.localtime().tm_mon
        self.semaphore = None
        self.cache: Dict[str, Dict] = {}
        self.cache_dirty = False

    async def __aenter__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._load_cache()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._save_cache()

    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logging.info(f"📦 已加载 subject 缓存: {len(self.cache)} 条")
            except Exception as e:
                logging.info(f"缓存读取失败，忽略: {e}")
                self.cache = {}

    def _save_cache(self):
        if not self.cache_dirty:
            return
        os.makedirs("data", exist_ok=True)
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, sort_keys=True)
            logging.info(f"💾 已保存 subject 缓存: {len(self.cache)} 条")
        except Exception as e:
            logging.warning(f"缓存保存失败: {e}")

    @staticmethod
    def _local_date(begin: str) -> Optional[datetime]:
        if not begin:
            return None
        try:
            dt = datetime.fromisoformat(begin.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(JST)
        except ValueError:
            return None

    async def _fetch_subject(self, session: aiohttp.ClientSession, subject_id: str) -> Optional[Dict]:
        if subject_id in self.cache:
            return self.cache[subject_id]
        async with self.semaphore:
            for attempt in range(3):
                try:
                    async with session.get(
                        SUBJECT_API.format(subject_id=subject_id),
                        headers={"User-Agent": USER_AGENT},
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as resp:
                        if resp.status == 404:
                            self.cache[subject_id] = {}
                            self.cache_dirty = True
                            return {}
                        if resp.status != 200:
                            raise aiohttp.ClientResponseError(
                                resp.request_info, resp.history, status=resp.status
                            )
                        data = await resp.json()
                        info = {
                            "eps": data.get("eps") or data.get("total_episodes") or 0,
                            "score": (data.get("rating") or {}).get("score") or None,
                            "votes": (data.get("rating") or {}).get("total") or 0,
                            "cover": ((data.get("images") or {}).get("large") or "").replace(
                                "http://", "https://"
                            ),
                            "title_cn": data.get("name_cn") or "",
                            "title_jp": data.get("name") or "",
                        }
                        self.cache[subject_id] = info
                        self.cache_dirty = True
                        return info
                except Exception as e:
                    if attempt == 2:
                        logging.debug(f"subject {subject_id} 获取失败: {e}")
                        return None
                    await asyncio.sleep(1.5 * (attempt + 1))
        return None

    async def fetch_month(self, session: aiohttp.ClientSession, year: int, month: int) -> List[Dict]:
        url = BANGUMI_DATA_URL.format(year=year, month=month)
        logging.info(f"正在获取: {url}")
        try:
            async with session.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 404:
                    logging.info(f"跳过 {year}-{month:02d}: 数据不存在（未发布）")
                    return []
                resp.raise_for_status()
                raw = await resp.json(content_type=None)
        except Exception as e:
            logging.info(f"跳过 {year}-{month:02d}: {e}")
            return []

        entries = []
        for item in raw:
            begin = item.get("begin", "")
            dt = self._local_date(begin)
            if dt is None:
                continue

            subject_id = ""
            for site in item.get("sites", []):
                if site.get("site") == "bangumi":
                    subject_id = str(site.get("id", ""))
                    break

            titles = item.get("titleTranslate", {}) or {}
            zh_candidates = titles.get("zh-Hans") or titles.get("zh-Hant") or []
            title_cn = zh_candidates[0] if zh_candidates else ""
            title_jp = item.get("title", "") or ""
            # 没有中文标题时，用日文标题占位，保持列非空
            display_title = title_cn or title_jp

            entries.append(
                {
                    "year": dt.year,
                    "month": dt.month,
                    "day": dt.day,
                    "cover": "",
                    "title": display_title,
                    "url": f"https://bangumi.tv/subject/{subject_id}" if subject_id else "",
                    "jp_title": title_jp if title_cn and title_jp != title_cn else "",
                    "episodes": "",
                    "score": "",
                    "votes": "",
                    "_subject_id": subject_id,
                }
            )

        # 补全条目元数据（并发受 semaphore 限制）
        tasks = [self._fetch_subject(session, e["_subject_id"]) for e in entries if e["_subject_id"]]
        await asyncio.gather(*tasks)

        for e in entries:
            sid = e.pop("_subject_id", "")
            info = self.cache.get(sid) if sid else None
            if not info:
                e["episodes"] = "未知"
                e["score"] = "-"
                e["votes"] = "0"
                continue
            if info.get("eps"):
                e["episodes"] = str(info["eps"])
            else:
                e["episodes"] = "未知"
            e["score"] = str(info["score"]) if info.get("score") else "-"
            e["votes"] = str(info.get("votes") or 0)
            e["cover"] = info.get("cover") or ""
            # 优先使用 API 的规范标题
            if info.get("title_cn"):
                e["title"] = info["title_cn"]
            if info.get("title_jp") and info["title_jp"] != e["title"]:
                e["jp_title"] = info["title_jp"]

        logging.info(f"✅ {year}-{month:02d}: {len(entries)} 条")
        return entries

    async def scrape_time_range(
        self, start_year: int, end_year: int, start_month: int = None, end_month: int = None
    ) -> List[Dict]:
        all_data: List[Dict] = []
        async with aiohttp.ClientSession(trust_env=True) as session:
            for year in range(start_year, end_year + 1):
                if start_year != end_year:
                    months = range(1, 13)
                elif start_month and end_month:
                    months = range(start_month, end_month + 1)
                elif start_month:
                    months = [start_month]
                else:
                    months = range(1, 13)

                for month in months:
                    if year == self.current_year and month > self.current_month + 1:
                        logging.info(f"跳过未来月份: {year}-{month:02d}")
                        continue
                    all_data.extend(await self.fetch_month(session, year, month))
        return all_data

    def generate_markdown(self, new_data: List[Dict], filename: str = "Bangumi_Anime.md"):
        existing_data = self.parse_existing_markdown(filename) if os.path.exists(filename) else []

        new_items_count = 0
        new_years_data = defaultdict(int)
        merged_data = []
        seen = set()

        def ident(item):
            return (
                item.get("year"),
                item.get("title"),
                item.get("episodes"),
                (item.get("url") or "").split("/")[-1],
            )

        for item in existing_data:
            key = ident(item)
            if key not in seen:
                seen.add(key)
                merged_data.append(item)

        for item in new_data:
            key = ident(item)
            if key not in seen:
                seen.add(key)
                new_items_count += 1
                new_years_data[item.get("year")] += 1
                merged_data.append(item)

        year_dict = defaultdict(list)
        for item in merged_data:
            year = item.get("year", "未知")
            if year in (0, "未知"):
                continue
            year_dict[year].append(item)

        os.makedirs("data", exist_ok=True)
        sorted_years = sorted(
            year_dict.keys(), key=lambda y: int(y) if str(y).isdigit() else 0, reverse=True
        )

        for year in sorted_years:
            md_content = "# Bangumi番剧数据报告\n\n"
            md_content += f"## {year}年\n\n"
            md_content += "| 放送日期 | 封面 | 中文标题 | 日文标题 | 话数 | 评分 | 评分人数 |\n"
            md_content += "| --- | --- | --- | --- | --- | --- | --- |\n"

            sorted_items = sorted(
                year_dict[year],
                key=lambda x: (
                    -int(x.get("year") or 0),
                    -int(x.get("month") or 0),
                    -int(x.get("day") or 0),
                ),
            )

            for item in sorted_items:
                date_parts = []
                if item.get("year"):
                    date_parts.append(f"{item['year']}")
                    if item.get("month") and int(item["month"]) > 0:
                        date_parts.append(f"{int(item['month']):02d}")
                        if item.get("day") and int(item["day"]) > 0:
                            date_parts.append(f"{int(item['day']):02d}")
                date_str = "-".join(date_parts) if date_parts else "未知"

                cover = f"![]({item['cover']})" if item.get("cover") else ""
                ch_title = (item.get("title") or "未知标题").strip()
                title_link = f"[{ch_title}]({item.get('url', '')})" if item.get("url") else ch_title
                jp_title = (item.get("jp_title") or "").strip()
                votes = re.sub(r"\D", "", str(item.get("votes", "0"))) or "0"
                score = item.get("score", "-") or "-"
                episodes = item.get("episodes", "未知") or "未知"

                md_content += (
                    f"| {date_str} | {cover} | {title_link} | {jp_title} | "
                    f"{episodes} | {score} | {votes} |\n"
                )
            md_content += "\n"

            with open(os.path.join("data", f"{year}.md"), "w", encoding="utf-8") as f:
                f.write(md_content)

        index = "# Bangumi番剧数据报告\n\n"
        index += "> 由于原始文件过大，GitHub 无法正常预览，现已按年份拆分存档。\n\n"
        index += "## 年份索引\n\n"
        for year in sorted_years:
            index += f"- [{year}年](data/{year}.md)\n"
        index += "\n## 说明\n\n"
        index += "- 数据来源：[bangumi-data](https://github.com/bangumi-data/bangumi-data) + [Bangumi API](https://api.bgm.tv)\n"
        index += "- Bangumi.tv 番剧浏览页现已要求登录，故改用上述公开数据源\n"
        index += "- 每日自动更新（GitHub Actions）\n"

        index_path = os.path.abspath(filename)
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index)

        logging.info("✅ 数据合并完成:")
        logging.info(f"   - 现有数据: {len(existing_data)} 条")
        logging.info(f"   - 本次新增: {new_items_count} 条")
        if new_items_count > 0:
            for year, count in sorted(new_years_data.items(), reverse=True):
                logging.info(f"     * {year}年: {count} 条")
        logging.info(f"📝 已按年份写入 data/ 并更新索引: {index_path}")

    def parse_existing_markdown(self, filename: str) -> List[Dict]:
        existing_data = []
        parsed_count = 0

        data_files = sorted(glob.glob(os.path.join("data", "*.md")))
        if not data_files:
            if not os.path.exists(filename):
                return []
            data_files = [filename]

        for filepath in data_files:
            current_year = None
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("## "):
                            year_match = re.match(r"## (\d+)年", line)
                            if year_match:
                                current_year = int(year_match.group(1))
                                continue
                        elif line.startswith("|") and not line.startswith(("| ---", "| 放送日期")):
                            parts = [p.strip() for p in line.split("|")[1:-1]]
                            if len(parts) < 6:
                                continue
                            try:
                                cover = ""
                                if "![]" in parts[1]:
                                    cover_match = re.search(r"!\[\]\((.*?)\)", parts[1])
                                    if cover_match:
                                        cover = cover_match.group(1)

                                title = parts[2]
                                url = ""
                                if "[" in parts[2] and "](" in parts[2]:
                                    title_match = re.search(r"\[(.*?)\]", parts[2])
                                    url_match = re.search(r"\]\((.*?)\)", parts[2])
                                    if title_match:
                                        title = title_match.group(1)
                                    if url_match:
                                        url = url_match.group(1)

                                item = {
                                    "year": current_year,
                                    "month": 0,
                                    "day": 0,
                                    "cover": cover,
                                    "title": title,
                                    "url": url,
                                    "jp_title": parts[3],
                                    "episodes": parts[4],
                                    "score": parts[5],
                                    "votes": parts[6] if len(parts) > 6 else "0",
                                }

                                date_parts = parts[0].split("-")
                                try:
                                    if len(date_parts) >= 1 and date_parts[0].isdigit():
                                        item["year"] = int(date_parts[0])
                                    if len(date_parts) >= 2 and date_parts[1].isdigit():
                                        item["month"] = int(date_parts[1])
                                    if len(date_parts) >= 3:
                                        if date_parts[2].isdigit():
                                            item["day"] = int(date_parts[2])
                                        elif "(" in date_parts[2]:
                                            day_part = date_parts[2].split("(")[0]
                                            if day_part.isdigit():
                                                item["day"] = int(day_part)
                                except ValueError:
                                    pass

                                existing_data.append(item)
                                parsed_count += 1
                            except Exception as e:
                                logging.debug(f"解析行出错: {line[:50]}... | {e}")
                                continue
            except Exception as e:
                logging.error(f"❌ 解析文件出错 {filepath}: {e}")
                continue

        logging.info(f"✅ 解析旧数据完成 | 文件数: {len(data_files)} | 条目: {parsed_count}")
        return existing_data

    async def main(self):
        async with self:
            parser = argparse.ArgumentParser(description="Bangumi Scraper")
            subparsers = parser.add_subparsers(dest="mode", required=True)

            subparsers.add_parser("interactive", help="Interactive mode for manual runs")

            auto_parser = subparsers.add_parser("auto", help="Automatic mode for CI/CD")
            auto_parser.add_argument("--year", type=int, required=True)
            auto_parser.add_argument("--month", type=int)
            auto_parser.add_argument("--concurrent", type=int, default=3)

            args = parser.parse_args()

            if args.mode == "auto":
                os.environ["CONCURRENT_REQUESTS"] = str(args.concurrent)
                start_year = end_year = args.year
                start_month = end_month = args.month
                logging.info(
                    f"🏃 自动模式 | 年份: {args.year} | 月份: {args.month or '全年'} "
                    f"（数据源: bangumi-data + api.bgm.tv）"
                )
            else:
                year_input = input("请输入要爬取的年份（支持范围，如2010-2023）: ").strip()
                start_year, end_year = self.process_year_input(year_input)

                month_input = None
                if start_year == end_year:
                    month_input = (
                        input("请输入月份（可选，支持范围，如4-7）: ").strip() or None
                    )

                start_month, end_month = (
                    self.process_month_input(month_input) if month_input else (None, None)
                )

            output_file = os.path.abspath("Bangumi_Anime.md")
            logging.info(f"📝 输出文件: {output_file}")

            data = await self.scrape_time_range(
                start_year, end_year, start_month, end_month
            )
            self.generate_markdown(data, output_file)

    @staticmethod
    def process_year_input(input_str: str) -> Tuple[int, int]:
        if not input_str:
            raise ValueError("必须输入年份")
        if "-" in input_str:
            parts = input_str.split("-")
            if len(parts) != 2:
                raise ValueError("无效的年份范围格式")
            start, end = map(int, parts)
            return (min(start, end), max(start, end))
        if not input_str.isdigit():
            raise ValueError("年份必须为数字")
        return (int(input_str), int(input_str))

    @staticmethod
    def process_month_input(input_str: str) -> Tuple[int, int]:
        if not input_str:
            return (None, None)
        if "-" in input_str:
            parts = input_str.split("-")
            if len(parts) != 2:
                raise ValueError("无效的月份范围格式")
            start, end = map(int, parts)
            if not (1 <= start <= 12 and 1 <= end <= 12):
                raise ValueError("月份必须在1-12之间")
            return (min(start, end), max(start, end))
        if not input_str.isdigit() or not (1 <= int(input_str) <= 12):
            raise ValueError("无效的月份输入")
        return (int(input_str), int(input_str))


async def run():
    try:
        async with BangumiScraper() as scraper:
            await scraper.main()
    except Exception as e:
        logging.error(f"未知错误: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(run())
