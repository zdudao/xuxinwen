# -*- coding: utf-8 -*-
"""
微信公众号文章索引页生成器
自动扫描 articles 文件夹，生成索引主页
"""

import os
import re
from pathlib import Path
from datetime import datetime
from trendradar.core import load_config
from trendradar.context import AppContext


class ArticleIndexGenerator:
    def __init__(self):
        self.config = load_config()
        self.ctx = AppContext(self.config)
        self.output_dir = Path("output")
        self.article_dir = self.output_dir / "articles"
        self.index_path = Path("G:/xinwen/index.html")

    def get_all_articles(self):
        """获取所有文章，按日期排序"""
        if not self.article_dir.exists():
            return []

        articles = []
        for f in self.article_dir.glob("*.html"):
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', f.name)
            if date_match:
                date_str = date_match.group(1)
                try:
                    article_date = datetime.strptime(date_str, "%Y-%m-%d")

                    title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', f.read_text(encoding="utf-8"))
                    title = title_match.group(1).strip() if title_match else f"老许聊实体 - {date_str}"

                    stats_match = re.search(r'共 (\d+) 条', f.read_text(encoding="utf-8"))
                    stats = stats_match.group(1) if stats_match else ""

                    articles.append({
                        "date": date_str,
                        "display_date": article_date.strftime("%Y年%m月%d日"),
                        "filename": f.name,
                        "title": title,
                        "stats": stats,
                        "path": f"../TrendRadar/output/articles/{f.name}"
                    })
                except ValueError:
                    continue

        articles.sort(key=lambda x: x["date"], reverse=True)
        return articles

    def generate_index_html(self, articles):
        """生成索引页HTML"""
        date_str = self.ctx.get_time().strftime("%Y年%m月%d日")

        article_items = ""
        for article in articles:
            article_items += f"""
        <div class="article-item">
            <div class="article-date">{article['display_date']}</div>
            <div class="article-content">
                <a href="{article['path']}" class="article-title" target="_blank">{article['title']}</a>
                <div class="article-stats">共 {article['stats']} 条</div>
            </div>
            <div class="article-arrow">→</div>
        </div>
"""

        if not article_items:
            article_items = """
        <div class="empty-state">
            <p>暂无文章</p>
            <p>运行 <code>python run_and_generate_article.py</code> 生成第一篇文章</p>
        </div>
"""

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>老许聊实体 - 每日行业资讯</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 40px;
        }}
        .header h1 {{
            color: white;
            font-size: 32px;
            margin-bottom: 10px;
            text-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }}
        .header p {{
            color: rgba(255,255,255,0.8);
            font-size: 16px;
        }}
        .articles-list {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            overflow: hidden;
        }}
        .article-item {{
            display: flex;
            align-items: center;
            padding: 20px 24px;
            border-bottom: 1px solid #eee;
            transition: background 0.2s;
        }}
        .article-item:last-child {{
            border-bottom: none;
        }}
        .article-item:hover {{
            background: #f8f9fa;
        }}
        .article-date {{
            flex: 0 0 120px;
            font-size: 14px;
            color: #666;
            font-weight: 500;
        }}
        .article-content {{
            flex: 1;
        }}
        .article-title {{
            color: #333;
            text-decoration: none;
            font-size: 16px;
            font-weight: 500;
            display: block;
            margin-bottom: 4px;
        }}
        .article-title:hover {{
            color: #667eea;
        }}
        .article-stats {{
            font-size: 12px;
            color: #999;
        }}
        .article-arrow {{
            color: #ccc;
            font-size: 20px;
            margin-left: 16px;
        }}
        .empty-state {{
            padding: 60px 40px;
            text-align: center;
            color: #666;
        }}
        .empty-state p {{
            margin-bottom: 10px;
        }}
        .empty-state code {{
            background: #f5f5f5;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 13px;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            color: rgba(255,255,255,0.7);
            font-size: 14px;
        }}
        .update-time {{
            text-align: center;
            color: rgba(255,255,255,0.6);
            font-size: 12px;
            margin-top: 20px;
        }}
        @media (max-width: 600px) {{
            .article-item {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .article-date {{
                margin-bottom: 8px;
            }}
            .article-arrow {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 老许聊实体</h1>
            <p>每日行业资讯 · AI智能分析</p>
        </div>

        <div class="articles-list">
{article_items}
        </div>

        <div class="update-time">
            最后更新: {date_str}
        </div>

        <div class="footer">
            <p>关注「老许聊实体」，每天五分钟，带你看透行业趋势</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def run(self):
        """运行生成器"""
        print("正在生成索引页...")

        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        articles = self.get_all_articles()
        print(f"找到 {len(articles)} 篇文章")

        html = self.generate_index_html(articles)

        with open(self.index_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"索引页已生成: {self.index_path}")
        return str(self.index_path)


def main():
    generator = ArticleIndexGenerator()
    generator.run()


if __name__ == "__main__":
    main()
