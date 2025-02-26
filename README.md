# AnimeTimeline 动漫时间线

[English Version](README_en.md)

一个用于爬取和整理番剧放送信息的Python工具，支持按年份和月份获取动漫信息，并以Markdown格式保存。

## 功能特点

- 支持按年份或月份爬取番剧信息
- 自动获取番剧标题、日文标题、话数、放送日期、评分等信息
- 支持增量更新，避免重复数据
- 按日期分类整理，生成清晰的Markdown文档
- 自动处理网络异常，支持失败重试
- 支持批量爬取指定年份范围的数据

## 安装说明

1. 克隆项目到本地
```bash
git clone https://github.com/yourusername/AnimeTimeline.git
cd AnimeTimeline
```

2. 创建并激活虚拟环境（可选）
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows
```

3. 安装依赖包
```bash
pip install -r requirements.txt
```

## 使用说明

1. 运行爬虫程序
```bash
python pull.py
```

2. 根据提示输入要爬取的年份
   - 支持单个年份，如：2024
   - 支持年份范围，如：2000-2024

3. 输入要爬取的月份（可选）
   - 输入1-12的数字爬取指定月份
   - 直接回车则爬取整年数据

## 数据存储

- 数据按年份和月份分类存储在对应文件夹中
- 每个日期的番剧信息存储在单独的Markdown文件中
- Markdown文件包含以下信息：
  - 番剧标题（中文）
  - 日文标题
  - 话数
  - 放送日期
  - 评分
  - 评分人数
  - 播放链接
  - 封面图片链接

## 项目结构

```
AnimeTimeline/
├── pull.py          # 主程序文件
├── requirements.txt  # 项目依赖
├── README.md        # 项目说明文档
├── SECURITY.md      # 安全政策
└── .github/         # GitHub配置文件
    └── workflows/   # GitHub Actions工作流
```

## 注意事项

1. 请合理控制爬取频率，避免对目标网站造成压力
2. 建议使用虚拟环境运行项目，避免依赖冲突
3. 如遇到网络问题，程序会自动重试
4. 数据更新时会自动去重，避免重复内容

## 贡献指南

1. Fork 本仓库
2. 创建新的功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 开源许可

本项目采用 Apache 2.0 许可证 - 详见 [LICENSE](LICENSE) 文件

## 安全问题

如果发现任何安全漏洞，请查看我们的[安全政策](SECURITY.md)了解如何报告。