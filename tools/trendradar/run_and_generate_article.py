# -*- coding: utf-8 -*-
"""
TrendRadar + 公众号文章生成 一键运行脚本
运行顺序: 抓取数据 -> 生成报告 -> 生成公众号文章 -> 生成日报索引页
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """执行命令并返回结果"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0


def main():
    print("🚀 开始运行 TrendRadar + 公众号文章生成")

    base_dir = Path(__file__).parent

    # 1. 运行 TrendRadar 主程序
    success = run_command(
        "python -m trendradar",
        "Step 1: 运行 TrendRadar 数据抓取和报告生成"
    )

    if not success:
        print("❌ TrendRadar 运行失败")
        sys.exit(1)

    # 2. 生成公众号文章
    article_generator_path = base_dir / "generate_wechat_article.py"
    if article_generator_path.exists():
        run_command(
            f"python {article_generator_path}",
            "Step 2: 生成公众号文章"
        )

    # 3. 生成日报索引页
    daily_index_path = base_dir / "generate_daily_index.py"
    if daily_index_path.exists():
        run_command(
            f"python {daily_index_path}",
            "Step 3: 生成日报索引页"
        )

    print("\n✅ 全部完成!")
    print("📄 公众号文章位置: output/articles/")
    print("📄 日报索引页: index.html")


if __name__ == "__main__":
    main()
