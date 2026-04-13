# 老许聊实体 - 每日行业资讯

> 专注实体商业资讯的自动化采集与推送系统

## 项目简介

本项目用于每日采集和展示实体商业领域的热点资讯，包括热榜新闻、RSS订阅、行业分析等内容。

## 系统架构

```
TrendRadar（数据采集）
    ↓ 生成日报
output/html/YYYY-MM-DD/HH-MM.html
    ↓ 手动复制
xuxinwen-static/
    ↓ GitHub Pages
https://zdudao.github.io/xuxinwen/
```

## 目录结构

```
.
├── index.html              # 首页索引
├── YYYY-MM-DD.html         # 当日日报
├── html/                   # 历史日报存档
│   └── YYYY-MM-DD/
│       └── HH-MM.html
├── wechat_YYYY-MM-DD.html  # 微信朋友圈文案
└── logo.jpg               # Logo
```

## 核心功能

### 1. 数据采集（TrendRadar）

- **热榜平台**：11个（今日头条、百度热搜、华尔街见闻、澎湃新闻、bilibili、财联社、凤凰网、贴吧、微博、抖音、知乎）
- **RSS订阅源**：14个（36氪、钛媒体、Hacker News等）
- **AI智能筛选**：自动分类和过滤

### 2. 报告生成

- HTML日报：包含热榜新闻、AI分析、行业洞察
- 微信文案：适合朋友圈分享的精简版本

### 3. 展示端（GitHub Pages）

- 静态网站，无需服务器
- 自动托管更新

## 快速开始

### 第一步：启动RSSHub

```bash
cd g:\dingyue\rsshub-local
pnpm install
pnpm run dev
```

RSSHub 启动后运行在 http://localhost:1200

### 第二步：运行TrendRadar

```bash
cd g:\dingyue\TrendRadar
python -m trendradar
```

### 第三步：复制日报到xuxinwen-static

将 `TrendRadar/output/html/YYYY-MM-DD/HH-MM.html` 复制到：
- `xuxinwen-static/YYYY-MM-DD.html`（当日日报）
- `xuxinwen-static/html/YYYY-MM-DD/HH-MM.html`（历史存档）

### 第四步：推送到GitHub

```bash
cd g:\dingyue\xuxinwen-static
git add .
git commit -m "更新日报：YYYY-MM-DD"
git push
```

## 每日工作流程

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 启动RSSHub | `cd rsshub-local && pnpm run dev` |
| 2 | 运行TrendRadar | `cd TrendRadar && python -m trendradar` |
| 3 | 复制日报文件 | 将HTML复制到xuxinwen-static |
| 4 | 修改标题 | 更新index.html中的当日标题 |
| 5 | 推送GitHub | 推送到origin/main |

## 内容规范

### 索引页标题（index.html）

使用标题党风格，吸引用户点击：

```
❌ 老许聊实体 - 每日行业资讯
✅ 虚报77亿!河南招商数据造假,程序员卖汉堡月入5万
```

### 日报页标题

格式：`老许聊实体 - MM-DD商业资讯`

### 微信朋友圈文案格式

```
老许聊实体—MM-DD

🔥 今日热点

- 新闻标题1
- 新闻标题2
- 新闻标题3

💡 洞察

一句话总结

🔗 完整报告

https://zdudao.github.io/xuxinwen/
```

## 配置文件说明

### TrendRadar配置（config/config.yaml）

| 配置项 | 说明 |
|--------|------|
| `ai_filter.min_score` | AI筛选分数阈值，0表示不过滤 |
| `hotlist.platforms` | 热榜平台列表 |
| `rss.feeds` | RSS订阅源配置 |

### 推送阈值建议

| 值 | 效果 |
|----|------|
| 0 | 显示所有AI分类为商业的内容 |
| 0.3 | 较低阈值，保留大部分内容 |
| 0.5 | 默认阈值（平衡） |
| 0.7 | 高阈值，只显示高相关度内容 |

## 常见问题

### Q: RSS订阅显示0条？

原因：AI筛选分数阈值过高
解决：将 `ai_filter.min_score` 设为 0

### Q: 推送失败？

原因：Git代理配置问题
解决：
```bash
git config --global --unset http.proxy
git config --global --unset https.proxy
```

### Q: 微信文案如何生成？

从日报中提取最热门的3-5条新闻，加上洞察总结即可

## 技术栈

- **数据采集**：Python + TrendRadar
- **RSS服务**：RSSHub
- **静态站点**：HTML + CSS + JavaScript
- **托管平台**：GitHub Pages

## 联系方式

- 抖音：168198020
- 微信：xuyang2946

## 许可证

AGPL-3.0
