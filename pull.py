import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
import pandas as pd

# 请求头
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) \
        AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
}

# 替换非法字符的映射表
ILLEGAL_CHAR_MAP = {
    '<': '＜',
    '>': '＞',
    ':': '：',
    '"': '＂',
    '/': '／',
    '\\': '＼',
    '|': '｜',
    '?': '？',
    '*': '＊'
}


def sanitize_filename(name):
    """
    替换文件名中的非法字符
    :param name: 原始文件名
    :return: 清理后的文件名
    """
    for illegal_char, replacement in ILLEGAL_CHAR_MAP.items():
        name = name.replace(illegal_char, replacement)
    return name


def get_total_pages(year, month):
    """
    获取指定年月的总页数
    :param year: 动漫年份
    :param month: 动漫月份
    :return: 总页数 (int)
    """
    url = f"https://bangumi.tv/anime/browser/airtime/{year}-{month:02d}?sort=date"
    for _ in range(3):  # 重试3次
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'lxml')
            # 使用page_inner选择器获取分页信息
            page_edge = soup.select_one(".page_inner .p_edge")
            if page_edge:
                # 从文本中提取总页数，格式为 "( 当前页 / 总页数 )"
                text = page_edge.text.strip()
                total_pages = int(text.split('/')[-1].strip().rstrip(')'))
                return total_pages
            # 如果没有找到分页信息，检查是否只有一页
            page_inner = soup.select_one(".page_inner")
            if page_inner:
                # 获取所有页码链接
                page_links = page_inner.select("a.p, strong.p_cur")
                if page_links:
                    # 获取最后一个数字页码
                    last_page = max(int(link.text) for link in page_links if link.text.isdigit())
                    return last_page
            return 1
        except requests.exceptions.RequestException as e:
            print(f"请求失败，正在重试：{e}")
            time.sleep(5)
    print("获取总页数失败。")
    return 0

def scrape_anime_info(year, month, total_pages):
    anime_list = []
    base_url = f"https://bangumi.tv/anime/browser/airtime/{year}-{month:02d}?sort=date&page="

    for page in range(1, total_pages + 1):
        url = base_url + str(page)
        print(f"正在爬取第 {page}/{total_pages} 页：{url}")
        retries = 3  # 最大重试次数
        success = False

        while retries > 0 and not success:
            try:
                response = requests.get(url, headers=HEADERS, timeout=15)
                response.encoding = response.apparent_encoding
                soup = BeautifulSoup(response.text, 'lxml')

                # 获取所有动漫条目
                items = soup.select('#browserItemList > li.item')
                for item in items:
                    anime_info = {}
                    
                    # 提取标题和播放链接
                    title_elem = item.select_one('h3 > a.l')
                    if title_elem:
                        anime_info['标题'] = title_elem.text.strip()
                        anime_info['播放链接'] = 'https://bangumi.tv' + title_elem.get('href', '')
                        # 提取日文标题
                        jp_title = title_elem.find_next_sibling('small', class_='grey')
                        if jp_title:
                            anime_info['日文标题'] = jp_title.text.strip()
                    
                    # 提取封面图片URL
                    img_elem = item.select_one('a.subjectCover img.cover')
                    if img_elem:
                        img_url = img_elem.get('src', '')
                        # 处理以//开头的URL
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        # 处理相对路径的URL
                        elif img_url.startswith('/'):
                            img_url = 'https://bangumi.tv' + img_url
                        anime_info['封面'] = img_url
                    
                    # 提取话数和放送日期
                    info_elem = item.select_one('p.info.tip')
                    if info_elem:
                        info_text = info_elem.text.strip()
                        # 提取话数
                        eps_match = re.search(r'(\d+)话', info_text)
                        anime_info['话数'] = eps_match.group(1) if eps_match else '未知'
                        
                        # 优化日期提取逻辑
                        date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', info_text)
                        if date_match:
                            anime_info['年'] = int(date_match.group(1))
                            anime_info['月'] = int(date_match.group(2))
                            anime_info['日'] = int(date_match.group(3))
                        else:
                            # 尝试匹配YYYY-MM格式
                            year_month_match = re.search(r'(\d{4})-(\d{1,2})', info_text)
                            if year_month_match:
                                anime_info['年'] = int(year_month_match.group(1))
                                anime_info['月'] = int(year_month_match.group(2))
                                anime_info['日'] = 1  # 设置为当月1日
                            else:
                                anime_info['年'] = year
                                anime_info['月'] = month
                                anime_info['日'] = '未知'
                    
                    # 提取评分
                    rate_info = item.select_one('p.rateInfo')
                    if rate_info:
                        score = rate_info.select_one('small.fade')
                        if score:
                            anime_info['评分'] = score.text.strip()
                        else:
                            anime_info['评分'] = '暂无评分'
                        # 提取评分人数
                        rate_count = rate_info.select_one('span.tip_j')
                        if rate_count:
                            count_text = rate_count.text.strip('()')
                            anime_info['评分人数'] = count_text
                    
                    anime_list.append(anime_info)
                
                success = True  # 爬取成功
                time.sleep(random.uniform(1, 3))  # 随机延迟
            except requests.exceptions.RequestException as e:
                retries -= 1
                print(f"请求失败，剩余重试次数：{retries}，错误信息：{e}")
                time.sleep(5)

        if not success:
            print(f"跳过第 {page} 页。")
    return anime_list

def create_folder(year, month=None):
    """
    创建年份和月份文件夹
    :param year: 动漫年份
    :param month: 动漫月份（可选）
    :return: 创建的文件夹路径
    """
    # 创建年份文件夹
    year_folder = os.path.join(os.getcwd(), str(year))
    if not os.path.exists(year_folder):
        os.makedirs(year_folder)
        print(f"创建年份文件夹：{year_folder}")
    
    # 如果指定了月份，创建月份文件夹
    if month is not None:
        month_folder = os.path.join(year_folder, f"{month:02d}")
        if not os.path.exists(month_folder):
            os.makedirs(month_folder)
            print(f"创建月份文件夹：{month_folder}")
        return month_folder
    
    return year_folder

def save_to_markdown(anime_list, folder_path):
    """
    将爬取的动漫信息按日期分组保存到Markdown文件中，支持增量更新
    :param anime_list: 番剧信息列表
    :param folder_path: 保存文件的文件夹路径
    """
    # 按日期分组
    date_groups = {}
    for anime in anime_list:
        year = anime['年']
        month = anime['月']
        day = anime['日']
        
        # 创建日期键
        date_key = f"{day if day != '未知' else 'unknown'}"
        
        if date_key not in date_groups:
            date_groups[date_key] = []
        date_groups[date_key].append(anime)
    
    # 为每个日期创建单独的Markdown文件
    for date_key, animes in date_groups.items():
        # 创建Markdown文件
        output_file = os.path.join(folder_path, f'{date_key}.md')
        existing_data = []
        
        # 读取已有的Markdown文件内容（如果存在）
        if os.path.exists(output_file):
            try:
                # 从Markdown表格中提取数据
                with open(output_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if len(lines) > 2:  # 确保文件至少包含表头
                        # 解析现有的Markdown表格数据
                        for line in lines[2:]:  # 跳过表头和分隔行
                            if line.strip() and '|' in line:
                                cols = [col.strip() for col in line.split('|')[1:-1]]
                                if len(cols) >= 8:  # 确保有足够的列
                                    existing_data.append({
                                        '标题': cols[0],
                                        '日文标题': cols[1],
                                        '话数': cols[2],
                                        '年': int(cols[3]),
                                        '月': int(cols[4]),
                                        '日': cols[5],
                                        '评分': cols[6],
                                        '评分人数': cols[7],
                                        '播放链接': cols[8],
                                        '封面': cols[9]
                                    })
            except Exception as e:
                print(f"读取已有文件失败：{e}，将创建新文件")
        
        # 通过播放链接去重
        existing_links = {item['播放链接'] for item in existing_data}
        new_animes = [anime for anime in animes if anime['播放链接'] not in existing_links]
        
        if new_animes or not existing_data:  # 如果有新数据或文件不存在
            # 合并现有数据和新数据
            all_animes = existing_data + new_animes
            
            # 按日期排序（未知日期放在最后）
            def sort_key(x):
                day = x['日']
                return float('inf') if day == '未知' else (float(day) if isinstance(day, (int, str)) else day)
            
            all_animes.sort(key=sort_key)
            
            # 创建Markdown表格内容
            table_content = "# 番剧信息\n\n"
            table_content += "|放送日期|封面|标题|日文标题|话数|评分|评分人数|\n"
            table_content += "|---|---|---|---|---|---|---|\n"
            
            for anime in all_animes:
                # 确保所有字段都存在，如果不存在则使用空字符串
                title = anime.get('标题', '').replace('|', '\\|')
                jp_title = anime.get('日文标题', '').replace('|', '\\|')
                episodes = anime.get('话数', '')
                year = anime.get('年', '')
                month = anime.get('月', '')
                day = anime.get('日', '')
                rating = anime.get('评分', '')
                rating_count = anime.get('评分人数', '')
                play_url = anime.get('播放链接', '')
                cover_url = anime.get('封面', '')
                
                # 处理日期格式
                date_str = f"{year:04d}-{month:02d}-{day:02d}" if isinstance(day, int) else f"{year:04d}-{month:02d}"
                
                # 处理封面图片和标题链接
                cover_img = f"![封面]({cover_url})" if cover_url else ''
                title_link = f"[{title}]({play_url})" if play_url and title else title
                
                # 添加表格行，处理特殊字符
                table_content += f"|{date_str}|{cover_img}|{title_link}|{jp_title}|{episodes}|{rating}|{rating_count}|\n"
            
            # 保存Markdown文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(table_content)
            
            print(f"已将 {len(new_animes)} 部新番剧信息追加到文件：{output_file}")
        else:
            print(f"日期 {date_key} 没有新增番剧信息")

def process_year_input(year_str):
    """
    处理年份输入，支持单年和年份范围
    :param year_str: 年份输入字符串
    :return: (start_year, end_year) 元组
    """
    if '-' in year_str:
        # 处理年份范围
        try:
            start_year, end_year = map(int, year_str.split('-'))
            if start_year > end_year:
                start_year, end_year = end_year, start_year
            return start_year, end_year
        except ValueError:
            print("请输入有效的年份范围！例如：2000-2025")
            exit()
    else:
        # 处理单年
        if not year_str.isdigit():
            print("请输入有效的年份！")
            exit()
        year = int(year_str)
        return year, year

def process_month_input():
    """
    处理月份输入
    :return: 月份数字或None
    """
    month = input("请输入要爬取的月份（1-12，直接回车则查询整年）：").strip()
    if not month:  # 直接回车
        return None
    if not month.isdigit() or not (1 <= int(month) <= 12):
        print("请输入有效的月份（1-12）！")
        exit()
    return int(month)

if __name__ == "__main__":
    # 1. 用户交互输入
    year_input = input("请输入要爬取的年份（支持范围，如：2000-2025）：").strip()
    start_year, end_year = process_year_input(year_input)
    
    # 获取当前年月
    current_year = time.localtime().tm_year
    current_month = time.localtime().tm_mon
    
    # 如果结束年份超过当前年份，则设置为当前年份
    if end_year > current_year:
        end_year = current_year
        print(f"结束年份已调整为当前年份：{current_year}")
    
    # 如果是年份范围，不需要输入月份
    month = None if start_year != end_year else process_month_input()
    
    all_anime_list = []
    
    # 2. 遍历年份范围
    for year in range(start_year, end_year + 1):
        if month is None:
            # 按年份查询
            print(f"\n开始处理 {year} 年的数据...")
            # 确定结束月份
            end_month = current_month if year == current_year else 12
            for m in range(1, end_month + 1):
                print(f"\n正在获取 {year} 年 {m} 月的总页数...")
                total_pages = get_total_pages(year, m)
                if total_pages > 0:
                    print(f"{year} 年 {m} 月共有 {total_pages} 页。")
                    print("开始爬取番剧信息...")
                    anime_list = scrape_anime_info(year, m, total_pages)
                    all_anime_list.extend(anime_list)
                    print(f"完成 {year} 年 {m} 月的爬取，获取 {len(anime_list)} 部番剧信息。")
                time.sleep(random.uniform(1, 3))  # 随机延迟
        else:
            # 按年月查询
            # 检查是否超过当前月份
            if year == current_year and month > current_month:
                print(f"跳过 {year} 年 {month} 月，因为超过当前月份。")
                continue
            
            print(f"\n正在获取 {year} 年 {month} 月的总页数...")
            total_pages = get_total_pages(year, month)
            if total_pages > 0:
                print(f"{year} 年 {month} 月共有 {total_pages} 页。")
                print("开始爬取番剧信息...")
                anime_list = scrape_anime_info(year, month, total_pages)
                all_anime_list.extend(anime_list)
                print(f"完成 {year} 年 {month} 月的爬取，获取 {len(anime_list)} 部番剧信息。")
    
    print(f"\n所有爬取完成，共获取 {len(all_anime_list)} 部番剧信息。")
    
    # 3. 创建输出文件夹并保存文件
    for year in range(start_year, end_year + 1):
        if month is None:
            # 按年份查询时，为每个月创建单独的文件夹
            end_month = current_month if year == current_year else 12
            for m in range(1, end_month + 1):
                # 过滤出当前年月的动漫
                current_month_anime = [anime for anime in all_anime_list 
                                     if anime['年'] == year and anime['月'] == m]
                if current_month_anime:
                    month_folder = create_folder(year, m)
                    save_to_markdown(current_month_anime, month_folder)
        else:
            # 按年月查询时，只创建指定月份的文件夹
            if not (year == current_year and month > current_month):
                current_month_anime = [anime for anime in all_anime_list 
                                     if anime['年'] == year and anime['月'] == month]
                if current_month_anime:
                    month_folder = create_folder(year, month)
                    save_to_markdown(current_month_anime, month_folder)