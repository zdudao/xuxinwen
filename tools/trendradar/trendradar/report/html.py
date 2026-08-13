# coding=utf-8
"""
HTML 报告渲染模块

提供 HTML 格式的热点新闻报告生成功能
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
import os

from trendradar.report.helpers import html_escape
from trendradar.utils.time import convert_time_for_display
from trendradar.ai.formatter import render_ai_analysis_html_rich


def render_html_content(
    report_data: Dict,
    total_titles: int,
    mode: str = "daily",
    update_info: Optional[Dict] = None,
    *,
    region_order: Optional[List[str]] = None,
    get_time_func: Optional[Callable[[], datetime]] = None,
    rss_items: Optional[List[Dict]] = None,
    rss_new_items: Optional[List[Dict]] = None,
    display_mode: str = "keyword",
    standalone_data: Optional[Dict] = None,
    ai_analysis: Optional[Any] = None,
    show_new_section: bool = True,
) -> str:
    """渲染HTML内容

    Args:
        report_data: 报告数据字典，包含 stats, new_titles, failed_ids, total_new_count
        total_titles: 新闻总数
        mode: 报告模式 ("daily", "current", "incremental")
        update_info: 更新信息（可选）
        region_order: 区域显示顺序列表
        get_time_func: 获取当前时间的函数（可选，默认使用 datetime.now）
        rss_items: RSS 统计条目列表（可选）
        rss_new_items: RSS 新增条目列表（可选）
        display_mode: 显示模式 ("keyword"=按关键词分组, "platform"=按平台分组)
        standalone_data: 独立展示区数据（可选），包含 platforms 和 rss_feeds
        ai_analysis: AI 分析结果对象（可选），AIAnalysisResult 实例
        show_new_section: 是否显示新增热点区域

    Returns:
        渲染后的 HTML 字符串
    """
    # 默认区域顺序
    default_region_order = ["hotlist", "rss", "new_items", "standalone", "ai_analysis"]
    if region_order is None:
        region_order = default_region_order

    # 读取模板文件
    template_path = os.path.join(os.path.dirname(__file__), '..', '..', 'output', 'html', 'template.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # 使用提供的时间函数或默认 datetime.now
    if get_time_func:
        now = get_time_func()
    else:
        now = datetime.now()

    # 计算筛选后的热点新闻数量
    hot_news_count = sum(len(stat["titles"]) for stat in report_data["stats"])

    # 处理报告类型显示
    if mode == "current":
        report_type = "当前榜单"
    elif mode == "incremental":
        report_type = "增量分析"
    else:
        report_type = "全天汇总"

    # 生成内容部分
    content_html = """
                <div class="search-bar">
                    <input type="text" class="search-input" placeholder="搜索新闻标题..." oninput="handleSearch(this.value)">
                </div>"""

    # 处理失败ID错误信息
    if report_data["failed_ids"]:
        content_html += """
                <div class="error-section">
                    <div class="error-title">⚠️ 请求失败的平台</div>
                    <ul class="error-list">"""
        for id_value in report_data["failed_ids"]:
            content_html += f'<li class="error-item">{html_escape(id_value)}</li>'
        content_html += """
                    </ul>
                </div>"""

    # 生成热点词汇统计部分的HTML
    stats_html = ""
    tab_bar_html = ""
    if report_data["stats"]:
        total_count = len(report_data["stats"])

        # 生成 Tab 栏 HTML
        tab_bar_html = '<div class="tab-bar">'
        for tab_i, tab_stat in enumerate(report_data["stats"]):
            escaped_tab_word = html_escape(tab_stat["word"])
            tab_count = tab_stat["count"]
            tab_bar_html += f'<button class="tab-btn" data-tab-index="{tab_i}">{escaped_tab_word}<span class="tab-count">{tab_count}</span></button>'
        tab_bar_html += '<button class="tab-btn" data-tab-index="all">全部</button>'
        tab_bar_html += '</div>'

        for i, stat in enumerate(report_data["stats"], 1):
            count = stat["count"]

            # 确定热度等级
            if count >= 10:
                count_class = "hot"
            elif count >= 5:
                count_class = "warm"
            else:
                count_class = ""

            escaped_word = html_escape(stat["word"])

            stats_html += f"""
                <div class="word-group" data-tab-index="{i - 1}">
                    <div class="word-header">
                        <div class="word-info">
                            <div class="word-name">{escaped_word}</div>
                            <div class="word-count {count_class}">{count} 条</div>
                        </div>
                        <div class="word-index"><span class="collapse-icon">▼</span>{i}/{total_count}</div>
                    </div>"""

            # 处理每个词组下的新闻标题，给每条新闻标上序号
            for j, title_data in enumerate(stat["titles"], 1):
                is_new = title_data.get("is_new", False)
                new_class = "new" if is_new else ""

                stats_html += f"""
                    <div class="news-item {new_class}">
                        <div class="news-number"><span class="num-text">{j}</span><span class="copy-icon">📋</span></div>
                        <div class="news-content">
                            <div class="news-header">"""

                # 根据 display_mode 决定显示来源还是关键词
                if display_mode == "keyword":
                    # keyword 模式：显示来源
                    stats_html += f'<span class="source-name">{html_escape(title_data["source_name"])}</span>'
                else:
                    # platform 模式：显示关键词
                    matched_keyword = title_data.get("matched_keyword", "")
                    if matched_keyword:
                        stats_html += f'<span class="keyword-tag">[{html_escape(matched_keyword)}]</span>'

                # 处理排名显示
                ranks = title_data.get("ranks", [])
                if ranks:
                    min_rank = min(ranks)
                    max_rank = max(ranks)
                    rank_threshold = title_data.get("rank_threshold", 10)

                    # 确定排名等级
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= rank_threshold:
                        rank_class = "high"
                    else:
                        rank_class = ""

                    if min_rank == max_rank:
                        rank_text = str(min_rank)
                    else:
                        rank_text = f"{min_rank}-{max_rank}"

                    stats_html += f'<span class="rank-num {rank_class}">{rank_text}</span>'

                # 处理时间显示
                time_display = title_data.get("time_display", "")
                if time_display:
                    # 简化时间显示格式，将波浪线替换为~
                    simplified_time = (
                        time_display.replace(" ~ ", "~")
                        .replace("[", "")
                        .replace("]", "")
                    )
                    stats_html += (
                        f'<span class="time-info">{html_escape(simplified_time)}</span>'
                    )

                # 处理出现次数
                count_info = title_data.get("count", 1)
                if count_info > 1:
                    stats_html += f'<span class="count-info">{count_info}次</span>'

                stats_html += """
                            </div>"""

                # 处理标题和链接
                escaped_title = html_escape(title_data["title"])
                link_url = title_data.get("mobile_url") or title_data.get("url", "")

                # 生成摘要（使用标题的前80个字符）
                summary = html_escape(title_data["title"])[:80] + "..." if len(title_data["title"]) > 80 else html_escape(title_data["title"])
                
                # 分类和平台信息
                category = html_escape(stat["word"])
                platform = html_escape(title_data["source_name"])

                # 生成标题和链接
                if link_url:
                    escaped_url = html_escape(link_url)
                    title_html = f'<a href="{escaped_url}" target="_blank" class="news-link">{escaped_title}</a>'
                else:
                    title_html = escaped_title

                stats_html += f"""
                            <div class="news-title">
                                {title_html}
                            </div>
                            <div class="news-summary">{summary}</div>
                            <div class="news-tags">
                                <span class="news-tag">{category}</span>
                                <span class="news-tag">{platform}</span>
                            </div>
                        </div>
                    </div>"""

            stats_html += """
                </div>"""

    # 给热榜统计添加外层包装
    if stats_html:
        stats_html = f"""
                <div class="hotlist-section">{tab_bar_html}{stats_html}
                </div>"""

    # 生成新增新闻区域的HTML
    new_titles_html = ""
    if show_new_section and report_data["new_titles"]:
        new_titles_html += f"""
                <div class="new-section">
                    <h2 class="new-section-title">新增热点</h2>
                    <div class="new-sources-grid">"""

        # 按来源分组
        sources = {}
        for item in report_data["new_titles"]:
            source = item["source_name"]
            if source not in sources:
                sources[source] = []
            sources[source].append(item)

        # 生成每个来源的新闻
        for source, items in sources.items():
            escaped_source = html_escape(source)
            new_titles_html += f"""
                    <div class="new-source-group">
                        <h3 class="new-source-title">{escaped_source}</h3>"""

            for i, item in enumerate(items, 1):
                escaped_title = html_escape(item["title"])
                link_url = item.get("mobile_url") or item.get("url", "")

                # 处理排名显示
                ranks = item.get("ranks", [])
                rank_html = ""
                if ranks:
                    min_rank = min(ranks)
                    max_rank = max(ranks)
                    rank_threshold = item.get("rank_threshold", 10)

                    # 确定排名等级
                    if min_rank <= 3:
                        rank_class = "top"
                    elif min_rank <= rank_threshold:
                        rank_class = "high"
                    else:
                        rank_class = ""

                    if min_rank == max_rank:
                        rank_text = str(min_rank)
                    else:
                        rank_text = f"{min_rank}-{max_rank}"

                    rank_html = f'<div class="new-item-rank {rank_class}">{rank_text}</div>'

                # 生成标题和链接
                if link_url:
                    escaped_url = html_escape(link_url)
                    title_html = f'<a href="{escaped_url}" target="_blank">{escaped_title}</a>'
                else:
                    title_html = escaped_title

                new_titles_html += f"""
                        <div class="new-item">
                            <div class="new-item-number">{i}</div>
                            {rank_html}
                            <div class="new-item-content">
                                <div class="new-item-title">{title_html}</div>
                            </div>
                        </div>"""

            new_titles_html += """
                    </div>"""

        new_titles_html += """
                    </div>
                </div>"""

    # 生成 RSS 订阅内容的HTML
    rss_html = ""
    if rss_items:
        # 检查数据格式：旧格式有 "entries"，新格式有 "titles"
        has_old_format = any("entries" in feed for feed in rss_items)
        
        if has_old_format:
            # 旧格式：按 feed 分组
            rss_html += f"""
                <div class="rss-section section-divider">
                    <div class="rss-section-header">
                        <h2 class="rss-section-title">RSS 订阅</h2>
                        <span class="rss-section-count">{len(rss_items)} 个源</span>
                    </div>
                    <div class="rss-feeds-grid">"""

            for feed in rss_items:
                feed_name = feed.get("feed_name", "未知源")
                escaped_feed_name = html_escape(feed_name)
                feed_entries = feed.get("entries", [])

                rss_html += f"""
                    <div class="feed-group">
                        <div class="feed-header">
                            <h3 class="feed-name">{escaped_feed_name}</h3>
                            <span class="feed-count">{len(feed_entries)} 条</span>
                        </div>"""

                for entry in feed_entries:
                    title = entry.get("title", "无标题")
                    link = entry.get("link", "")
                    published = entry.get("published", "")
                    author = entry.get("author", "")
                    summary = entry.get("summary", "")

                    escaped_title = html_escape(title)
                    escaped_link = html_escape(link)
                    escaped_published = html_escape(published)
                    escaped_author = html_escape(author)
                    escaped_summary = html_escape(summary)

                    rss_html += f"""
                        <div class="rss-item">
                            <div class="rss-meta">
                                <span class="rss-time">{escaped_published}</span>
                                <span class="rss-author">{escaped_author}</span>
                            </div>
                            <div class="rss-title">
                                <a href="{escaped_link}" target="_blank" class="rss-link">{escaped_title}</a>
                            </div>
                            <div class="rss-summary">{escaped_summary}</div>
                        </div>"""

                rss_html += """
                    </div>"""

            rss_html += """
                    </div>
                </div>"""
        else:
            # 新格式：按 RSS 源分组（count_rss_frequency 返回的格式）
            # 将相同 source_name 的条目合并到同一个 feed 下
            from collections import defaultdict
            feeds_map = defaultdict(list)
            for keyword_group in rss_items:
                for item in keyword_group.get("titles", []):
                    source_name = item.get("source_name", "未知源")
                    feeds_map[source_name].append(item)
            
            rss_html += f"""
                <div class="rss-section section-divider">
                    <div class="rss-section-header">
                        <h2 class="rss-section-title">RSS 订阅</h2>
                        <span class="rss-section-count">{len(feeds_map)} 个源</span>
                    </div>
                    <div class="rss-feeds-grid">"""

            for feed_name, entries in feeds_map.items():
                escaped_feed_name = html_escape(feed_name)
                rss_html += f"""
                    <div class="feed-group">
                        <div class="feed-header">
                            <h3 class="feed-name">{escaped_feed_name}</h3>
                            <span class="feed-count">{len(entries)} 条</span>
                        </div>"""

                for entry in entries:
                    title = entry.get("title", "无标题")
                    link = entry.get("url", "") or entry.get("link", "")
                    published = entry.get("time_display", "") or entry.get("published_at", "")
                    author = entry.get("author", "")
                    summary = entry.get("summary", "")

                    escaped_title = html_escape(title)
                    escaped_link = html_escape(link)
                    escaped_published = html_escape(published)
                    escaped_author = html_escape(author)
                    escaped_summary = html_escape(summary)

                    rss_html += f"""
                        <div class="rss-item">
                            <div class="rss-meta">
                                <span class="rss-time">{escaped_published}</span>
                                <span class="rss-author">{escaped_author}</span>
                            </div>
                            <div class="rss-title">
                                <a href="{escaped_link}" target="_blank" class="rss-link">{escaped_title}</a>
                            </div>
                            <div class="rss-summary">{escaped_summary}</div>
                        </div>"""

                rss_html += """
                    </div>"""

            rss_html += """
                    </div>
                </div>"""

    # 生成独立展示区的HTML (已禁用)
    standalone_html = ""

    # 生成 AI 分析结果的HTML
    ai_html = ""
    if ai_analysis:
        ai_html += f"""
                <div class="ai-section section-divider">
                    <div class="ai-section-header">
                        <h2 class="ai-section-title">AI 分析</h2>
                        <span class="ai-section-badge">GPT</span>
                    </div>
                    <div class="ai-blocks-grid">"""

        # 使用 AI 分析格式化器
        ai_html += render_ai_analysis_html_rich(ai_analysis)

        ai_html += """
                    </div>
                </div>"""

    # 按区域顺序组装内容
    for region in region_order:
        if region == "hotlist" and stats_html:
            content_html += stats_html
        elif region == "rss" and rss_html:
            content_html += rss_html
        elif region == "new_items" and new_titles_html:
            content_html += new_titles_html
        elif region == "standalone" and standalone_html:
            content_html += standalone_html
        elif region == "ai_analysis" and ai_html:
            content_html += ai_html

    # 替换模板中的占位符
    html = template.replace("{{date}}", now.strftime("%Y-%m-%d"))
    html = html.replace("{{content}}", content_html)
    html = html.replace("{{report_type}}", report_type)
    html = html.replace("{{total_count}}", str(total_titles))
    html = html.replace("{{filter_count}}", str(hot_news_count))
    html = html.replace("{{news_date}}", now.strftime("%m-%d %H:%M"))
    html = html.replace("{{full_date}}", now.strftime("%Y-%m-%d %H:%M:%S"))

    # 添加JavaScript代码
    html += """
        <script>
            // ===== 浏览器增强功能 =====

            function toggleWideMode() {
                document.body.classList.toggle('wide-mode');
                var isWide = document.body.classList.contains('wide-mode');
                try { localStorage.setItem('trendradar-wide-mode', isWide ? '1' : '0'); } catch(e) {}
                var btn = document.querySelector('.toggle-wide-btn');
                if (btn) btn.textContent = isWide ? '⊡' : '⛶';
                initTabVisibility();
                initCollapseVisibility();
                initStandaloneTabVisibility();
            }

            function toggleDarkMode() {
                var isDark = document.body.classList.toggle('dark-mode');
                try { localStorage.setItem('trendradar-dark-mode', isDark ? '1' : '0'); } catch(e) {}
                var btn = document.querySelector('.toggle-dark-btn');
                if (btn) btn.textContent = isDark ? '☀' : '☽';
            }

            function initTabs() {
                var tabBar = document.querySelector('.tab-bar');
                if (!tabBar) return;
                var tabs = tabBar.querySelectorAll('.tab-btn');
                var groups = document.querySelectorAll('.word-group[data-tab-index]');
                initTabVisibility();

                function activateTab(index) {
                    tabs.forEach(function(t) { t.classList.remove('active'); });
                    if (index === 'all') {
                        var allBtn = tabBar.querySelector('[data-tab-index="all"]');
                        if (allBtn) allBtn.classList.add('active');
                        groups.forEach(function(g) { g.style.display = ''; });
                        try { history.replaceState(null, '', '#all'); } catch(e) {}
                        return;
                    }
                    var idx = parseInt(index);
                    tabs.forEach(function(t) {
                        if (parseInt(t.dataset.tabIndex) === idx) t.classList.add('active');
                    });
                    if (document.body.classList.contains('wide-mode') && !tabBar.classList.contains('tab-hidden')) {
                        groups.forEach(function(g) {
                            g.style.display = (parseInt(g.dataset.tabIndex) === idx) ? '' : 'none';
                        });
                    }
                    try { history.replaceState(null, '', '#tab-' + idx); } catch(e) {}
                }

                tabs.forEach(function(tab) {
                    tab.addEventListener('click', function() {
                        var idx = tab.dataset.tabIndex;
                        activateTab(idx === 'all' ? 'all' : parseInt(idx));
                    });
                });

                tabBar.addEventListener('keydown', function(e) {
                    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                        var tabsArr = Array.from(tabs);
                        var ci = tabsArr.findIndex(function(t) { return t.classList.contains('active'); });
                        var dir = e.key === 'ArrowRight' ? 1 : -1;
                        var ni = Math.max(0, Math.min(tabsArr.length - 1, ci + dir));
                        var nt = tabsArr[ni];
                        activateTab(nt.dataset.tabIndex === 'all' ? 'all' : parseInt(nt.dataset.tabIndex));
                        nt.focus();
                        e.preventDefault();
                    }
                });

                var hash = window.location.hash;
                if (hash === '#all') { activateTab('all'); }
                else if (hash.indexOf('#tab-') === 0) { activateTab(parseInt(hash.replace('#tab-', ''))); }
                else { activateTab(0); }
            }

            function initTabVisibility() {
                var tabBar = document.querySelector('.tab-bar');
                if (!tabBar) return;
                var groups = document.querySelectorAll('.word-group[data-tab-index]');
                var isWide = document.body.classList.contains('wide-mode');
                if (!isWide || groups.length <= 2) {
                    tabBar.classList.add('tab-hidden');
                    groups.forEach(function(g) { g.style.display = ''; });
                } else {
                    tabBar.classList.remove('tab-hidden');
                    var activeTab = tabBar.querySelector('.tab-btn.active');
                    if (activeTab) { activeTab.click(); }
                    else {
                        var firstTab = tabBar.querySelector('.tab-btn');
                        if (firstTab) firstTab.click();
                    }
                }
            }

            function handleSearch(query) {
                query = query.toLowerCase();
                document.querySelectorAll('.news-item').forEach(function(item) {
                    var title = (item.querySelector('.news-title') || {}).textContent || '';
                    item.style.display = (!query || title.toLowerCase().indexOf(query) !== -1) ? '' : 'none';
                });
                document.querySelectorAll('.rss-item').forEach(function(item) {
                    var title = (item.querySelector('.rss-title') || {}).textContent || '';
                    item.style.display = (!query || title.toLowerCase().indexOf(query) !== -1) ? '' : 'none';
                });
            }

            function initBackToTop() {
                var fabBar = document.querySelector('.fab-bar');
                if (!fabBar) return;
                window.addEventListener('scroll', function() {
                    fabBar.classList.toggle('visible', window.scrollY > 300);
                });
            }

            function initCollapse() {
                document.querySelectorAll('.word-header').forEach(function(header) {
                    header.addEventListener('click', function() {
                        var tabBar = document.querySelector('.tab-bar');
                        if (document.body.classList.contains('wide-mode') && tabBar && !tabBar.classList.contains('tab-hidden')) return;
                        var group = header.closest('.word-group');
                        if (group) group.classList.toggle('collapsed');
                    });
                });
                initCollapseVisibility();
            }

            function initCollapseVisibility() {
                var headers = document.querySelectorAll('.word-header');
                var tabBar = document.querySelector('.tab-bar');
                var isTabMode = document.body.classList.contains('wide-mode') && tabBar && !tabBar.classList.contains('tab-hidden');
                headers.forEach(function(h) {
                    if (isTabMode) { h.classList.remove('collapsible'); }
                    else { h.classList.add('collapsible'); }
                });
                if (isTabMode) {
                    document.querySelectorAll('.word-group.collapsed').forEach(function(g) {
                        g.classList.remove('collapsed');
                    });
                }
            }

            // 独立展示区 Tab 切换
            function initStandaloneTabs() {
                var tabBar = document.querySelector('.standalone-tab-bar');
                if (!tabBar) return;
                var groups = document.querySelectorAll('.standalone-group[data-standalone-tab]');
                var btns = tabBar.querySelectorAll('.tab-btn[data-standalone-tab]');

                function activateStandaloneTab(val) {
                    btns.forEach(function(b) {
                        var bVal = b.getAttribute('data-standalone-tab');
                        b.classList.toggle('active', bVal === String(val));
                    });
                    groups.forEach(function(g) {
                        var gVal = g.getAttribute('data-standalone-tab');
                        g.style.display = (val === 'all' || gVal === String(val)) ? '' : 'none';
                    });
                }

                btns.forEach(function(btn) {
                    btn.addEventListener('click', function() {
                        activateStandaloneTab(btn.getAttribute('data-standalone-tab'));
                    });
                });

                // 初始状态
                initStandaloneTabVisibility();
            }

            function initStandaloneTabVisibility() {
                var tabBar = document.querySelector('.standalone-tab-bar');
                if (!tabBar) return;
                var groups = document.querySelectorAll('.standalone-group[data-standalone-tab]');
                var isWide = document.body.classList.contains('wide-mode');
                if (!isWide || groups.length <= 1) {
                    tabBar.classList.add('tab-hidden');
                    groups.forEach(function(g) { g.style.display = ''; });
                } else {
                    tabBar.classList.remove('tab-hidden');
                    var activeBtn = tabBar.querySelector('.tab-btn.active');
                    if (activeBtn) activeBtn.click();
                    else { var first = tabBar.querySelector('.tab-btn'); if (first) first.click(); }
                }
            }

            // ===== 截图功能 =====

            async function saveAsImage() {
                const button = event.target;
                const originalText = button.textContent;

                try {
                    button.textContent = '保存中...';
                    button.disabled = true;

                    // 准备截图状态
                    var screenshotState = prepareForScreenshot();

                    // 隐藏保存按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 等待DOM更新
                    await new Promise(resolve => setTimeout(resolve, 100));

                    // 使用html2canvas截取整个页面
                    const container = document.querySelector('.container');
                    const canvas = await html2canvas(container, {
                        backgroundColor: '#ffffff',
                        scale: 1.5,
                        useCORS: true,
                        allowTaint: true
                    });

                    // 恢复页面状态
                    buttons.style.visibility = 'visible';
                    restoreAfterScreenshot(screenshotState);

                    // 保存图片
                    const link = document.createElement('a');
                    link.download = '老许聊实体-' + new Date().toISOString().slice(0,10) + '.png';
                    link.href = canvas.toDataURL('image/png');
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    button.textContent = '保存成功!';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    restoreAfterScreenshot(screenshotState);
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            }

            async function saveAsMultipleImages() {
                const button = event.target;
                const originalText = button.textContent;

                try {
                    button.textContent = '保存中...';
                    button.disabled = true;

                    const groups = document.querySelectorAll('.word-group');
                    const images = [];

                    for (let i = 0; i < groups.length; i++) {
                        const group = groups[i];
                        const groupName = group.querySelector('.word-name').textContent;

                        // 准备截图状态
                        var screenshotState = prepareForScreenshot();

                        // 隐藏保存按钮
                        const buttons = document.querySelector('.save-buttons');
                        buttons.style.visibility = 'hidden';

                        // 滚动到当前组
                        group.scrollIntoView({ behavior: 'smooth' });
                        await new Promise(resolve => setTimeout(resolve, 500));

                        // 截取当前组
                        const canvas = await html2canvas(group, {
                            backgroundColor: '#ffffff',
                            scale: 1.5,
                            useCORS: true,
                            allowTaint: true
                        });

                        // 恢复页面状态
                        buttons.style.visibility = 'visible';
                        restoreAfterScreenshot(screenshotState);

                        // 保存图片
                        const link = document.createElement('a');
                        link.download = `老许聊实体-${new Date().toISOString().slice(0,10)}-${i+1}-${groupName}.png`;
                        link.href = canvas.toDataURL('image/png');
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        await new Promise(resolve => setTimeout(resolve, 1000));
                    }

                    button.textContent = '保存成功!';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    restoreAfterScreenshot(screenshotState);
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            }

            function prepareForScreenshot() {
                var state = {
                    collapsed: [],
                    wideMode: document.body.classList.contains('wide-mode')
                };

                // 展开所有折叠的组
                var collapsedGroups = document.querySelectorAll('.word-group.collapsed');
                collapsedGroups.forEach(function(group) {
                    state.collapsed.push(group);
                    group.classList.remove('collapsed');
                });

                // 切换到窄屏模式以确保内容完整
                if (state.wideMode) {
                    document.body.classList.remove('wide-mode');
                }

                return state;
            }

            function restoreAfterScreenshot(state) {
                // 恢复折叠状态
                state.collapsed.forEach(function(group) {
                    group.classList.add('collapsed');
                });

                // 恢复宽屏模式
                if (state.wideMode) {
                    document.body.classList.add('wide-mode');
                }
            }

            // 初始化功能
            document.addEventListener('DOMContentLoaded', function() {
                // 恢复用户偏好设置
                try {
                    if (localStorage.getItem('trendradar-wide-mode') === '1') {
                        document.body.classList.add('wide-mode');
                        var btn = document.querySelector('.toggle-wide-btn');
                        if (btn) btn.textContent = '⊡';
                    }
                    if (localStorage.getItem('trendradar-dark-mode') === '1') {
                        document.body.classList.add('dark-mode');
                        var btn = document.querySelector('.toggle-dark-btn');
                        if (btn) btn.textContent = '☀';
                    }
                } catch(e) {}

                initTabs();
                initBackToTop();
                initCollapse();
                initStandaloneTabs();

                // 初始化阅读进度条
                window.addEventListener('scroll', function() {
                    var winScroll = document.body.scrollTop || document.documentElement.scrollTop;
                    var height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
                    var scrolled = (winScroll / height) * 100;
                    document.querySelector('.reading-progress').style.width = scrolled + '%';
                });

                // 复制功能
                document.querySelectorAll('.news-number').forEach(function(num) {
                    num.addEventListener('click', function() {
                        var text = this.querySelector('.num-text').textContent;
                        navigator.clipboard.writeText(text).then(function() {
                            num.classList.add('copied');
                            setTimeout(function() {
                                num.classList.remove('copied');
                            }, 2000);
                        });
                    });
                });

                // 快捷键
                document.addEventListener('keydown', function(e) {
                    if (e.ctrlKey || e.metaKey) return;
                    
                    if (e.key === 'w' || e.key === 'W') {
                        toggleWideMode();
                        e.preventDefault();
                    } else if (e.key === 'd' || e.key === 'D') {
                        toggleDarkMode();
                        e.preventDefault();
                    } else if (e.key === '/') {
                        var searchInput = document.querySelector('.search-input');
                        if (searchInput) {
                            searchInput.focus();
                            e.preventDefault();
                        }
                    }
                });
            });
        </script>
    </body>
    </html>
"""

    return html
