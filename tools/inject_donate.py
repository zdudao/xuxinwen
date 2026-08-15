#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_donate.py —— 给历史日报批量注入打赏组件（一次性脚本）

规则：
- 在 </style></head> 之间插入 <link rel="stylesheet" href="../../donate.css">
- 在 </body> 前插入 <script src="../../donate.js" data-donate-img="../../donate.png"></script>
- 幂等：已包含 donate.css / donate.js 则跳过
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HTML_DIR = os.path.join(ROOT, "html")

CSS_TAG = '<link rel="stylesheet" href="../../donate.css">'
JS_TAG = '<script src="../../donate.js" data-donate-img="../../donate.png"></script>'

changed = 0
skipped = 0

for dirpath, dirnames, filenames in os.walk(HTML_DIR):
    for fn in sorted(filenames):
        if not fn.endswith(".html"):
            continue
        path = os.path.join(dirpath, fn)
        with open(path, encoding="utf-8") as f:
            content = f.read()

        if "donate.css" in content and "donate.js" in content:
            skipped += 1
            continue

        # head 注入 CSS：在 </head> 前
        if CSS_TAG not in content:
            content = content.replace("</head>", CSS_TAG + "\n</head>", 1)
        # body 尾部注入 JS：在 </body> 前
        if JS_TAG not in content:
            content = content.replace("</body>", JS_TAG + "\n</body>", 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        changed += 1
        print(f"[ok] {os.path.relpath(path, ROOT)}")

print(f"\n完成: 更新 {changed} 个, 跳过 {skipped} 个")
