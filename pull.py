import argparse
import asyncio
import logging
import os
import re
import time
import glob
from collections import defaultdict
from typing import Dict, List, Tuple

import aiohttp
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 请求头配置
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 '
                  'Safari/537.36',
    'Referer': 'https://bangumi.tv/'
}

# 正则表达式预编译
EPS_PATTERN = re.compile(r'(\d+)话')
FULL_DATE_PATTERN = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日')
YEAR_MONTH_PATTERN = re.compile(r'(\d{4})年(\d{1,2})月')
YEAR_PATTERN = re.compile(r'(\d{4})年')
# 新增的正则表达式，用于匹配格式化的日期
FORMATTED_DATE_PATTERN = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})(?:\(.*?\))?')
FORMATTED_YEAR_MONTH_PATTERN = re.compile(r'(\d{4})-(\d{1,2})(?:\(.*?\))?')

# 并发控制配置
DEFAULT_CONCURRENT = 3
MAX_CONCURRENT = int(os.environ.get('CONCURRENT_REQUESTS', DEFAULT_CONCURRENT))


class BangumiScraper:
    def __init__(self):
        self.semaphore = None
        self.connector = None
        self.current_year = time.localtime().tm_year
        self.current_month = time.localtime().tm_mon

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self.connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, ssl=False)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """异步上下文管理器出口"""
        await self.connector.close()

    async def fetch_pages(self, session: aiohttp.ClientSession, url: str) -> int:
        """获取总页数"""
        retries = 3
        while retries > 0:
            try:
                async with session.get(url, headers=HEADERS, timeout=20) as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status)

                    soup = BeautifulSoup(await resp.text(), 'lxml')
                    pagination = soup.select_one('.page_inner')

                    if not pagination:
                        return 1

                    last_page = 1
                    for page in pagination.select('a.p'):
                        if page.text.isdigit():
                            last_page = max(last_page, int(page.text))
                    return last_page

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                retries -= 1
                logging.info(f"获取页数失败: {str(e)}，剩余重试次数: {retries}")
                await asyncio.sleep(2 + retries * 3)
        return 0

    async def scrape_page(self, session: aiohttp.ClientSession, base_url: str, page: int, year: int,
                          month: int = None) -> List[Dict]:
        """爬取单个页面"""
        url = f"{base_url}&page={page}"
        logging.info(f"正在爬取: {url}")

        try:
            async with self.semaphore:
                async with session.get(url, headers=HEADERS, timeout=20) as resp:
                    resp.raise_for_status()
                    soup = BeautifulSoup(await resp.text(), 'lxml')
                    return self.parse_page(soup, year, month)
        except Exception as e:
            logging.info(f"页面爬取失败: {url}，错误: {str(e)}")
            return []

    def parse_page(self, soup: BeautifulSoup, base_year: int, base_month: int = None) -> List[Dict]:
        """解析页面内容（修复标题和封面问题）"""
        results = []
        for item in soup.select('#browserItemList > li.item'):
            anime = defaultdict(str)

            # 标题信息处理
            title_tag = item.select_one('h3 > a.l')
            if title_tag:
                # 提取中文标题（主标题）
                anime['title'] = title_tag.text.strip()
                anime['url'] = f"https://bangumi.tv{title_tag['href']}"

                # 提取日文标题（副标题）
                if jp_title := title_tag.find_next_sibling('small', class_='grey'):
                    anime['jp_title'] = jp_title.text.strip()

            # 封面图片处理
            if img := item.select_one('a.subjectCover img.cover'):
                # 修复封面URL协议问题
                cover_url = img.get('src') or img.get('data-cfsrc', '')
                if cover_url.startswith('//'):
                    cover_url = f"https:{cover_url}"
                anime['cover'] = cover_url

            # 元数据解析
            self.parse_metadata(item.select_one('p.info.tip'), anime, base_year, base_month)
            self.parse_rating(item.select_one('p.rateInfo'), anime)

            results.append(anime)
        return results

    def parse_metadata(self, elem: BeautifulSoup, anime: Dict, base_year: int, base_month: int = None):
        """解析元数据"""
        if not elem:
            return

        text = elem.text.strip()

        # 初始化默认值
        anime.update({
            'year': base_year,
            'month': base_month or 0,
            'day': 0
        })

        # 话数提取
        if eps := EPS_PATTERN.search(text):
            anime['episodes'] = eps.group(1)

        # 日期解析 - 按优先顺序尝试不同格式
        if formatted_date := FORMATTED_DATE_PATTERN.search(text):
            anime.update({
                'year': int(formatted_date.group(1)),
                'month': int(formatted_date.group(2)),
                'day': int(formatted_date.group(3))
            })
        elif full_date := FULL_DATE_PATTERN.search(text):
            anime.update({
                'year': int(full_date.group(1)),
                'month': int(full_date.group(2)),
                'day': int(full_date.group(3))
            })
        elif formatted_ym := FORMATTED_YEAR_MONTH_PATTERN.search(text):
            anime.update({
                'year': int(formatted_ym.group(1)),
                'month': int(formatted_ym.group(2)),
                'day': 0
            })
        elif ym_date := YEAR_MONTH_PATTERN.search(text):
            anime.update({
                'year': int(ym_date.group(1)),
                'month': int(ym_date.group(2)),
                'day': 0
            })
        elif year_only := YEAR_PATTERN.search(text):
            anime['year'] = int(year_only.group(1))
            anime['month'] = 0
            anime['day'] = 0
        elif direct_year := re.search(r'\b(\d{4})\b', text):
            anime['year'] = int(direct_year.group(1))
            anime['month'] = 0
            anime['day'] = 0

    @staticmethod
    def parse_rating(elem: BeautifulSoup, anime: Dict):
        """解析评分信息"""
        if not elem:
            return

        if score := elem.select_one('span.number'):
            anime['score'] = score.text.strip()

        if count := elem.select_one('span.tip_j'):
            anime['votes'] = count.text.strip('()')

    async def scrape_time_range(self, session: aiohttp.ClientSession, start_year: int, end_year: int,
                                start_month: int = None, end_month: int = None) -> List[Dict]:
        """处理时间范围爬取"""
        all_data = []

        for year in range(start_year, end_year + 1):
            if start_year != end_year:
                months = [None]
            else:
                months = range(start_month, end_month + 1) if start_month else [None]

            for month in months:
                if month:
                    url = f"https://bangumi.tv/anime/browser/airtime/{year}-{month:02d}?sort=date"
                else:
                    url = f"https://bangumi.tv/anime/browser/airtime/{year}?sort=date"

                if year == self.current_year and month and month > self.current_month:
                    logging.info(f"跳过未来月份: {year}-{month}")
                    continue

                total_pages = await self.fetch_pages(session, url)
                if total_pages == 0:
                    continue

                tasks = [self.scrape_page(session, url, p, year, month)
                         for p in range(1, total_pages + 1)]
                results = await asyncio.gather(*tasks)
                all_data.extend(
                    [item for sublist in results for item in sublist])

        return all_data

    def generate_markdown(self, new_data: List[Dict], filename: str = "Bangumi_Anime.md"):
        """生成或更新Markdown报告（按年份拆分）"""
        existing_data = self.parse_existing_markdown(filename) if os.path.exists(filename) else []

        new_items_count = 0
        new_years_data = defaultdict(int)

        merged_data = []
        seen = set()

        for item in existing_data:
            identifier = (
                item.get('year'),
                item.get('title'),
                item.get('episodes'),
                (item.get('url') or '').split('/')[-1]
            )
            if identifier not in seen:
                seen.add(identifier)
                merged_data.append(item)

        for item in new_data:
            identifier = (
                item.get('year'),
                item.get('title'),
                item.get('episodes'),
                (item.get('url') or '').split('/')[-1]
            )
            if identifier not in seen:
                seen.add(identifier)
                new_items_count += 1
                new_years_data[item.get('year')] += 1
                merged_data.append({
                    'year': item.get('year', 0),
                    'month': item.get('month', 0),
                    'day': item.get('day', 0),
                    'cover': item.get('cover', ''),
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'jp_title': item.get('jp_title', ''),
                    'episodes': item.get('episodes', '未知'),
                    'score': item.get('score', '-'),
                    'votes': item.get('votes', '0')
                })

        year_dict = defaultdict(list)
        for item in merged_data:
            year = item.get('year', '未知')
            if year == 0 or year == '未知':
                continue
            year_dict[year].append(item)

        os.makedirs('data', exist_ok=True)

        sorted_years = sorted(year_dict.keys(),
                              key=lambda y: int(y) if str(y).isdigit() else 0,
                              reverse=True)

        for year in sorted_years:
            md_content = "# Bangumi番剧数据报告\n\n"
            md_content += f"## {year}年\n\n"
            md_content += "| 放送日期 | 封面 | 中文标题 | 日文标题 | 话数 | 评分 | 评分人数 |\n"
            md_content += "| --- | --- | --- | --- | --- | --- | --- |\n"

            sorted_items = sorted(
                year_dict[year],
                key=lambda x: (-int(x.get('year') or 0),
                               -int(x.get('month') or 0),
                               -int(x.get('day') or 0))
            )

            for item in sorted_items:
                date_parts = []
                if item.get('year'):
                    date_parts.append(f"{item['year']}")
                    if item.get('month') and int(item['month']) > 0:
                        date_parts.append(f"{int(item['month']):02d}")
                        if item.get('day') and int(item['day']) > 0:
                            date_parts.append(f"{int(item['day']):02d}")
                date_str = "-".join(date_parts) if date_parts else "未知"

                cover = f"![]({item['cover']})" if item.get('cover') else ""

                ch_title = (item.get('title') or '未知标题').strip()
                title_link = f"[{ch_title}]({item.get('url', '')})" if item.get('url') else ch_title

                jp_title = (item.get('jp_title') or '').strip()
                votes_raw = item.get('votes', '0')
                votes = re.sub(r'\D', '', str(votes_raw)) or '0'

                md_content += f"| {date_str} | {cover} | {title_link} | {jp_title} | " \
                              f"{item.get('episodes', '未知')} | {item.get('score', '-')} | " \
                              f"{votes} |\n"
            md_content += "\n"

            year_file = os.path.join('data', f"{year}.md")
            with open(year_file, 'w', encoding='utf-8') as f:
                f.write(md_content)

        index = "# Bangumi番剧数据报告\n\n"
        index += "> 由于原始文件过大，GitHub 无法正常预览，现已按年份拆分存档。\n\n"
        index += "## 年份索引\n\n"
        for year in sorted_years:
            index += f"- [{year}年](data/{year}.md)\n"
        index += "\n## 说明\n\n"
        index += "- 数据自动从 [Bangumi.tv](https://bangumi.tv) 抓取并合并\n"
        index += "- 每日自动更新（GitHub Actions）\n"
        index += "- 如需查看全部历史数据，请直接浏览 [data/](data/) 目录\n"

        index_path = filename
        if not os.path.isabs(index_path):
            index_path = os.path.abspath(index_path)
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index)

        logging.info("✅ 数据合并完成:")
        logging.info(f"   - 现有数据: {len(existing_data)} 条")
        logging.info(f"   - 本次新增: {new_items_count} 条")
        if new_items_count > 0:
            logging.info("   - 新增数据年份分布:")
            for year, count in sorted(new_years_data.items(), reverse=True):
                logging.info(f"     * {year}年: {count} 条")
        logging.info(f"📝 已按年份写入 data/ 并更新索引: {index_path}")

    def parse_existing_markdown(self, filename: str) -> List[Dict]:
        """解析现有Markdown文件（优先读取 data/ 目录）"""
        existing_data = []
        parsed_count = 0

        data_files = sorted(glob.glob(os.path.join('data', '*.md')))
        if not data_files:
            if not os.path.exists(filename):
                return []
            data_files = [filename]

        for filepath in data_files:
            current_year = None
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('## '):
                            year_match = re.match(r'## (\d+)年', line)
                            if year_match:
                                current_year = int(year_match.group(1))
                                continue
                        elif line.startswith('|') and not line.startswith(('| ---', '| 放送日期')):
                            parts = [p.strip() for p in line.split('|')[1:-1]]
                            if len(parts) < 6:
                                continue
                            try:
                                cover = ''
                                if '![]' in parts[1]:
                                    cover_match = re.search(r'!\[\]\((.*?)\)', parts[1])
                                    if cover_match:
                                        cover = cover_match.group(1)

                                title = parts[2]
                                url = ''
                                if '[' in parts[2] and '](' in parts[2]:
                                    title_match = re.search(r'\[(.*?)\]', parts[2])
                                    url_match = re.search(r'\]\((.*?)\)', parts[2])
                                    if title_match:
                                        title = title_match.group(1)
                                    if url_match:
                                        url = url_match.group(1)

                                item = {
                                    'year': current_year,
                                    'month': 0,
                                    'day': 0,
                                    'cover': cover,
                                    'title': title,
                                    'url': url,
                                    'jp_title': parts[3],
                                    'episodes': parts[4],
                                    'score': parts[5],
                                    'votes': parts[6] if len(parts) > 6 else '0'
                                }

                                date_str = parts[0]
                                date_parts = date_str.split('-')
                                try:
                                    if len(date_parts) >= 1 and date_parts[0].isdigit():
                                        item['year'] = int(date_parts[0])
                                    if len(date_parts) >= 2 and date_parts[1].isdigit():
                                        item['month'] = int(date_parts[1])
                                    if len(date_parts) >= 3:
                                        if date_parts[2].isdigit():
                                            item['day'] = int(date_parts[2])
                                        elif '(' in date_parts[2]:
                                            day_part = date_parts[2].split('(')[0]
                                            if day_part.isdigit():
                                                item['day'] = int(day_part)
                                except ValueError:
                                    pass

                                existing_data.append(item)
                                parsed_count += 1
                            except Exception as e:
                                logging.debug(f"解析行出错: {line[:50]}... | 错误: {str(e)}")
                                continue
            except Exception as e:
                logging.error(f"❌ 解析文件出错 {filepath}: {str(e)}")
                continue

        logging.info(f"✅ 解析旧数据完成 | 解析文件数: {len(data_files)} | 解析条目: {parsed_count}")
        return existing_data

    async def main(self):
        async with self:
            parser = argparse.ArgumentParser(description='Bangumi Scraper')
            subparsers = parser.add_subparsers(dest='mode', required=True)

            interactive_parser = subparsers.add_parser(
                'interactive', help='Interactive mode for manual runs')

            auto_parser = subparsers.add_parser(
                'auto', help='Automatic mode for CI/CD')
            auto_parser.add_argument(
                '--year', type=int, required=True, help='Target year')
            auto_parser.add_argument('--month', type=int, help='Target month')
            auto_parser.add_argument(
                '--concurrent', type=int, default=3, help='Concurrent requests')

            args = parser.parse_args()

            if args.mode == 'auto':
                os.environ['CONCURRENT_REQUESTS'] = str(args.concurrent)
                start_year = end_year = args.year
                start_month = end_month = args.month
                logging.info(f"🏃 自动模式启动 | 年份: {args.year} | 月份: {args.month or '全年'}")
            else:
                year_input = input("请输入要爬取的年份（支持范围，如2010-2023）: ").strip()
                start_year, end_year = self.process_year_input(year_input)

                month_input = None
                if start_year == end_year:
                    month_input = input(
                        "请输入月份（可选，支持范围，如4-7）: ").strip() or None

                start_month, end_month = self.process_month_input(
                    month_input) if month_input else (None, None)

            output_file = "Bangumi_Anime.md"
            if not os.path.isabs(output_file):
                output_file = os.path.abspath(output_file)

            logging.info(f"📝 输出文件路径: {output_file}")

            async with aiohttp.ClientSession(connector=self.connector) as session:
                data = await self.scrape_time_range(session, start_year, end_year, start_month, end_month)
                self.generate_markdown(data, output_file)

    @staticmethod
    def process_year_input(input_str: str) -> Tuple[int, int]:
        if not input_str:
            raise ValueError("必须输入年份")

        if '-' in input_str:
            parts = input_str.split('-')
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

        if '-' in input_str:
            parts = input_str.split('-')
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
    except aiohttp.ClientError as e:
        logging.error(f"网络请求错误: {str(e)}")
    except Exception as e:
        logging.error(f"未知错误: {str(e)}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(run())
