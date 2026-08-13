# -*- coding: utf-8 -*-
"""
微信公众号文章生成器 (HTML格式)
直接从 TrendRadar HTML 报告提取内容，生成带外链和图片的公众号文章
支持自定义时间窗口过滤
"""

import os
import re
import json
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from trendradar.core import load_config
from trendradar.context import AppContext


class WeChatArticleGenerator:
    def __init__(self):
        self.config = load_config()
        self.ctx = AppContext(self.config)
        self.output_dir = Path("output")
        self.article_dir = self.output_dir / "articles"
        self.article_dir.mkdir(parents=True, exist_ok=True)
        self.image_cache = {}

        self.article_hour = 12
        self.time_window_hours = 24

    def get_time_window(self) -> Tuple[datetime, datetime]:
        """获取文章统计时间窗口
        返回: (窗口开始时间, 窗口结束时间)
        窗口: 前一天12:00 - 当天12:00
        """
        now = self.ctx.get_time()
        today_noon = now.replace(hour=self.article_hour, minute=0, second=0, microsecond=0)

        if now.hour < self.article_hour:
            end_time = today_noon
            start_time = (today_noon - timedelta(days=1))
        else:
            start_time = today_noon
            end_time = today_noon + timedelta(days=1)

        return start_time, end_time

    def parse_news_time(self, time_str: str) -> Optional[datetime]:
        """解析新闻时间字符串为datetime对象"""
        if not time_str:
            return None

        try:
            formats = [
                "%m-%d %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%d-%m-%Y %H:%M",
                "%H:%M",
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(time_str.strip(), fmt)
                except ValueError:
                    continue

            return None
        except Exception:
            return None

    def is_within_time_window(self, time_str: str) -> bool:
        """判断新闻时间是否在时间窗口内"""
        start_time, end_time = self.get_time_window()
        news_time = self.parse_news_time(time_str)

        if news_time is None:
            return True

        news_time = self.ctx.get_time().replace(
            month=news_time.month,
            day=news_time.day,
            hour=news_time.hour,
            minute=news_time.minute,
            second=0,
            microsecond=0
        )

        return start_time <= news_time <= end_time

    def get_latest_html_report(self):
        """获取最新的HTML报告路径"""
        latest_dir = self.output_dir / "html" / "latest"
        daily_report = latest_dir / "daily.html"

        if daily_report.exists():
            return daily_report

        date_str = self.ctx.format_date()
        date_dir = self.output_dir / "html" / date_str
        if date_dir.exists():
            html_files = list(date_dir.glob("*.html"))
            if html_files:
                return max(html_files, key=lambda p: p.stat().st_mtime)

        return None

    def extract_content_from_html(self, html_path):
        """从HTML报告提取内容"""
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        result = {
            "date": self.extract_date(content),
            "total_count": self.extract_total_count(content),
            "filtered_count": self.extract_filtered_count(content),
            "hot_topics": self.extract_hot_topics(content),
            "ai_analysis": self.extract_ai_analysis(content),
            "rss_section": self.extract_rss_section_with_urls(content),
            "time_window": self.get_time_window()
        }

        return result

    def extract_date(self, content):
        """提取报告日期"""
        match = re.search(r'<span class="info-value">(\d{2}-\d{2} \d{2}:\d{2})</span>', content)
        if match:
            return match.group(1)
        return datetime.now().strftime("%m-%d %H:%M")

    def extract_total_count(self, content):
        """提取抓取总数"""
        match = re.search(r'抓取总数.*?<span class="info-value">(\d+) 条</span>', content, re.DOTALL)
        if match:
            return match.group(1)
        return "0"

    def extract_filtered_count(self, content):
        """提取筛选结果"""
        match = re.search(r'筛选结果.*?<span class="info-value">(\d+) 条</span>', content, re.DOTALL)
        if match:
            return match.group(1)
        return "0"

    def extract_hot_topics(self, content):
        """提取热点话题"""
        topics = []

        word_groups = re.findall(r'<div class="word-group"[^>]*>(.*?)</div>\s*</div>\s*</div>', content, re.DOTALL)
        for group in word_groups[:5]:
            word_match = re.search(r'<div class="word-name">([^<]+)</div>', group)
            count_match = re.search(r'<div class="word-count[^"]*">(\d+) 条</div>', group)

            if word_match and count_match:
                word_name = word_match.group(1)
                count = count_match.group(1)

                items = []
                news_items = re.findall(
                    r'<div class="news-item[^>]*>.*?<div class="news-title"><a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>',
                    group, re.DOTALL
                )

                for url, title in news_items[:5]:
                    time_match = re.search(r'<span class="time-info">([^<]*)</span>', group)
                    time_str = time_match.group(1) if time_match else ""

                    if self.is_within_time_window(time_str):
                        items.append({
                            "title": title.strip(),
                            "url": url.strip(),
                            "time": time_str
                        })

                if items:
                    topics.append({
                        "category": word_name,
                        "count": str(len(items)),
                        "items": items
                    })

        return topics

    def extract_ai_analysis(self, content):
        """提取AI分析内容"""
        ai_blocks = []

        ai_section = re.search(r'<div class="ai-blocks-grid">(.*?)</div>\s*</div>\s*</div>', content, re.DOTALL)
        if not ai_section:
            return ai_blocks

        blocks_html = ai_section.group(1)

        parts = re.split(r'<div class="ai-block">', blocks_html)
        for part in parts[1:]:
            title_match = re.search(r'<div class="ai-block-title">([^<]+)</div>', part)
            content_match = re.search(r'<div class="ai-block-content">(.*?)</div>\s*</div>', part, re.DOTALL)

            if title_match and content_match:
                title = title_match.group(1).strip()
                content_html = content_match.group(1)

                clean_content = re.sub(r'<br\s*/?>', '\n', content_html)
                clean_content = re.sub(r'<[^>]+>', '', clean_content)
                clean_content = re.sub(r'\n+', '\n', clean_content).strip()

                ai_blocks.append({
                    "title": title,
                    "content": clean_content
                })

        return ai_blocks

    def extract_rss_section_with_urls(self, content):
        """提取RSS内容，包含URL"""
        rss_items = []

        item_pattern = r'<div class="rss-item">.*?<div class="rss-meta">.*?<span class="rss-time">([^<]+)</span>.*?<span class="rss-author">([^<]+)</span>.*?<div class="rss-title"><a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
        matches = re.findall(item_pattern, content, re.DOTALL)

        for time, author, url, title in matches[:8]:
            time_str = time.strip()
            if self.is_within_time_window(time_str):
                rss_items.append({
                    "time": time_str,
                    "author": author.strip(),
                    "title": title.strip(),
                    "url": url.strip()
                })

        return rss_items

    async def fetch_image_for_url(self, session, url, title):
        """尝试获取新闻页面的图片"""
        try:
            if url in self.image_cache:
                return self.image_cache[url]

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    html = await response.text()

                    og_image = re.search(r'<meta property="og:image" content="([^"]*)"', html)
                    if og_image:
                        img_url = og_image.group(1)
                        self.image_cache[url] = img_url
                        return img_url

                    twitter_image = re.search(r'<meta name="twitter:image" content="([^"]*)"', html)
                    if twitter_image:
                        img_url = twitter_image.group(1)
                        self.image_cache[url] = img_url
                        return img_url

                    first_img = re.search(r'<img[^>]*src="([^"]*)"[^>]*>', html)
                    if first_img:
                        img_url = first_img.group(1)
                        if img_url.startswith('http'):
                            self.image_cache[url] = img_url
                            return img_url

            self.image_cache[url] = None
            return None
        except Exception:
            self.image_cache[url] = None
            return None

    async def fetch_images_for_items(self, items):
        """并发获取多个URL的图片"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for item in items:
                if item.get('url'):
                    tasks.append(self.fetch_image_for_url(session, item['url'], item.get('title', '')))

            await asyncio.gather(*tasks, return_exceptions=True)

    def get_image_for_item(self, url):
        """获取指定URL的图片"""
        return self.image_cache.get(url)

    def generate_html_article(self, data):
        """生成HTML格式文章"""
        date_str = self.ctx.get_time().strftime("%Y年%m月%d日")
        start_time, end_time = data["time_window"]
        window_str = f"{start_time.strftime('%m-%d %H:%M')} - {end_time.strftime('%m-%d %H:%M')}"

        total_items = sum(len(topic['items']) for topic in data["hot_topics"])
        total_items += len(data["rss_section"])

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>老许聊实体 - {date_str}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #fafafa;
            color: #333;
            line-height: 1.8;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px;
            color: white;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 24px;
        }}
        .header .date {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .header .stats {{
            font-size: 12px;
            margin-top: 10px;
            opacity: 0.8;
        }}
        .intro {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .section-title {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
            color: #333;
        }}
        .topic-category {{
            font-size: 16px;
            font-weight: bold;
            color: #667eea;
            margin: 15px 0 10px 0;
        }}
        .topic-category span {{
            font-size: 12px;
            color: #999;
            font-weight: normal;
            margin-left: 8px;
        }}
        .news-item {{
            margin-bottom: 12px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 3px solid #667eea;
        }}
        .news-item a {{
            color: #333;
            text-decoration: none;
            display: block;
        }}
        .news-item a:hover {{
            color: #667eea;
        }}
        .news-item img {{
            max-width: 100%;
            max-height: 200px;
            border-radius: 6px;
            margin: 8px 0;
        }}
        .news-item .time {{
            font-size: 11px;
            color: #999;
            margin-top: 4px;
        }}
        .rss-item {{
            margin-bottom: 15px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        .rss-item .meta {{
            font-size: 12px;
            color: #999;
            margin-bottom: 5px;
        }}
        .rss-item a {{
            color: #333;
            text-decoration: none;
            font-weight: 500;
        }}
        .rss-item a:hover {{
            color: #667eea;
        }}
        .rss-item img {{
            max-width: 100%;
            max-height: 150px;
            border-radius: 6px;
            margin-top: 8px;
        }}
        .ai-section {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .ai-block {{
            margin-bottom: 20px;
        }}
        .ai-block-title {{
            font-size: 16px;
            font-weight: bold;
            color: #764ba2;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px dashed #ddd;
        }}
        .ai-block-content {{
            color: #555;
            line-height: 1.8;
            white-space: pre-wrap;
        }}
        .footer {{
            text-align: center;
            padding: 30px;
            color: #999;
            font-size: 14px;
        }}
        .disclaimer {{
            background: #fff3cd;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            font-size: 13px;
            color: #856404;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 老许聊实体 - 每日行业资讯</h1>
        <div class="date">{date_str} · 午间汇总</div>
        <div class="stats">统计周期: {window_str} | 共 {total_items} 条</div>
    </div>

    <div class="intro">
        <p>各位实体老板、行业同仁们好，这里是老许。</p>
        <p>今天为大家带来最新的行业资讯解读，帮助大家把握市场脉搏。</p>
        <p><em>本期统计周期：{window_str}</em></p>
    </div>
"""

        if data["hot_topics"]:
            html += """
    <div class="section">
        <div class="section-title">🔥 今日热点</div>
"""
            for topic in data["hot_topics"]:
                html += f"""
        <div class="topic-category">{topic['category']}<span>({topic['count']}条)</span></div>
"""
                for item in topic['items']:
                    img_url = self.get_image_for_item(item['url'])
                    img_html = f'<img src="{img_url}" alt="配图">' if img_url else ''
                    time_html = f'<div class="time">{item.get("time", "")}</div>' if item.get("time") else ''
                    html += f"""
        <div class="news-item">
            <a href="{item['url']}" target="_blank">{item['title']}</a>
            {time_html}
            {img_html}
        </div>
"""

            html += """
    </div>
"""

        if data["rss_section"]:
            html += """
    <div class="section">
        <div class="section-title">📰 行业资讯</div>
"""
            for item in data["rss_section"]:
                img_url = self.get_image_for_item(item['url'])
                img_html = f'<img src="{img_url}" alt="配图">' if img_url else ''
                html += f"""
        <div class="rss-item">
            <div class="meta">{item['author']} · {item['time']}</div>
            <a href="{item['url']}" target="_blank">{item['title']}</a>
            {img_html}
        </div>
"""

            html += """
    </div>
"""

        if data["ai_analysis"]:
            html += """
    <div class="ai-section">
        <div class="section-title">💡 老许解读</div>
"""
            for block in data["ai_analysis"]:
                content = re.sub(r'^' + re.escape(block['title']) + r'\s*', '', block['content'])
                html += f"""
        <div class="ai-block">
            <div class="ai-block-title">{block['title']}</div>
            <div class="ai-block-content">{content}</div>
        </div>
"""

            html += """
    </div>
"""

        html += """
    <div class="footer">
        <p>关注「老许聊实体」，每天五分钟，带你看透行业趋势。</p>
        <div class="disclaimer">
            免责声明：本文仅供参考，不构成投资建议。实体经营有风险，决策需谨慎。
        </div>
    </div>
</body>
</html>
"""
        return html

    def save_article(self, article_content, is_html=True):
        """保存文章"""
        now = self.ctx.get_time()
        date_str = now.strftime("%Y-%m-%d")

        if is_html:
            filename = f"wechat_article_{date_str}.html"
        else:
            filename = f"wechat_article_{date_str}.txt"

        filepath = self.article_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(article_content)

        return str(filepath)

    async def run_async(self):
        """异步运行生成流程"""
        start_time, end_time = self.get_time_window()
        print(f"开始生成公众号文章...")
        print(f"统计周期: {start_time.strftime('%m-%d %H:%M')} - {end_time.strftime('%m-%d %H:%M')}")

        html_path = self.get_latest_html_report()
        if not html_path:
            print("未找到HTML报告")
            return None

        print(f"读取报告: {html_path}")

        data = self.extract_content_from_html(html_path)

        all_items = []
        for topic in data["hot_topics"]:
            all_items.extend(topic["items"])
        for item in data["rss_section"]:
            all_items.append({"url": item["url"], "title": item["title"]})

        if all_items:
            print(f"正在获取 {len(all_items)} 个新闻页面的图片...")
            await self.fetch_images_for_items(all_items)

        total_filtered = sum(len(topic['items']) for topic in data["hot_topics"]) + len(data["rss_section"])
        print(f"提取到 {len(data['hot_topics'])} 个分类（过滤后 {total_filtered} 条），{len(data['ai_analysis'])} 个AI分析块")

        html_article = self.generate_html_article(data)
        filepath = self.save_article(html_article, is_html=True)

        print(f"HTML文章已保存: {filepath}")
        return filepath

    def run(self):
        """运行生成流程"""
        return asyncio.run(self.run_async())


def main():
    generator = WeChatArticleGenerator()
    filepath = generator.run()
    if filepath:
        print(f"\n✅ 公众号文章生成完成!")
        print(f"📄 文件位置: {filepath}")
    else:
        print("❌ 文章生成失败")


if __name__ == "__main__":
    main()
