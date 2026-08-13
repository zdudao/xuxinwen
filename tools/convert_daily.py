#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert_daily.py —— 将 TrendRadar 原始 HTML 转换为黑红报纸风格日报 + 更新首页

用法:
    python tools/convert_daily.py \
        --input <TrendRadar原始HTML路径> \
        [--output-dir <站点html目录, 默认 .>] \
        [--index <站点首页路径, 默认 ./index.html>] \
        [--ai-key <Deepseek API Key>] \
        [--ai-model deepseek-chat] \
        [--skip-ai]   # 跳过 AI 三段式生成（降级模式）

流程:
  1. 解析 TrendRadar 原始 HTML（分类新闻 + RSS + AI 分析块）
  2. 调用 Deepseek 生成: 头条标题 / 4 信号卡 / 3 行动建议 / 每条新闻 现象-判断-动作
  3. 生成黑红报纸风格日报 html/YYYY-MM-DD/HH-MM.html
  4. 更新首页 index.html（今日头条 + 归档列表 + 期数）
"""
import argparse
import datetime
import html as html_mod
import json
import os
import re
import sys

try:
    import requests
except ImportError:
    requests = None

# ══════════════════════════════════════════════════════════════
# 1. 解析 TrendRadar 原始 HTML
# ══════════════════════════════════════════════════════════════

def parse_trendradar(html_text: str) -> dict:
    """从 TrendRadar 原始 HTML 提取结构化数据"""
    # 日期
    date_m = re.search(r'(\d{4}-\d{2}-\d{2})', html_text)
    date_str = date_m.group(1) if date_m else datetime.date.today().isoformat()

    # 抓取时间 HH:MM
    time_m = re.search(r'数据抓取时间:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2})', html_text)
    if time_m:
        hh_mm = f"{time_m.group(2)}-{time_m.group(3)}"
    else:
        hh_mm = datetime.datetime.now().strftime("%H-%M")

    # ── 新闻分组（word-group） ──
    groups = []
    for gm in re.finditer(r'<div class="word-group" data-tab-index="\d+">(.*?)</div>\s*(?=<div class="word-group"|<div class="rss-section)', html_text, re.S):
        block = gm.group(1)
        name_m = re.search(r'class="word-name">([^<]+)</div>', block)
        count_m = re.search(r'class="word-count[^"]*">(\d+)\s*条', block)
        if not name_m:
            continue
        items = []
        for im in re.finditer(r'<div class="news-item[^>]*>(.*?)</div>\s*(?=<div class="news-item|</div>|<div class="word-group)', block, re.S):
            ib = im.group(1)
            link_m = re.search(r'<a href="([^"]+)"[^>]*class="news-link">(.*?)</a>', ib, re.S)
            src_m = re.search(r'class="source-name">([^<]+)</span>', ib)
            if not link_m:
                continue
            items.append({
                "title": clean_text(link_m.group(2)),
                "link": link_m.group(1).strip(),
                "source": clean_text(src_m.group(1)) if src_m else "",
            })
        if items:
            groups.append({
                "name": clean_text(name_m.group(1)),
                "count": int(count_m.group(1)) if count_m else len(items),
                "items": items,
            })

    # ── RSS 深度文章 ──
    rss_items = []
    rss_block_m = re.search(r'<div class="rss-feeds-grid">(.*?)</div>\s*</div>\s*(?=<div class="ai-section|<div class="footer)', html_text, re.S)
    if rss_block_m:
        for fm in re.finditer(r'<div class="feed-group">(.*?)</div>\s*(?=<div class="feed-group|</div>)', rss_block_m.group(1), re.S):
            fb = fm.group(1)
            src_m = re.search(r'class="feed-name">([^<]+)</h3>', fb)
            src = clean_text(src_m.group(1)) if src_m else ""
            for im in re.finditer(r'<a href="([^"]+)"[^>]*class="rss-link">(.*?)</a>', fb, re.S):
                rss_items.append({
                    "title": clean_text(im.group(2)),
                    "link": im.group(1).strip(),
                    "source": src,
                })

    # ── AI 分析块 ──
    ai_blocks = []
    for bm in re.finditer(r'<div class="ai-block">\s*<div class="ai-block-title">([^<]+)</div>\s*<div class="ai-block-content">(.*?)</div>\s*</div>', html_text, re.S):
        title = clean_text(bm.group(1))
        content = clean_text(bm.group(2), keep_br=True)
        ai_blocks.append({"title": title, "content": content})

    # 抓取总数 / 筛选结果
    total_m = re.search(r'<span class="footer-info-label">抓取总数</span>\s*<span class="footer-info-value">(\d+)\s*条', html_text)
    filtered_m = re.search(r'<span class="footer-info-label">筛选结果</span>\s*<span class="footer-info-value">(\d+)\s*条', html_text)

    return {
        "date": date_str,
        "hh_mm": hh_mm,
        "groups": groups,
        "rss_items": rss_items,
        "ai_blocks": ai_blocks,
        "total": int(total_m.group(1)) if total_m else 0,
        "filtered": int(filtered_m.group(1)) if filtered_m else sum(g["count"] for g in groups),
    }


def clean_text(text: str, keep_br: bool = False) -> str:
    """清理 HTML 片段文本"""
    if keep_br:
        text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ══════════════════════════════════════════════════════════════
# 2. AI 生成（头条/信号/行动/三段式）
# ══════════════════════════════════════════════════════════════

AI_SYSTEM_PROMPT = """你是「老许聊实体」的主笔老许，一位深耕实体商业（餐饮/零售/选址/政策）的行业分析师。
你的日报读者是实体店老板与创业者，他们需要的是：新闻背后的判断，以及可落地的行动。

请根据提供的新闻列表，输出严格的 JSON（不要 markdown 代码块），结构如下：
{
  "headline": "今日头条标题，用 3~5 个本期最值得关注的热点关键词概括，逗号分隔，40~60字",
  "signals": [
    {"tag": "4字内标签", "title": "信号标题(10字内)", "desc": "一句话描述(30字内)"}
    × 4 条
  ],
  "actions": [
    {"num": "01", "title": "行动标题(15字内)", "phenomenon": "现象(40字内)", "judgment": "判断(50字内)", "action": "动作(60字内，可含**强调**)"}
    × 3 条
  ],
  "stories": [
    {"fact": "核心事件，客观陈述发生了什么(50字内)", "read": "背景判断，怎么解读(70字内)", "act": "行动参考，老板该怎么做(70字内，可含**强调**)"}
    × 每条新闻一条，顺序与输入一致
  ]
}

要求：
- 语言干练、口语化、有老许自己的判断力，不说正确的废话
- 事实要忠于新闻，判断与行动要有差异化价值
- 不要编造新闻里没有的数字与事实"""


def call_ai(api_key: str, model: str, prompt: str, max_tokens: int = 6000) -> dict:
    """调用 Deepseek 生成结构化日报内容"""
    if not api_key or requests is None:
        return {}
    url = "https://api.deepseek.com/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as e:
        print(f"[warn] AI 调用失败: {e}", file=sys.stderr)
        return {}


def build_ai_prompt(data: dict) -> str:
    """构造 AI prompt：输入新闻清单"""
    lines = [f"今日日期：{data['date']}，共 {len([i for g in data['groups'] for i in g['items']])} 条新闻。\n"]
    lines.append("【新闻清单】（每条格式：序号. [分类] 标题 —— 来源）\n")
    idx = 1
    for g in data["groups"]:
        for it in g["items"]:
            lines.append(f"{idx}. [{g['name']}] {it['title']} —— {it['source']}")
            idx += 1
    lines.append("\n请按 system 要求输出 JSON。stories 数组必须与上面 1..N 顺序一一对应。")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 3. 生成黑红报纸风格日报 HTML
# ══════════════════════════════════════════════════════════════

DAILY_CSS = """
  :root{
    --bg:#100E0C; --ink:#EDE7DD; --muted:#9C9388; --faint:#635B51;
    --hair:rgba(237,231,221,0.12); --accent:#D2553F; --accent-soft:rgba(210,85,63,0.14); --accent-wash:rgba(210,85,63,0.08);
    --serif:'Noto Serif SC','Songti SC',serif;
    --sans:'Inter','Noto Sans SC',-apple-system,'Microsoft YaHei',sans-serif;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{font-family:var(--sans);background:var(--bg);color:var(--ink);line-height:1.8;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  a{color:inherit;text-decoration:none}
  ::selection{background:var(--accent);color:#fff}
  .container{max-width:780px;margin:0 auto;padding:0 24px 96px}

  .masthead{padding:56px 0 30px;text-align:center}
  .rule{height:1px;background:var(--hair);width:100%}
  .kicker{font-size:11px;letter-spacing:.42em;color:var(--muted);text-transform:uppercase;padding:18px 0 14px;font-weight:500}
  .wordmark{font-family:var(--serif);font-weight:900;font-size:clamp(34px,7vw,52px);letter-spacing:.04em;line-height:1;color:var(--ink)}
  .wordmark .dot{color:var(--accent)}
  .edition{font-size:12.5px;letter-spacing:.18em;color:var(--faint);padding:16px 0 18px;font-variant-numeric:tabular-nums}
  .edition .prev{margin-left:14px;font-size:11px;letter-spacing:.06em;color:var(--muted)}
  .edition .prev:hover{color:var(--accent)}

  .lead{position:relative;padding:30px 0 30px 26px;margin:8px 0 6px;border-left:3px solid var(--accent)}
  .lead::before{content:"";position:absolute;left:-3px;top:0;width:3px;height:0;background:var(--accent);transition:height .3s ease}
  .lead:hover::before{height:100%}
  .lead-label{font-size:11px;letter-spacing:.34em;color:var(--accent);font-weight:600;margin-bottom:14px;text-transform:uppercase}
  .lead-title{font-family:var(--serif);font-weight:700;font-size:clamp(22px,4.4vw,30px);line-height:1.32;color:var(--ink);margin-bottom:14px}
  .lead-meta{font-size:12.5px;color:var(--faint);letter-spacing:.04em;font-variant-numeric:tabular-nums}

  .sec-head{display:flex;align-items:baseline;gap:16px;margin:48px 0 20px}
  .sec-head .en{font-size:10px;letter-spacing:.4em;color:var(--faint);text-transform:uppercase;font-weight:500}
  .sec-head h2{font-family:var(--serif);font-size:22px;font-weight:700;color:var(--ink);letter-spacing:.02em}
  .sec-head::after{content:"";flex:1;height:1px;background:var(--hair)}

  .action-card{background:#16130F;border:1px solid var(--hair);border-radius:4px;padding:24px 26px;margin-bottom:14px}
  .action-card .ac-num{font-family:var(--serif);font-size:13px;color:var(--accent);letter-spacing:.2em;font-weight:700}
  .action-card .ac-title{font-size:17px;font-weight:700;color:var(--ink);margin:6px 0 14px;font-family:var(--serif)}
  .action-card .ac-seg{margin-bottom:12px}
  .action-card .ac-seg:last-child{margin-bottom:0}
  .action-card .ac-seg .seg-lbl{display:block;font-size:10px;font-weight:600;letter-spacing:.28em;color:var(--muted);text-transform:uppercase;margin-bottom:4px}
  .action-card .ac-seg p{font-size:14px;color:var(--ink);line-height:1.75;max-width:45em}
  .action-card .ac-seg p strong{color:var(--accent);font-weight:600}

  .signals{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .signal{background:#16130F;border:1px solid var(--hair);border-radius:4px;padding:20px 22px}
  .signal .s-tag{display:inline-block;font-size:10px;font-weight:600;letter-spacing:.22em;color:var(--accent);text-transform:uppercase;margin-bottom:12px;padding-bottom:4px;border-bottom:1px solid var(--accent)}
  .signal .s-title{font-size:15px;font-weight:700;color:var(--ink);margin-bottom:8px;line-height:1.5;font-family:var(--serif)}
  .signal .s-desc{font-size:13px;color:var(--muted);line-height:1.7}

  .story{padding:28px 0;border-bottom:1px solid var(--hair);scroll-margin-top:20px}
  .story:first-of-type{padding-top:8px}
  .story-head{display:flex;align-items:flex-start;gap:18px;margin-bottom:18px}
  .story .s-num{font-family:var(--serif);font-size:13px;color:var(--accent);letter-spacing:.14em;font-weight:700;line-height:1.6;flex-shrink:0;padding-top:4px}
  .story .s-title{font-family:var(--serif);font-size:19px;font-weight:700;color:var(--ink);line-height:1.45;letter-spacing:.01em}
  .story .s-title:hover{color:var(--accent)}
  .story .s-src{margin-top:8px;font-size:11.5px;color:var(--faint);letter-spacing:.06em}
  .story .s-src .sep{color:var(--faint);margin:0 8px}
  .story .s-src a:hover{color:var(--accent)}
  .field{display:grid;grid-template-columns:88px 1fr;gap:18px;padding:12px 0 12px 4px}
  .field .f-lbl{font-size:10.5px;font-weight:600;letter-spacing:.24em;text-transform:uppercase;padding-top:5px}
  .field .f-lbl .f-en{display:block;font-size:9px;letter-spacing:.3em;color:var(--faint);font-weight:500;margin-top:2px}
  .field .f-body{font-size:14px;color:var(--ink);line-height:1.8;max-width:46em}
  .field .f-body strong{color:var(--accent);font-weight:600}
  .field.sec .f-lbl{color:var(--muted)}
  .field.judge .f-lbl{color:var(--accent)}
  .field.act .f-lbl{color:var(--muted)}
  .field.judge .f-body{color:var(--muted)}
  .field.act .f-body{border-left:2px solid var(--accent);padding-left:14px}

  .read{margin-top:4px}
  .read-item{display:grid;grid-template-columns:96px 1fr;gap:18px;padding:15px 4px;border-bottom:1px solid var(--hair);transition:background .2s,padding-left .2s}
  .read-item:hover{background:var(--accent-wash);padding-left:12px}
  .read-item .r-src{font-size:11px;letter-spacing:.18em;color:var(--accent);text-transform:uppercase;font-weight:600}
  .read-item .r-title{font-size:14.5px;color:var(--ink);line-height:1.6}
  .read-item:hover .r-title{color:var(--accent)}

  .insight-block{padding:24px 26px;margin-bottom:14px;background:#16130F;border:1px solid var(--hair);border-left:3px solid var(--accent);border-radius:4px}
  .insight-block h3{font-size:12px;font-weight:600;letter-spacing:.2em;color:var(--accent);text-transform:uppercase;margin-bottom:14px}
  .insight-block p{font-size:14px;color:var(--ink);line-height:1.85;max-width:48em}
  .insight-block .lbl{color:var(--muted);font-weight:600}

  .footer{margin-top:72px;padding-top:34px;border-top:1px solid var(--hair);text-align:center}
  .footer .f-main{font-family:var(--serif);font-size:14px;color:var(--ink);letter-spacing:.08em}
  .footer .f-copy{font-size:11.5px;color:var(--faint);margin-top:16px;font-variant-numeric:tabular-nums;letter-spacing:.06em}
  .footer .f-copy a{color:var(--muted);text-decoration:underline}
  .footer .f-copy a:hover{color:var(--accent)}

  .reveal{opacity:0;transform:translateY(10px);transition:opacity .6s ease,transform .6s ease}
  .reveal.in{opacity:1;transform:none}
  @media (max-width:560px){
    .container{padding:0 18px 72px}
    .signals{grid-template-columns:1fr}
    .field{grid-template-columns:1fr;gap:2px}
    .story-head{flex-direction:column;gap:8px}
    .lead{padding-left:18px}
    .read-item{grid-template-columns:1fr;gap:4px}
  }
  @media (prefers-reduced-motion:reduce){*{transition:none!important}.reveal{opacity:1;transform:none}html{scroll-behavior:auto}}
"""


def esc(s: str) -> str:
    return html_mod.escape(str(s or ""), quote=True)


def render_daily(data: dict, ai: dict, period: int) -> str:
    """渲染黑红报纸风格日报 HTML"""
    d = data["date"].split("-")
    cn_date = f"{d[0]}年{d[1]}月{d[2]}日"
    total_news = sum(g["count"] for g in data["groups"])
    headline = ai.get("headline", "今日实体商业要闻")
    signals = ai.get("signals", [])
    actions = ai.get("actions", [])
    stories = ai.get("stories", [])

    # 上一期链接
    prev_link = ""
    prev_date = datetime.date.fromisoformat(data["date"]) - datetime.timedelta(days=1)
    prev_dir = prev_date.isoformat()
    prev_link = f'<a class="prev" href="../{prev_dir}/">← 上一期</a>'

    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>""" + esc(f"老许聊实体 · {d[1]}月{d[2]}日实体生意日报") + """</title>
<meta name="description" content="今日实体商业要闻速览，每天 5 分钟，看透实体生意。">
<meta property="og:title" content="老许聊实体 · 实体生意日报">
<meta property="og:type" content="article">
<meta property="og:site_name" content="老许聊实体">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700;900&display=swap" rel="stylesheet">
<style>""" + DAILY_CSS + """</style>
</head>
<body>
<div class="container">
  <header class="masthead">
    <div class="rule"></div>
    <div class="kicker">实体商业 · 每日内参</div>
    <h1 class="wordmark">老许聊实体<span class="dot">.</span></h1>
    <div class="edition">第 """ + str(period) + """ 期　·　""" + cn_date + """　·　每日更新""" + prev_link + """</div>
    <div class="rule"></div>
  </header>

  <div class="lead reveal">
    <div class="lead-label">今日头条 · TODAY</div>
    <div class="lead-title">""" + esc(headline) + """</div>
    <div class="lead-meta">""" + cn_date + """　·　阅读约 6 分钟　·　共 """ + str(total_news) + """ 条</div>
  </div>
""")

    # ── 行动建议 ──
    if actions:
        parts.append('  <div class="sec-head reveal"><span class="en">Action</span><h2>今日行动建议</h2></div>\n')
        for a in actions[:3]:
            parts.append(f"""  <div class="action-card reveal">
    <div class="ac-num">{esc(a.get('num', ''))}</div>
    <div class="ac-title">{esc(a.get('title', ''))}</div>
    <div class="ac-seg"><span class="seg-lbl">现象</span><p>{esc(a.get('phenomenon', ''))}</p></div>
    <div class="ac-seg"><span class="seg-lbl">判断</span><p>{esc(a.get('judgment', ''))}</p></div>
    <div class="ac-seg"><span class="seg-lbl">动作</span><p>{esc(a.get('action', ''))}</p></div>
  </div>
""")

    # ── 信号速览 ──
    if signals:
        parts.append('  <div class="sec-head reveal"><span class="en">Signals</span><h2>信号速览</h2></div>\n')
        parts.append('  <div class="signals reveal">\n')
        for s in signals[:4]:
            parts.append(f"""    <div class="signal"><span class="s-tag">{esc(s.get('tag', ''))}</span><div class="s-title">{esc(s.get('title', ''))}</div><div class="s-desc">{esc(s.get('desc', ''))}</div></div>
""")
        parts.append('  </div>\n')

    # ── 新闻条目 ──
    parts.append(f'  <div class="sec-head reveal"><span class="en">Stories</span><h2>今日 {total_news} 条要闻</h2></div>\n')
    idx = 1
    flat_items = [it for g in data["groups"] for it in g["items"]]
    for i, it in enumerate(flat_items):
        seg = stories[i] if i < len(stories) and isinstance(stories[i], dict) else {}
        num = f"{idx:02d}"
        idx += 1
        src_html = esc(it.get("source", ""))
        if it.get("link"):
            link_html = f'<a class="s-title" href="{esc(it["link"])}" target="_blank" rel="noopener">{esc(it["title"])}</a>'
        else:
            link_html = f'<span class="s-title">{esc(it["title"])}</span>'
        if seg:
            fact = seg.get("fact", "")
            read = seg.get("read", "")
            act = seg.get("act", "")
            fields = f"""    <div class="field sec"><span class="f-lbl">核心事件<span class="f-en">FACT</span></span><p class="f-body">{esc(fact)}</p></div>
    <div class="field judge"><span class="f-lbl">背景判断<span class="f-en">READ</span></span><p class="f-body">{esc(read)}</p></div>
    <div class="field act"><span class="f-lbl">行动参考<span class="f-en">ACT</span></span><p class="f-body">{esc(act)}</p></div>
"""
        else:
            fields = ""
        parts.append(f"""  <article class="story reveal" id="s{num}">
    <div class="story-head">
      <span class="s-num">{num}</span>
      <div>
        {link_html}
        <div class="s-src">{src_html}{f'<span class="sep">·</span><a href="{esc(it["link"])}" target="_blank" rel="noopener">原链</a>' if it.get("link") else ''}</div>
      </div>
    </div>
{fields}  </article>
""")

    # ── 深度阅读 ──
    if data["rss_items"]:
        parts.append('  <div class="sec-head reveal"><span class="en">Readings</span><h2>深度阅读</h2></div>\n')
        parts.append('  <div class="read reveal">\n')
        for r in data["rss_items"]:
            parts.append(f"""    <a class="read-item" href="{esc(r['link'])}" target="_blank" rel="noopener"><span class="r-src">{esc(r['source'])}</span><span class="r-title">{esc(r['title'])}</span></a>
""")
        parts.append('  </div>\n')

    # ── 老许研判（AI 分析块） ──
    insight_map = {"核心热点态势": "核心热点态势", "舆论风向争议": "舆论风向争议",
                   "异动与弱信号": "异动与弱信号", "独立源点速览": "独立源点速览",
                   "研判策略建议": "研判策略建议"}
    insight_blocks = []
    for b in data["ai_blocks"]:
        if b["title"] in insight_map:
            insight_blocks.append(b)
    if insight_blocks:
        parts.append('  <div class="sec-head reveal"><span class="en">Insight</span><h2>老许研判</h2></div>\n')
        for b in insight_blocks:
            paras = []
            for para in b["content"].split("\n"):
                para = para.strip()
                if not para:
                    continue
                if para.startswith("【") or "：" in para[:10]:
                    paras.append(f'<p style="margin-top:12px">{esc(para)}</p>')
                else:
                    paras.append(f"<p>{esc(para)}</p>")
            parts.append(f"""  <div class="insight-block reveal">
    <h3>{esc(b['title'])}</h3>
{chr(10).join(paras)}
  </div>
""")

    # ── 页脚 ──
    parts.append(f"""  <footer class="footer reveal">
    <div class="f-main">老许聊实体</div>
    <div class="f-copy">每天 5 分钟，看透实体生意　·　第 {period} 期 · {cn_date}　·　共 {total_news} 条 / {data['total']} 条</div>
  </footer>
</div>

<script>
  var io=new IntersectionObserver(function(es){{es.forEach(function(e){{if(e.isIntersecting){{e.target.classList.add('in');io.unobserve(e.target);}}}});}},{{threshold:0.08}});
  document.querySelectorAll('.reveal').forEach(function(el){{io.observe(el);}});
</script>
</body>
</html>
""")
    return "".join(parts)


# ══════════════════════════════════════════════════════════════
# 4. 更新首页 index.html
# ══════════════════════════════════════════════════════════════

def update_index(index_path: str, data: dict, ai: dict, period: int, daily_rel: str) -> None:
    """更新首页：今日头条 + 归档列表 + 期数"""
    if not os.path.exists(index_path):
        print("[skip] 首页不存在，跳过更新", file=sys.stderr)
        return
    with open(index_path, encoding="utf-8") as f:
        content = f.read()

    d = data["date"].split("-")
    cn_date = f"{d[0]}年{d[1]}月{d[2]}日"
    item_date = f"{d[1]}.{d[2]}"
    headline = ai.get("headline", "今日实体商业要闻")

    # 4.1 今日头条 lead
    lead_pattern = re.compile(
        r'<a class="lead reveal" href="[^"]+" target="_blank" rel="noopener">.*?</a>', re.S)
    new_lead = (f'<a class="lead reveal" href="{daily_rel}" target="_blank" rel="noopener">\n'
                f'    <div class="lead-label">今日头条 · TODAY</div>\n'
                f'    <div class="lead-title">{esc(headline)}</div>\n'
                f'    <div class="lead-meta">{cn_date}　·　阅读约 6 分钟</div>\n'
                f'    <span class="lead-cta">阅读今日日报 →</span>\n'
                f'  </a>')
    if lead_pattern.search(content):
        content = lead_pattern.sub(new_lead, content, count=1)

    # 4.2 归档列表：8月分组顶部插入今日条目（幂等）
    month_key = f"{d[0]}年{d[1]}月"
    new_item = (f'        <a class="item" href="{daily_rel}" target="_blank" rel="noopener">\n'
                f'            <span class="item-date">{item_date}</span>\n'
                f'            <span class="item-title">{esc(headline)}</span>\n'
                f'            <span class="item-arrow" aria-hidden="true">→</span>\n'
                f'        </a>\n')
    month_pattern = re.compile(
        r'(<div class="month-sep"><span>' + re.escape(month_key) + r'</span></div><div class="list">\n)')
    if month_pattern.search(content):
        if daily_rel not in content:
            content = month_pattern.sub(r"\1" + new_item, content, count=1)

    # 4.3 期数
    content = re.sub(r'第 \d+ 期', f'第 {period} 期', content, count=2)
    content = re.sub(r'共 \d+ 期', f'共 {period} 期', content, count=1)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[ok] 首页已更新: {index_path}")


# ══════════════════════════════════════════════════════════════
# 5. 主流程
# ══════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser(description="TrendRadar → 黑红日报 + 首页")
    ap.add_argument("--input", required=True, help="TrendRadar 原始 HTML 路径")
    ap.add_argument("--output-dir", default=".", help="站点 html 目录（默认当前目录）")
    ap.add_argument("--index", default="index.html", help="首页路径（默认 ./index.html）")
    ap.add_argument("--ai-key", default=os.environ.get("AI_API_KEY", ""), help="Deepseek API Key")
    ap.add_argument("--ai-model", default="deepseek-chat", help="AI 模型名")
    ap.add_argument("--skip-ai", action="store_true", help="跳过 AI 生成（降级：仅标题+来源）")
    ap.add_argument("--period", type=int, default=0, help="期数（0=自动从首页探测+1）")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        html_text = f.read()
    data = parse_trendradar(html_text)
    print(f"[ok] 解析完成: {data['date']} {data['hh_mm']}, "
          f"{sum(g['count'] for g in data['groups'])} 条新闻, {len(data['rss_items'])} 篇深度, "
          f"{len(data['ai_blocks'])} 个分析块")

    # AI 生成
    ai = {}
    if not args.skip_ai:
        prompt = build_ai_prompt(data)
        ai = call_ai(args.ai_key, args.ai_model, prompt)
        if ai:
            print(f"[ok] AI 生成完成: 信号{len(ai.get('signals', []))} 行动{len(ai.get('actions', []))} 故事{len(ai.get('stories', []))}")
        else:
            print("[warn] AI 生成失败，降级为无三段式模式", file=sys.stderr)
    else:
        print("[warn] --skip-ai，仅生成标题列表", file=sys.stderr)

    # 期数探测：今日条目已存在则不递增（重跑幂等）
    period = args.period
    if not period and os.path.exists(args.index):
        with open(args.index, encoding="utf-8") as f:
            idx_content = f.read()
        daily_file = f"{data['hh_mm']}.html"
        daily_rel_tmp = f"html/{data['date']}/{daily_file}"
        m = re.search(r'第 (\d+) 期', idx_content)
        cur = int(m.group(1)) if m else 0
        exists = daily_rel_tmp in idx_content
        period = cur if (exists and cur > 0) else cur + 1

    # 渲染日报
    daily_html = render_daily(data, ai, period)
    daily_file = f"{data['hh_mm']}.html"
    daily_rel = f"html/{data['date']}/{daily_file}"
    daily_path = os.path.join(args.output_dir, daily_rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(daily_path), exist_ok=True)
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(daily_html)
    print(f"[ok] 日报已生成: {daily_path}")

    # 更新首页
    update_index(args.index, data, ai, period, daily_rel)

    return 0


if __name__ == "__main__":
    sys.exit(main())
