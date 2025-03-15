# AnimeTimeline 动漫时间线

[English Version](README.md)

一个用于爬取和整理番剧放送信息的 Python 工具，支持按年份和月份获取动漫信息，并以 Markdown 格式保存。包含自动化更新工作流，支持每日自动同步最新番剧数据。

## 功能特点

- 📅 双模式运行：支持交互式命令行和自动化脚本两种模式
- ⚡ 智能更新：每日自动同步最新番剧数据（北京时间 8:00）
- 📈 增量更新：自动合并新旧数据，智能去重处理
- 🕰️ 时间范围：支持年份范围（如 2010-2024）和月份范围（如 4-7）
- 📦 数据导出：生成结构化 Markdown 文档，包含完整元数据
- 🔁 失败重试：自动处理网络异常，支持 3 次重试机制
- 🤖 自动归档：通过 GitHub Actions 自动创建版本化 Pull Request
- 🛡️ 安全控制：可配置并发请求数（默认 3 并发）

## 安装说明

1. 克隆项目到本地
   ```bash
   git clone https://github.com/yourusername/AnimeTimeline.git
   cd AnimeTimeline
   ```

2. 创建并激活虚拟环境（推荐）
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

### 交互模式（手动运行）

```bash
python pull.py interactive
```

- 根据提示输入年份范围（如 2010-2024）
- 输入月份范围（可选，仅限单个年份时）
- 数据将保存至 [Bangumi_Anime.md](Bangumi_Anime.md)

### 自动模式（脚本调用）

```bash
python pull.py auto --year 2024 --month 3
```

| 参数 | 说明 | 示例 |
| --- | --- | --- |
| --year | 目标年份（必填） | 2024 |
| --month | 目标月份（可选） | 3 |
| --concurrent | 并发数（默认 3） | 5 |

### 自动化工作流

```yaml
# 定时任务：
- 每日自动运行，更新当月数据
- 每月 1 日补充更新上月数据
- 自动生成版本化 Pull Request

# 手动触发：
- 支持通过 GitHub 界面手动触发更新
```

## 数据存储

- 📂 数据文件：[Bangumi_Anime.md](Bangumi_Anime.md) - 包含完整的动漫时间线数据
- 🗂️ 版本控制：通过 Git 分支管理历史版本
- 📊 数据结构：

```markdown
| 放送日期 | 封面 | 中文标题 | 日文标题 | 话数 | 评分 | 评分人数 |
| --- | --- | --- | --- | --- | --- | --- |
| 2024-03 | ![](封面URL) | [标题](详情页) | 原版标题 | 12 | 8.9 | 1523 |
```

## 项目结构

```
AnimeTimeline/
├── .github/          # 自动化配置
│   └── workflows/
│       └── update-anime.yml  # 每日更新工作流
├── pull.py           # 主程序（支持双模式）
├── requirements.txt  # 依赖配置
├── Bangumi_Anime.md  # 生成的数据文件
├── SECURITY.md       # 安全政策
└── README.md         # 本说明文档
```

## 注意事项

### 网络请求

- 默认并发数设为 3，如需调整请设置环境变量：
  ```bash
  export CONCURRENT_REQUESTS=5
  ```
- 避免高频请求，间隔时间 ≥ 1 秒

### 数据安全

- Markdown 文件采用 UTF-8 编码
- 自动处理非法文件名字符
- 建议定期 commit 数据变更

### 异常处理

- 网络错误自动重试 3 次
- 日期解析失败时自动使用基准年份
- 封面 URL 自动补全协议头

## 贡献指南

### 代码贡献

1. Fork 本仓库
2. 创建功能分支
   ```bash
   git checkout -b feature/NewFeature
   ```
3. 提交代码变更
   ```bash
   git commit -m 'feat: Add awesome feature'
   ```
4. 推送分支
   ```bash
   git push origin feature/NewFeature
   ```
5. 创建 Pull Request

### 数据维护

- 通过 Review Pull Request 参与数据校验
- 在 Issue 中报告数据异常
- 建议使用 Discussion 讨论数据格式改进

## 开源协议

本项目采用 Apache 2.0 许可证 - 详见 LICENSE 文件

## 安全政策

如果发现任何安全漏洞，请查看我们的安全政策文档了解报告流程，我们将尽快响应处理。