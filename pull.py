import argparse
import asyncio
import logging
import os
import re
import time
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
DEFAULT_CONCURRENT = 5
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
        # 1. 先尝试匹配完整的格式化日期 YYYY-MM-DD
        if formatted_date := FORMATTED_DATE_PATTERN.search(text):
            anime.update({
                'year': int(formatted_date.group(1)),
                'month': int(formatted_date.group(2)),
                'day': int(formatted_date.group(3))
            })
        # 2. 尝试匹配中文完整日期 YYYY年MM月DD日
        elif full_date := FULL_DATE_PATTERN.search(text):
            anime.update({
                'year': int(full_date.group(1)),
                'month': int(full_date.group(2)),
                'day': int(full_date.group(3))
            })
        # 3. 尝试匹配格式化年月 YYYY-MM
        elif formatted_ym := FORMATTED_YEAR_MONTH_PATTERN.search(text):
            anime.update({
                'year': int(formatted_ym.group(1)),
                'month': int(formatted_ym.group(2)),
                'day': 0
            })
        # 4. 尝试匹配中文年月 YYYY年MM月
        elif ym_date := YEAR_MONTH_PATTERN.search(text):
            anime.update({
                'year': int(ym_date.group(1)),
                'month': int(ym_date.group(2)),
                'day': 0
            })
        # 5. 最后尝试仅匹配年份
        elif year_only := YEAR_PATTERN.search(text):
            anime['year'] = int(year_only.group(1))
            anime['month'] = 0
            anime['day'] = 0
        # 6. 如果以上都没匹配到，尝试直接匹配数字年份
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
            # 当输入年份范围时，忽略月份参数
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
        """生成或更新Markdown报告"""
        # 合并现有数据
        existing_data = self.parse_existing_markdown(
            filename) if os.path.exists(filename) else []

        # 记录新数据的统计信息
        new_items_count = 0
        new_years_data = defaultdict(int)

        # 合并数据并跟踪新增条目
        merged_data = []
        seen = set()

        # 处理现有数据
        for item in existing_data:
            identifier = (
                item.get('year'),
                item.get('title'),
                item.get('episodes'),
                item.get('url', '').split('/')[-1] if item.get('url') else ''
            )
            if identifier not in seen:
                seen.add(identifier)
                merged_data.append(item)

        # 处理新数据
        for item in new_data:
            identifier = (
                item.get('year'),
                item.get('title'),
                item.get('episodes'),
                item.get('url', '').split('/')[-1] if item.get('url') else ''
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

        # 按年份分组
        year_dict = defaultdict(list)
        for item in merged_data:
            year = item.get('year', '未知')
            year_dict[year].append(item)

        # 创建目录结构
        md_content = "# Bangumi番剧数据报告\n\n## 目录\n"
        sorted_years = sorted(year_dict.keys(),
                              key=lambda y: int(y) if str(y).isdigit() else 0,
                              reverse=True)

        # 生成目录
        for year in sorted_years:
            md_content += f"- [{year}年](#{year}年)\n"
        md_content += "\n"

        # 生成详细内容
        for year in sorted_years:
            md_content += f"## {year}年\n\n"
            md_content += "| 放送日期 | 封面 | 中文标题 | 日文标题 | 话数 | 评分 | 评分人数 |\n"
            md_content += "| --- | --- | --- | --- | --- | --- | --- |\n"

            # 按日期排序
            sorted_items = sorted(
                year_dict[year],
                key=lambda x: (-x['year'], -
                x.get('month', 0), -x.get('day', 0))
            )

            # 生成表格行
            for item in sorted_items:
                # 日期格式化
                date_parts = []
                if item.get('year'):
                    date_parts.append(f"{item['year']}")
                    if item.get('month') and item['month'] > 0:  # 确保月份有效
                        date_parts.append(f"{item['month']:02d}")
                        if item.get('day') and item['day'] > 0:  # 确保日期有效
                            date_parts.append(f"{item['day']:02d}")
                date_str = "-".join(date_parts) if date_parts else "未知"

                # 封面处理
                cover = f"![]({item['cover']})" if item.get('cover') else ""

                # 标题链接
                ch_title = item.get('title', '未知标题').strip()
                title_link = f"[{ch_title}]({item.get('url', '')})" if item.get(
                    'url') else ch_title

                # 日文标题处理
                jp_title = item.get('jp_title', '').strip()

                # 评分人数处理
                votes = re.sub(r'\D', '', item.get('votes', '0'))  # 提取纯数字
                votes = votes if votes else '0'

                md_content += f"| {date_str} | {cover} | {title_link} | {jp_title} | " \
                              f"{item.get('episodes', '未知')} | {item.get('score', '-')} | " \
                              f"{votes} |\n"
            md_content += "\n"

        # 输出统计信息
        logging.info("✅ 数据合并完成:")
        logging.info(f"   - 现有数据: {len(existing_data)} 条")
        logging.info(f"   - 本次新增: {new_items_count} 条")

        # 按年份显示新增数据统计
        if new_items_count > 0:
            logging.info("   - 新增数据年份分布:")
            for year, count in sorted(new_years_data.items(), reverse=True):
                logging.info(f"     * {year}年: {count} 条")

        # 写入文件
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(md_content)
        logging.info(f"📝 报告已保存至: {os.path.abspath(filename)}")

    def parse_existing_markdown(self, filename: str) -> List[Dict]:
        """解析现有Markdown文件"""
        existing_data = []
        current_year = None
        line_count = 0
        parsed_count = 0

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    line_count += 1
                    line = line.strip()

                    # 匹配年份标题
                    if line.startswith('## '):
                        year_match = re.match(r'## (\d+)年', line)
                        if year_match:
                            current_year = int(year_match.group(1))

                    # 匹配表格行
                    elif line.startswith('|') and not line.startswith(('| ---', '| 放送日期')):
                        parts = [p.strip() for p in line.split('|')[1:-1]]
                        if len(parts) >= 6:
                            try:
                                # 解析封面URL
                                cover = ''
                                if '![]' in parts[1]:
                                    cover_match = re.search(
                                        r'!\[\]\((.*?)\)', parts[1])
                                    if cover_match:
                                        cover = cover_match.group(1)

                                # 解析标题和URL
                                title = parts[2]
                                url = ''
                                if '[' in parts[2] and '](' in parts[2]:
                                    title_match = re.search(r'\[(.*?)\]', parts[2])
                                    url_match = re.search(r'\]\((.*?)\)', parts[2])
                                    if title_match:
                                        title = title_match.group(1)
                                    if url_match:
                                        url = url_match.group(1)

                                # 初始化条目，确保有默认值
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

                                # 解析日期（加强日期解析）
                                date_str = parts[0]
                                date_parts = date_str.split('-')

                                try:
                                    if len(date_parts) >= 1:
                                        # 处理纯年份格式
                                        if date_parts[0].isdigit():
                                            item['year'] = int(date_parts[0])

                                    if len(date_parts) >= 2:
                                        # 处理年-月格式
                                        if date_parts[1].isdigit():
                                            item['month'] = int(date_parts[1])

                                    if len(date_parts) >= 3:
                                        # 处理年-月-日格式
                                        if date_parts[2].isdigit():
                                            item['day'] = int(date_parts[2])
                                        # 处理可能含有括号的情况, 如 "25(美国)"
                                        elif '(' in date_parts[2]:
                                            day_part = date_parts[2].split('(')[0]
                                            if day_part.isdigit():
                                                item['day'] = int(day_part)
                                except ValueError:
                                    # 如果日期解析失败，保留当前年份
                                    item['year'] = current_year

                                existing_data.append(item)
                                parsed_count += 1
                            except Exception as e:
                                logging.error(f"⚠️ 解析行出错: {line[:50]}... | 错误: {str(e)}")
                                continue

            logging.info(f"✅ 解析旧数据完成 | 总行数: {line_count} | 解析条目: {parsed_count}")
            return existing_data
        except Exception as e:
            logging.error(f"❌ 解析文件出错: {str(e)}")
            # 发生错误时返回空列表，确保程序可以继续运行
            return []

    @staticmethod
    def merge_data(existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """合并并去重数据"""
        seen = set()
        merged = []

        # 处理现有数据
        for item in existing:
            identifier = (
                item.get('year'),
                item.get('title'),
                item.get('episodes'),
                item.get('url', '').split('/')[-1] if item.get('url') else ''
            )
            if identifier not in seen:
                seen.add(identifier)
                merged.append(item)

        # 处理新数据
        for item in new:
            identifier = (
                item.get('year'),
                item.get('title'),
                item.get('episodes'),
                item.get('url', '').split('/')[-1] if item.get('url') else ''
            )
            if identifier not in seen:
                seen.add(identifier)
                merged.append({
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

        return merged

    async def main(self):
        async with self:
            parser = argparse.ArgumentParser(description='Bangumi Scraper')
            subparsers = parser.add_subparsers(dest='mode', required=True)

            # 交互模式
            interactive_parser = subparsers.add_parser(
                'interactive', help='Interactive mode for manual runs')

            # 自动模式
            auto_parser = subparsers.add_parser(
                'auto', help='Automatic mode for CI/CD')
            auto_parser.add_argument(
                '--year', type=int, required=True, help='Target year')
            auto_parser.add_argument('--month', type=int, help='Target month')
            auto_parser.add_argument(
                '--concurrent', type=int, default=3, help='Concurrent requests')

            args = parser.parse_args()

            if args.mode == 'auto':
                # 自动模式逻辑
                os.environ['CONCURRENT_REQUESTS'] = str(args.concurrent)
                start_year = end_year = args.year
                start_month = end_month = args.month
                logging.info(f"🏃 自动模式启动 | 年份: {args.year} | 月份: {args.month or '全年'}")
            else:
                # 交互模式逻辑
                year_input = input("请输入要爬取的年份（支持范围，如2010-2023）: ").strip()
                start_year, end_year = self.process_year_input(year_input)

                month_input = None
                if start_year == end_year:
                    month_input = input(
                        "请输入月份（可选，支持范围，如4-7）: ").strip() or None

                start_month, end_month = self.process_month_input(
                    month_input) if month_input else (None, None)

            # 定义输出文件路径
            output_file = "Bangumi_Anime.md"
            # 确保文件路径是绝对路径
            if not os.path.isabs(output_file):
                output_file = os.path.abspath(output_file)

            logging.info(f"📝 输出文件路径: {output_file}")

            async with aiohttp.ClientSession(connector=self.connector) as session:
                data = await self.scrape_time_range(session, start_year, end_year, start_month, end_month)
                # 确保在自动模式下也能正确合并现有数据
                self.generate_markdown(data, output_file)

    @staticmethod
    def process_year_input(input_str: str) -> Tuple[int, int]:
        """处理年份输入"""
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
        """处理月份输入"""
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
