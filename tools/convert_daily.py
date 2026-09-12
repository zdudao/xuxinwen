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
import urllib.request

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


def _extract_json(text: str) -> dict:
    """尽力从模型输出中解析出 JSON 对象；兼容 ```json 围栏 与 尾逗号。"""
    if not text:
        return {}
    t = text.strip()
    # 1) 去除 markdown 代码围栏
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    # 2) 截取最外层 {...}
    m = re.search(r"\{.*\}", t, re.S)
    cand = m.group(0) if m else t
    try:
        return json.loads(cand)
    except Exception:
        pass
    # 3) 修复尾逗号后重试
    repaired = re.sub(r",\s*([\]}])", r"\1", cand)
    try:
        return json.loads(repaired)
    except Exception:
        return {}


def call_ai(api_key: str, model: str, prompt: str, max_tokens: int = 6000,
            system_prompt: str = None, temperature: float = 0.7,
            retries: int = 2) -> dict:
    """调用 Deepseek 生成结构化内容（标准库 urllib，无外部依赖）。

    - system_prompt: 不传则用默认 AI_SYSTEM_PROMPT（日报）；月总结传 MONTHLY_SYSTEM_PROMPT
    - 失败时自动降级温度重试，提升 JSON 稳定性
    """
    if not api_key:
        return {}
    sys_prompt = system_prompt if system_prompt else AI_SYSTEM_PROMPT
    url = "https://api.deepseek.com/chat/completions"
    last_err = None
    for attempt in range(retries + 1):
        try:
            t = temperature if attempt == 0 else max(0.1, temperature - 0.2)
            payload = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": t,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            parsed = _extract_json(content)
            if parsed:
                return parsed
            last_err = "解析后为空或非 JSON"
        except Exception as e:
            last_err = str(e)
            print(f"[warn] AI 调用第 {attempt + 1} 次失败: {e}", file=sys.stderr)
    print(f"[warn] AI 调用最终失败（共 {retries + 1} 次）: {last_err}", file=sys.stderr)
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
  html{scroll-behavior:smooth;-webkit-text-size-adjust:100%;text-size-adjust:100%}
  body{font-family:var(--sans);background:var(--bg);color:var(--ink);line-height:1.8;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  a{color:inherit;text-decoration:none}
  img,svg,video{max-width:100%;height:auto}
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
  /* ── 自适应：同一页面按屏幕宽度自动重排（桌面 / 平板 / 手机） ── */
  @media (max-width:900px){
    .container{padding:0 22px 84px}
    .masthead{padding:44px 0 26px}
    .sec-head{margin:40px 0 18px}
    .lead{padding:26px 0 26px 22px}
    .field{grid-template-columns:76px 1fr;gap:14px}
    .read-item{grid-template-columns:82px 1fr;gap:14px}
  }
  @media (max-width:600px){
    .container{padding:0 18px 64px}
    body{line-height:1.75}
    .masthead{padding:32px 0 20px}
    .kicker{letter-spacing:.3em;padding:12px 0 10px}
    .edition{padding:12px 0 14px}
    .edition .prev{display:block;margin:6px 0 0}
    .lead{padding:22px 0 22px 16px;margin:6px 0 4px;border-left-width:2px}
    .lead-label{letter-spacing:.24em;margin-bottom:10px}
    .lead-title{font-size:clamp(20px,5.8vw,25px)}
    .sec-head{margin:34px 0 14px;gap:10px}
    .sec-head .en{letter-spacing:.28em}
    .sec-head h2{font-size:19px}
    .signals{grid-template-columns:1fr;gap:10px}
    .signal{padding:16px 16px}
    .action-card,.insight-block{padding:18px 17px;border-radius:3px}
    .action-card .ac-seg p,.insight-block p{font-size:13.5px;line-height:1.72}
    .story{padding:22px 0}
    .story-head{flex-direction:column;gap:6px;margin-bottom:14px}
    .story .s-title{font-size:17.5px}
    .field{grid-template-columns:1fr;gap:2px;padding:10px 0}
    .field .f-lbl{padding-top:0}
    .field .f-lbl .f-en{display:inline;margin:0 0 0 6px}
    .field .f-body{font-size:13.5px;line-height:1.75}
    .field.act .f-body{padding-left:12px}
    .read-item{grid-template-columns:1fr;gap:4px;padding:13px 2px}
    .read-item:hover{padding-left:2px}
    .footer{margin-top:52px;padding-top:26px}
  }
  @media (max-width:380px){
    .container{padding:0 14px 56px}
    .wordmark{letter-spacing:.02em}
    .story .s-title{font-size:16.5px}
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
<link rel="stylesheet" href="../../donate.css">
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
<script src="../../donate.js" data-donate-img="../../donate.png"></script>
</body>
</html>
""")
    return "".join(parts)


# ══════════════════════════════════════════════════════════════
# 3.5 月度总结生成（特稿版 · 杂志长读风，与日报同一视觉语言）
# ══════════════════════════════════════════════════════════════

MONTHLY_CSS = """
  /* ── 特稿版 · 杂志长读（与日报同一视觉语言：纸面 + 印章红 + 衬线） ── */
  *{margin:0;padding:0;box-sizing:border-box}
  html{scroll-behavior:smooth;-webkit-text-size-adjust:100%;text-size-adjust:100%}
  :root{--bg:#FBF7F0;--ink:#201B16;--muted:#776B5E;--faint:#A99C8B;
    --hair:rgba(32,27,22,.15);--accent:#A8321F;--wash:rgba(168,50,31,.06);--card:#FFFFFF;--w:720px;
    --serif:'Noto Serif SC','Songti SC',serif;--sans:'Inter','Noto Sans SC',-apple-system,'Microsoft YaHei',sans-serif}
  body{font-family:var(--sans);background:var(--bg);color:var(--ink);line-height:2.0;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  a{color:inherit;text-decoration:none}
  img,svg,video{max-width:100%;height:auto}
  ::selection{background:var(--accent);color:#fff}
  .container{max-width:var(--w);margin:0 auto;padding:0 30px 110px}
  .rule{height:1px;background:var(--hair)}
  .masthead{padding:72px 0 30px;text-align:center}
  .kicker{font-size:11px;letter-spacing:.42em;color:var(--muted);text-transform:uppercase;padding:16px 0 12px;font-weight:500}
  .wordmark{font-family:var(--serif);font-weight:900;font-size:clamp(34px,6.6vw,52px);letter-spacing:.03em;line-height:1.06}
  .wordmark .dot{color:var(--accent)}
  .edition{font-size:12.5px;letter-spacing:.15em;color:var(--faint);padding:14px 0 16px;font-variant-numeric:tabular-nums}
  .lead{position:relative;padding:34px 0 30px 30px;margin:6px 0;border-left:3px solid var(--accent)}
  .lead-label{font-size:11px;letter-spacing:.32em;color:var(--accent);font-weight:600;margin-bottom:14px;text-transform:uppercase}
  .lead-title{font-family:var(--serif);font-weight:700;font-size:clamp(23px,4.6vw,32px);line-height:1.32;margin-bottom:14px}
  .lead-body{font-size:16.5px;color:var(--muted);line-height:2.05;max-width:46em}
  .lead-body::first-letter{font-family:var(--serif);float:left;font-size:62px;line-height:.84;padding:8px 12px 0 0;color:var(--accent);font-weight:900}
  .nav-chips{display:flex;flex-wrap:wrap;gap:9px;margin:22px 0 2px}
  .chip{font-size:12px;letter-spacing:.05em;color:var(--muted);border:1px solid var(--hair);border-radius:999px;padding:5px 13px}
  .chip b{color:var(--accent);font-weight:600;margin-right:7px;font-family:var(--serif)}
  .sec-head{display:flex;align-items:baseline;gap:14px;margin:64px 0 22px}
  .sec-head .en{font-size:10px;letter-spacing:.4em;color:var(--faint);text-transform:uppercase;font-weight:500}
  .sec-head h2{font-family:var(--serif);font-size:25px;font-weight:700;letter-spacing:.02em}
  .sec-head::after{content:"";flex:1;height:1px;background:var(--hair)}
  .note{font-size:12.5px;color:var(--faint);border:1px dashed var(--hair);padding:12px 16px;margin-top:18px;border-radius:4px}
  .trend{padding:34px 0;border-bottom:1px solid var(--hair)}
  .trend:last-of-type{border-bottom:none}
  .t-head{display:flex;align-items:flex-start;gap:16px;margin-bottom:14px}
  .t-num{font-family:var(--serif);font-size:13px;color:var(--accent);letter-spacing:.14em;font-weight:700;flex-shrink:0;padding-top:6px}
  .t-title{font-family:var(--serif);font-size:23px;font-weight:700;line-height:1.45}
  .t-desc{font-size:15.5px;color:var(--muted);line-height:1.9;margin-bottom:12px}
  .t-field{display:grid;grid-template-columns:74px 1fr;gap:16px;padding:9px 0 9px 2px;margin-top:4px}
  .f-lbl{font-size:10.5px;font-weight:600;letter-spacing:.24em;text-transform:uppercase;padding-top:5px;color:var(--muted)}
  .t-field.judge .f-lbl{color:var(--accent)}
  .f-body{font-size:14.5px;line-height:2.0;max-width:46em}
  .t-field.judge .f-body{color:var(--muted)}
  .t-field.act .f-body{border-left:2px solid var(--accent);padding-left:14px}
  .topic{display:grid;grid-template-columns:34px 1fr;gap:14px;padding:17px 0;border-bottom:1px solid var(--hair)}
  .topic:last-of-type{border-bottom:none}
  .tp-num{font-family:var(--serif);font-size:14px;color:var(--faint);font-weight:700;padding-top:4px;font-variant-numeric:tabular-nums}
  .tp-title{font-family:var(--serif);font-size:18px;font-weight:700;line-height:1.5;margin-bottom:7px}
  .tp-judge{font-size:14.5px;color:var(--muted);line-height:1.9}
  .tp-act{font-size:13px;color:var(--accent);line-height:1.75;margin-top:7px;padding-left:12px;border-left:2px solid var(--accent)}
  .pull{font-family:var(--serif);font-size:23px;font-weight:700;line-height:1.6;padding:34px 0 34px 30px;border-left:3px solid var(--accent);margin:24px 0 10px;color:var(--ink)}
  .chain{background:var(--card);border:1px solid var(--hair);border-left:3px solid var(--accent);border-radius:4px;padding:20px 22px;margin-bottom:14px;box-shadow:0 1px 3px rgba(32,27,22,.05)}
  .chain h4{font-family:var(--serif);font-size:16px;font-weight:700;margin-bottom:9px}
  .chain p{font-size:14px;color:var(--muted);line-height:1.9}
  .fc-call{background:var(--wash);border-left:3px solid var(--accent);padding:20px 22px;font-size:16px;line-height:1.95;margin-bottom:16px}
  .fc-watch{list-style:none}
  .fc-watch li{position:relative;padding:12px 0 12px 22px;border-bottom:1px solid var(--hair);font-size:14px;line-height:1.8}
  .fc-watch li::before{content:'▸';position:absolute;left:0;color:var(--accent)}
  .ins{padding:22px 24px;margin-bottom:14px;background:var(--card);border:1px solid var(--hair);border-left:3px solid var(--accent);border-radius:4px;box-shadow:0 1px 3px rgba(32,27,22,.05)}
  .ins .i-label{font-size:10.5px;letter-spacing:.3em;text-transform:uppercase;color:var(--accent);font-weight:600;margin-bottom:10px}
  .ins .i-label .zh{margin-left:10px;letter-spacing:.12em;color:var(--muted);font-size:12px}
  .ins p{font-size:14.5px;line-height:1.95}
  .index{display:flex;flex-wrap:wrap;gap:6px 16px}
  .ix{font-size:12.5px;color:var(--muted);display:inline-flex;gap:8px;padding:5px 0;max-width:340px}
  .ix .ix-date{color:var(--accent);font-variant-numeric:tabular-nums;font-weight:600;flex-shrink:0}
  .ix:hover{color:var(--ink)}
  .footer{margin-top:60px;padding-top:22px;border-top:1px solid var(--hair);text-align:center;font-size:12px;color:var(--faint);letter-spacing:.08em}
  /* ── 自适应：同一页面按屏幕宽度自动重排（桌面 / 平板 / 手机） ── */
  @media (max-width:900px){
    .container{padding:0 26px 96px}
    .masthead{padding:56px 0 26px}
    .sec-head{margin:52px 0 20px}
    .lead{padding:30px 0 26px 24px}
    .lead-body{font-size:16px;line-height:1.95}
    .t-field{grid-template-columns:68px 1fr;gap:14px}
  }
  @media (max-width:600px){
    .container{padding:0 18px 72px}
    body{line-height:1.85}
    .masthead{padding:38px 0 22px}
    .kicker{letter-spacing:.3em;padding:12px 0 10px}
    .edition{letter-spacing:.1em}
    .nav-chips{gap:7px;margin:18px 0 2px}
    .chip{font-size:11.5px;padding:5px 11px}
    .lead{padding:24px 0 22px 16px;margin:6px 0;border-left-width:2px}
    .lead-label{letter-spacing:.24em;margin-bottom:10px}
    .lead-title{font-size:clamp(20px,5.8vw,25px);line-height:1.34}
    .lead-body{font-size:15.5px;line-height:1.85}
    .lead-body::first-letter{font-size:46px;padding:6px 10px 0 0}
    .sec-head{margin:42px 0 16px;gap:10px}
    .sec-head .en{letter-spacing:.28em}
    .sec-head h2{font-size:21px}
    .trend{padding:26px 0}
    .t-head{gap:12px;margin-bottom:11px}
    .t-title{font-size:20px;line-height:1.42}
    .t-desc{font-size:15px;line-height:1.8;margin-bottom:10px}
    .t-field{grid-template-columns:1fr;gap:2px;padding:8px 0 8px 2px}
    .f-lbl{letter-spacing:.18em;padding-top:0}
    .f-body{font-size:14.5px;line-height:1.85}
    .t-field.act .f-body{padding-left:12px}
    .topic{grid-template-columns:26px 1fr;gap:10px;padding:15px 0}
    .tp-title{font-size:17px;line-height:1.45}
    .tp-judge{font-size:14px;line-height:1.8}
    .tp-act{font-size:12.5px;line-height:1.7;padding-left:10px}
    .pull{font-size:18px;line-height:1.55;padding:26px 0 26px 16px;margin:20px 0 8px;border-left-width:2px}
    .chain{padding:16px;border-radius:3px}
    .chain h4{font-size:15px}
    .chain p{font-size:13.5px;line-height:1.8}
    .fc-call{padding:16px;font-size:15px;line-height:1.85}
    .fc-watch li{padding:10px 0 10px 18px;font-size:13.5px;line-height:1.75}
    .ins{padding:17px;border-radius:3px}
    .ins p{font-size:14px;line-height:1.8}
    .ins .i-label{letter-spacing:.2em;margin-bottom:8px}
    .index{gap:4px 12px}
    .ix{max-width:100%;font-size:13px;padding:7px 0}
    .footer{margin-top:46px;padding-top:22px}
  }
  @media (max-width:380px){
    .container{padding:0 14px 60px}
    .wordmark{letter-spacing:.02em}
    .lead-body::first-letter{font-size:40px;padding:5px 8px 0 0}
    .topic{grid-template-columns:22px 1fr;gap:8px}
    .t-num,.tp-num{font-size:12px}
  }
"""

MONTHLY_SYSTEM_PROMPT = """你是「老许聊实体」的主笔老许，一位深耕实体商业（餐饮/零售/选址/政策）的行业分析师。
你正在为读者撰写一份「月度实体商业深度研判」。读者是实体店老板与创业者，他们不要"新闻复述"，要的是判断、预判与可落地的动作。

请根据提供的「当月每日头条标题」清单，输出严格的 JSON（不要 markdown 代码块），结构如下：
{
  "trends": [
    {"title": "趋势标题(12字内)",
     "desc": "现象：这个月发生了什么(60字内)",
     "so_what": "判断：它为什么会发生、对实体店到底意味着什么(90字内)",
     "action": "动作：老板该据此做什么(50字内)"}
    × 3 条（月度核心趋势）
  ],
  "topics": [
    {"title": "话题标题(15字内)",
     "desc": "现象(45字内)",
     "so_what": "判断：背后的逻辑与影响(70字内)",
     "action": "动作(45字内)"}
    × 10 条（当月十大热门话题，按热度排序）
  ],
  "synthesis": [
    {"chain": "合流标题(14字内)",
     "detail": "把哪几条看似无关的新闻串成一条因果链、共同指向什么结论(110字内)"}
    × 3 条（信号合流：不要孤立看新闻，要指出新闻之间的因果）
  ],
  "forecast": {
    "call": "下月总体预判(120字内：哪些信号会发酵、实体店会先感受到什么)",
    "watch": ["要盯的先行指标1(45字内)", "指标2", "指标3"]
  },
  "insights": {
    "opportunity": "机会点(120字内，给实体老板可抓的具体机会)",
    "risk": "风险提示(120字内，需警惕的具体风险)",
    "action": "行动建议(120字内，具体到本周可做的动作)"
  }
}

硬要求：
- 每条话题与趋势都必须走「现象 → 判断 → 动作」三层，判断要讲"为什么"和"对实体店意味着什么"，不许只复述新闻。
- synthesis 必须真正把多条新闻连起来（如"房租涨 + 社保全额缴 + 金税四期 = 成本三杀"），这是本报告最有价值的部分。
- forecast 必须是对下个月的预判，不是对过去的总结；watch 是要读者去盯的具体先行指标（如"某类店铺的关店率""某政策的落地细则"）。
- 语言干练、口语化、有老许自己的判断力，不说正确的废话。
- 趋势/话题/洞察必须忠于当月头条，不编造新闻里没有的事实与数字。
- 聚焦实体商业视角（餐饮/零售/选址/政策/消费），不要泛泛而谈。"""


def is_month_end(date_str: str) -> bool:
    """判断给定日期是否为当月最后一天"""
    d = datetime.date.fromisoformat(date_str)
    nd = d + datetime.timedelta(days=1)
    return nd.month != d.month


def collect_month_dailies(month: str, output_dir: str) -> list:
    """收集某月所有日报的日期与头条标题，返回 [{date, title, rel}]"""
    from pathlib import Path
    base = Path(output_dir) / "html"
    items = []
    for day_dir in sorted(base.glob(f"{month}-*")):
        if not day_dir.is_dir():
            continue
        for html_file in sorted(day_dir.glob("*.html")):
            raw = html_file.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'<div class="lead-title">([^<]*)</div>', raw)
            title = m.group(1).strip() if (m and m.group(1).strip()) else ""
            # 早期模板的 lead-title 可能缺失或是站名（如「老许聊实体 - 2026-08-05商业资讯」），尝试回退正文真实标题
            suspicious = (not title) or ("老许聊实体" in title) or ("商业资讯" in title)
            if suspicious:
                st = re.search(r'class="s-title"[^>]*>([^<]+)</a>', raw) or re.search(r'<div class="s-title">([^<]+)</div>', raw)
                if st:
                    cand = st.group(1).strip()
                    if "老许聊实体" not in cand and "商业资讯" not in cand:
                        title = cand
            if (not title) or ("老许聊实体" in title) or ("商业资讯" in title):
                t = re.search(r'<title>([^<]*)</title>', raw)
                if t:
                    title = t.group(1).strip().replace("老许聊实体 - ", "").replace("老许聊实体 · ", "")
            if not title:
                title = html_file.stem
            dd = day_dir.name.split("-")[2]
            items.append({
                "date": f"{month.split('-')[1]}-{dd}",
                "title": title,
                "rel": f"{day_dir.name}/{html_file.name}",
            })
    return items


def build_monthly_prompt(month: str, items: list) -> str:
    lines = [f"月份：{month.replace('-', '年')}月（共 {len(items)} 期日报）\n"]
    lines.append("【当月每日头条标题】")
    for it in items:
        lines.append(f"{it['date']}：{it['title']}")
    lines.append("\n请按 system 要求输出 JSON：trends 3 条（各含 desc/so_what/action 三层）、topics 10 条（各含 desc/so_what/action 三层）、synthesis 3 条（chain+detail）、forecast（call + watch 3 条）、insights（opportunity/risk/action）。")
    return "\n".join(lines)


def render_monthly_summary(month: str, items: list, ai: dict) -> str:
    """渲染月度深读页（特稿版 · 杂志长读风，与日报同一视觉语言）"""
    ym = month.split("-")
    y, mo = int(ym[0]), int(ym[1])
    cn_month = f"{y}年{mo}月"
    trends = ai.get("trends", []) or []
    topics = ai.get("topics", []) or []
    insights = ai.get("insights", {}) or {}
    synthesis = ai.get("synthesis", []) or []
    forecast = ai.get("forecast", {}) or {}
    has_ai = bool(ai)

    def _is_real(t):
        return bool(t) and "老许聊实体" not in t and "商业资讯" not in t and len(t) >= 8

    real_items = [it for it in items if _is_real(it["title"])]
    if not trends:
        src = real_items[:3] if real_items else items[:3]
        trends = [{"title": it["title"], "desc": "（AI 深度趋势分析待生成，配置 key 后重跑）"} for it in src]
    if not topics:
        src = real_items[:10] if real_items else items[:10]
        topics = [{"title": it["title"], "desc": "（AI 话题提炼待生成，配置 key 后重跑）"} for it in src]

    # 刊头期次行
    last_day = (datetime.date(y, mo, 1) + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    edition_line = f"{y}.{mo:02d}.01 — {mo:02d}.{last_day.day:02d}　·　共 {len(items)} 期　·　老许聊实体"

    # 卷首导语：优先「信号合流」第一条，退回首条主线
    if synthesis:
        lead_title = synthesis[0].get("chain", "") or (trends[0].get("title", "") if trends else "")
        lead_body = synthesis[0].get("detail", "") or (trends[0].get("desc", "") if trends else "")
    else:
        lead_title = trends[0].get("title", "") if trends else cn_month + "实体商业"
        lead_body = trends[0].get("desc", "") if trends else ""

    chips_html = "".join(
        f'<span class="chip"><b>{i:02d}</b>{esc(t.get("title", ""))}</span>'
        for i, t in enumerate(trends[:3], 1)
    )

    def _trend_article(i, t):
        parts = ['<article class="trend">',
                 f'  <div class="t-head"><span class="t-num">{i:02d}</span><h3 class="t-title">{esc(t.get("title", ""))}</h3></div>']
        if t.get("desc"):
            parts.append(f'  <p class="t-desc">{esc(t["desc"])}</p>')
        if t.get("so_what"):
            parts.append(f'  <div class="t-field judge"><span class="f-lbl">判断</span><p class="f-body">{esc(t["so_what"])}</p></div>')
        if t.get("action"):
            parts.append(f'  <div class="t-field act"><span class="f-lbl">动作</span><p class="f-body">{esc(t["action"])}</p></div>')
        parts.append('</article>')
        return "\n".join(parts)

    trends_html = "\n".join(_trend_article(i, t) for i, t in enumerate(trends[:3], 1))

    def _topic_article(i, tp):
        judge = "　".join([x for x in [tp.get("desc", ""), tp.get("so_what", "")] if x])
        parts = ['<article class="topic">',
                 f'  <div class="tp-num">{i:02d}</div>',
                 '  <div>',
                 f'    <h3 class="tp-title">{esc(tp.get("title", ""))}</h3>']
        if judge:
            parts.append(f'    <p class="tp-judge">{esc(judge)}</p>')
        if tp.get("action"):
            parts.append(f'    <p class="tp-act">{esc(tp["action"])}</p>')
        parts += ['  </div>', '</article>']
        return "\n".join(parts)

    topics_html = "\n".join(_topic_article(i, tp) for i, tp in enumerate(topics[:10], 1))

    # 引言块：取导语最后一句（需与导语本体不同，避免重复）
    pull_html = ""
    if lead_body:
        sents = [x.strip() for x in re.split(r"[。！？]", lead_body) if x.strip()]
        if len(sents) >= 2:
            last = sents[-1] + "。"
            if last != lead_body:
                pull_html = f'<blockquote class="pull">{esc(last)}</blockquote>'

    synthesis_html = "\n".join(
        f'<div class="chain"><h4>{esc(s.get("chain", ""))}</h4><p>{esc(s.get("detail", ""))}</p></div>'
        for s in synthesis[:3]
    )
    fc_call = esc(forecast.get("call", ""))
    fc_watch = forecast.get("watch", []) or []
    forecast_html = ""
    if fc_call or fc_watch:
        call_html = f'<div class="fc-call">{fc_call}</div>' if fc_call else ""
        watch_inner = "\n".join(f'<li>{esc(w)}</li>' for w in fc_watch[:5])
        watch_html = f'<ul class="fc-watch">{watch_inner}</ul>' if watch_inner else ""
        forecast_html = "\n".join([x for x in [call_html, watch_html] if x])

    insights_html = "\n".join(
        f'<div class="ins"><div class="i-label">{en}<span class="zh">{zh}</span></div><p>{esc(val or "（AI 深度分析待生成）")}</p></div>'
        for en, zh, val in [
            ("Opportunity", "机会点", insights.get("opportunity", "")),
            ("Risk", "风险提示", insights.get("risk", "")),
            ("Action", "行动建议", insights.get("action", "")),
        ]
    )

    def _ix(it):
        t = it["title"]
        if len(t) > 26:
            t = t[:26] + "…"
        return f'<a class="ix" href="{esc(it["rel"])}"><span class="ix-date">{esc(it["date"])}</span>{esc(t)}</a>'
    index_html = "\n".join(_ix(it) for it in items)

    ai_note = "" if has_ai else '<div class="note">※ 本月「主线 / 话题」暂由当月头条标题自动聚合；配置 AI key 后重跑即为深度研判版。</div>'

    synthesis_section = ""
    if synthesis_html:
        synthesis_section = ('<div class="sec-head"><span class="en">Convergence</span><h2>信号合流 · 新闻之间的因果</h2></div>\n'
                             + synthesis_html)
    forecast_section = ""
    if forecast_html:
        forecast_section = ('<div class="sec-head"><span class="en">Forecast</span><h2>下月预判 · 盯住这几个信号</h2></div>\n'
                            + forecast_html)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>老许聊实体 · {cn_month}月度深读</title>
<meta name="description" content="{cn_month}实体商业月度深读：三条主线、十大话题、信号合流与下月预判。">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../donate.css">
<style>{MONTHLY_CSS}</style>
</head>
<body>
<div class="container">
  <header class="masthead">
    <div class="rule"></div>
    <div class="kicker">实体商业 · 月度深读</div>
    <h1 class="wordmark">{cn_month}<span class="dot">·</span>实体月读</h1>
    <div class="edition">{edition_line}</div>
    <div class="rule"></div>
  </header>
  <section class="lead">
    <div class="lead-label">卷首 · The Month in One Line</div>
    <h2 class="lead-title">{esc(lead_title)}</h2>
    <p class="lead-body">{esc(lead_body)}</p>
    <div class="nav-chips">{chips_html}</div>
  </section>
  {ai_note}
  <div class="sec-head"><span class="en">Mainlines</span><h2>本月三条主线</h2></div>
{trends_html}
  <div class="sec-head"><span class="en">Topics</span><h2>十大热门话题</h2></div>
{topics_html}
  {pull_html}
{synthesis_section}
{forecast_section}
  <div class="sec-head"><span class="en">Insights</span><h2>行业洞察与建议</h2></div>
{insights_html}
  <div class="sec-head"><span class="en">Archive</span><h2>本期日期索引</h2></div>
  <div class="index">
{index_html}
  </div>
  <footer class="footer">老许聊实体 · 每月底自动生成 · 数据来源：每日实体生意日报</footer>
</div>
</body>
</html>
"""


def generate_monthly_summary(month: str, output_dir: str, api_key: str, model: str) -> str:
    """生成某月月度总结页面，返回输出文件路径"""
    from pathlib import Path
    items = collect_month_dailies(month, output_dir)
    if not items:
        print(f"[skip] 未找到 {month} 的日报，跳过月总结", file=sys.stderr)
        return ""
    ai = {}
    if api_key:
        prompt = build_monthly_prompt(month, items)
        ai = call_ai(api_key, model, prompt, max_tokens=4000, system_prompt=MONTHLY_SYSTEM_PROMPT)
        if ai:
            print(f"[ok] AI 月度分析完成: 趋势{len(ai.get('trends', []))} 话题{len(ai.get('topics', []))}")
        else:
            print("[warn] AI 月度分析失败，降级为头条聚合", file=sys.stderr)
    else:
        print("[warn] 无 AI key，月总结降级为头条聚合", file=sys.stderr)
    html = render_monthly_summary(month, items, ai)
    out_path = Path(output_dir) / "html" / f"{month}-summary.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"[ok] 月总结已生成: {out_path}（{len(items)} 期）")
    return str(out_path)


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

    # 4.2 归档列表：对应月份分组插入今日条目（幂等：按日期判断）
    #     - 月份分组已存在 → 在该组顶部插入
    #     - 月份分组不存在（每月首日）→ 自动新建该月份分隔组（修复：跨月不归档的 bug）
    #     注：首页曾被页面编辑器注入 data-page-node-id 等属性，正则须容忍此类属性与换行差异
    month_key = f"{d[0]}年{d[1]}月"
    item_date_full = f"{d[0]}.{d[1]}.{d[2]}"
    new_item = (f'        <a class="item" href="{daily_rel}" target="_blank" rel="noopener">\n'
                f'            <span class="item-date">{item_date_full}</span>\n'
                f'            <span class="item-title">{esc(headline)}</span>\n'
                f'            <span class="item-arrow" aria-hidden="true">→</span>\n'
                f'        </a>\n')
    month_pattern = re.compile(
        r'<div class="month-sep"[^>]*><span[^>]*>' + re.escape(month_key) + r'</span></div><div class="list"[^>]*>')
    if month_pattern.search(content):
        # 幂等：该日期条目已存在则不重复插入
        if f'<span class="item-date">{item_date_full}</span>' not in content:
            content = month_pattern.sub(lambda m: m.group(0) + "\n" + new_item, content, count=1)
    else:
        # 新建月份分组：插在「往期归档」标签之后、现有第一个月份分组之前
        new_block = (f'<div class="month-sep"><span>{month_key}</span></div>'
                     f'<div class="list">\n{new_item}</div>')
        sec = re.search(r'<div class="sec-label[^>]*>往期归档[^\n]*</div>', content)
        if sec:
            content = content[:sec.end()] + new_block + content[sec.end():]
        elif '<div class="archive' in content:
            content = content.replace('<div class="archive', new_block + '<div class="archive', 1)

    # 4.3 期数 + 刊头日期
    content = re.sub(r'第 \d+ 期', f'第 {period} 期', content, count=2)
    # 刊头 edition 的日期（第 X 期　·　YYYY年MM月DD日　·　每日更新）
    content = re.sub(r'(第 \d+ 期　·　)\d{4}年\d{2}月\d{2}日(　·　每日更新)',
                     f'\\g<1>{cn_date}\\g<2>', content, count=1)
    content = re.sub(r'共 \d+ 期', f'共 {period} 期', content, count=1)
    # 页脚最后更新日期
    content = re.sub(r'(最后更新 )\d{4}年\d{2}月\d{2}日', f'\\g<1>{cn_date}', content, count=1)

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[ok] 首页已更新: {index_path}")

    # 4.4 注入月度总结链接（幂等：已存在则跳过；每月底生成的月总结自动出现在此）
    inject_summary_links(index_path)


def inject_summary_links(index_path: str) -> None:
    """把已生成的月度总结页（html/YYYY-MM-summary.html）链接注入对应月份归档分组之后。

    每月底 generate_monthly_summary 生成总结页后，下一轮 update_index 会自动把链接补进首页；
    历史月总结（如 8 月）也可在生成总结页后由本函数一次补齐。幂等，重复运行不会重复插入。
    """
    from pathlib import Path
    html_dir = Path(index_path).parent / "html"
    if not html_dir.exists():
        return
    summaries = sorted(html_dir.glob("*-summary.html"))
    if not summaries:
        return
    try:
        content = Path(index_path).read_text(encoding="utf-8")
    except Exception:
        return
    changed = False
    for summ in summaries:
        month_id = summ.stem.replace("-summary", "")
        if "-" not in month_id:
            continue
        y, m = month_id.split("-", 1)
        month_key = f"{y}年{m}月"  # 月份零填充，须与首页 month-sep 文本一致（如 2026年08月）
        href = f"html/{summ.name}"
        if href in content:
            continue  # 已注入，跳过
        link_html = (f'        <a class="summary-link" href="{href}" target="_blank" '
                     f'rel="noopener">{int(m)}月新闻汇总与分析　汇总 →</a>\n')
        # 定位该月份的 .list 块（条目均为 <a>，无嵌套 <div>，故非贪婪可精确收口）
        pat = re.compile(
            r'(<div class="month-sep"[^>]*>\s*<span[^>]*>' + re.escape(month_key)
            + r'</span></div>\s*)(<div class="list"[^>]*>.*?</div>)', re.S)
        mm = pat.search(content)
        if not mm:
            continue
        content = content[:mm.end()] + "\n" + link_html + content[mm.end():]
        changed = True
        print(f"[ok] 已注入月总结链接: {href}")
    if changed:
        Path(index_path).write_text(content, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# 5. 主流程
# ══════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser(description="TrendRadar → 黑红日报 + 首页")
    ap.add_argument("--input", default="", help="TrendRadar 原始 HTML 路径（非月总结模式必填）")
    ap.add_argument("--output-dir", default=".", help="站点 html 目录（默认当前目录）")
    ap.add_argument("--index", default="index.html", help="首页路径（默认 ./index.html）")
    ap.add_argument("--ai-key", default=os.environ.get("AI_API_KEY", ""), help="Deepseek API Key")
    ap.add_argument("--ai-model", default="deepseek-chat", help="AI 模型名")
    ap.add_argument("--skip-ai", action="store_true", help="跳过 AI 生成（降级：仅标题+来源）")
    ap.add_argument("--period", type=int, default=0, help="期数（0=自动从首页探测+1）")
    ap.add_argument("--monthly-summary", action="store_true", help="仅生成月度总结（配合 --month 指定月份，不生成日报）")
    ap.add_argument("--month", default="", help="指定月份 YYYY-MM（用于 --monthly-summary 补历史月；缺省取当月）")
    args = ap.parse_args()

    # 仅生成月度总结（手动补历史月 / 显式调用入口，不生成日报）
    if args.monthly_summary:
        month = args.month or datetime.date.today().strftime("%Y-%m")
        out = generate_monthly_summary(month, args.output_dir, args.ai_key, args.ai_model)
        if out:
            print(f"[ok] 月总结已输出: {out}")
        return 0

    if not args.input:
        print("[error] 非月总结模式下 --input 必填", file=sys.stderr)
        return 1

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

    # 月末自动生成月度总结：若今天是当月最后一天，则聚合全月生成月总结
    if is_month_end(data["date"]):
        month = data["date"][:7]
        print(f"[info] 检测到 {month} 最后一天，自动生成月度总结…")
        generate_monthly_summary(month, args.output_dir, args.ai_key, args.ai_model)

    return 0


if __name__ == "__main__":
    sys.exit(main())
