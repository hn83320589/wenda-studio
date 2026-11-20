#!/usr/bin/env python3
"""問達工作室部落格建置程式。

用法：
    python3 tools/build.py              建置 posts/ 底下所有文章
    python3 tools/build.py --preview 檔案.md  只把一篇草稿建成單頁預覽（不動 blog/）

文章來源：posts/YYYY-MM-DD-slug.md，開頭為 front matter：
    ---
    title: 標題
    date: 2026-11-17
    category: 排程與批次
    summary: 一兩句摘要
    ---

特殊區塊：
    ```mermaid caption="說明文字"     -> 轉成 SVG（網頁用）與 PNG（Notion、社群用）
    ```figure caption="說明文字" width="720"
    <div>...任意 HTML 示意畫面...</div>
    ```                               -> 截成 PNG

需要：pip install markdown pygments playwright；npm install --prefix tools
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
BLOG = ROOT / "blog"
SITE_URL = "https://hn83320589.github.io/wenda-studio"
MERMAID_JS_CANDIDATES = [
    ROOT / "tools/node_modules/mermaid/dist/mermaid.min.js",
    Path("/home/claude/tools-node/node_modules/mermaid/dist/mermaid.min.js"),
]

FENCE_RE = re.compile(r"^```(mermaid|figure)([^\n]*)\n(.*?)\n```[ \t]*$", re.S | re.M)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')

MERMAID_CONFIG = {
    "startOnLoad": False,
    "theme": "base",
    "flowchart": {"htmlLabels": False, "curve": "basis"},
    "sequence": {"mirrorActors": False},
    "themeVariables": {
        "primaryColor": "#DCEAE7",
        "primaryBorderColor": "#2F7F78",
        "primaryTextColor": "#1B2B3A",
        "secondaryColor": "#F6E7CC",
        "tertiaryColor": "#EEF3F2",
        "lineColor": "#2F7F78",
        "textColor": "#1B2B3A",
        "fontFamily": "Noto Sans TC, PingFang TC, Microsoft JhengHei, sans-serif",
        "fontSize": "16px",
    },
}

BASE_CSS = """
:root{--mist:#EEF3F2;--pane:#DCEAE7;--edge:#2F7F78;--ink:#1B2B3A;--mute:#5A6B75;--amber:#C9861F;--white:#FBFDFC;
--hand:"LXGW WenKai TC","Kaiti TC","BiauKai",serif;--sans:"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;
--mono:"JetBrains Mono","SFMono-Regular",Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--mist);color:var(--ink);font-family:var(--sans);font-size:17px;line-height:1.85;-webkit-font-smoothing:antialiased}
a{color:var(--edge);text-underline-offset:3px}
:focus-visible{outline:3px solid var(--amber);outline-offset:3px}
.wrap{width:min(760px,100% - 40px);margin-inline:auto}
.top{display:flex;justify-content:space-between;align-items:center;padding:22px 0;width:min(1080px,100% - 40px);margin-inline:auto}
.brand{font-family:var(--hand);font-weight:700;font-size:1.2rem;color:var(--ink);text-decoration:none}
.top nav a{margin-left:20px;color:var(--ink);text-decoration:none;font-size:.95rem}
.top nav a:hover{color:var(--edge)}
h1{font-family:var(--hand);font-size:clamp(1.9rem,4vw,2.6rem);line-height:1.3;margin:24px 0 10px}
h2{font-family:var(--hand);font-size:1.55rem;line-height:1.4;margin:48px 0 12px}
h3{font-size:1.12rem;margin:32px 0 8px}
.meta{color:var(--mute);font-size:.92rem;margin-bottom:36px}
.meta span+span::before{content:"／";margin:0 6px;color:rgba(47,127,120,.5)}
article p,article li{max-width:40em}
article img{max-width:100%;height:auto}
figure{margin:32px 0;text-align:center}
figure img{background:var(--white);border:1px solid rgba(47,127,120,.3);border-radius:8px;padding:12px}
figcaption{color:var(--mute);font-size:.9rem;margin-top:8px}
code{font-family:var(--mono);font-size:.88em;background:rgba(220,234,231,.8);padding:1px 5px;border-radius:4px}
pre{background:#1B2B3A;color:#E6EEF0;padding:18px 20px;border-radius:8px;overflow-x:auto;line-height:1.6;font-size:.88rem}
pre code{background:none;padding:0;color:inherit;font-size:inherit}
blockquote{margin:24px 0;padding:4px 20px;border-left:3px solid var(--amber);background:rgba(201,134,31,.08);color:var(--ink)}
table{border-collapse:collapse;width:100%;margin:24px 0;font-size:.95rem;background:var(--white)}
th,td{border:1px solid rgba(47,127,120,.3);padding:8px 12px;text-align:left;vertical-align:top}
th{background:var(--pane)}
.note{color:var(--mute);font-size:.9rem}
.post-end{margin:56px 0 24px;padding-top:24px;border-top:1px dashed rgba(47,127,120,.45)}
.list{list-style:none;padding:0;margin:0}
.list li{padding:22px 0;border-bottom:1px solid rgba(47,127,120,.22)}
.list a.t{font-size:1.15rem;font-weight:700;color:var(--ink);text-decoration:none}
.list a.t:hover{color:var(--edge)}
.list .d{color:var(--mute);font-size:.88rem;display:block;margin-bottom:4px}
.list p{margin:6px 0 0;color:var(--mute)}
footer{padding:40px 0 56px;color:var(--mute);font-size:.88rem}
@media (max-width:600px){body{font-size:16px}.top nav a{margin-left:14px}}
"""

PAGE = """<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="{og_type}">
{og_image}<link rel="alternate" type="application/rss+xml" title="問達工作室文章" href="{root}blog/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=LXGW+WenKai+TC:wght@400;700&family=Noto+Sans+TC:wght@400;500;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<header class="top">
  <a class="brand" href="{root}">問達工作室</a>
  <nav aria-label="頁面導覽"><a href="{root}">首頁</a><a href="{root}blog/">文章</a><a href="{root}#contact">預約診斷</a></nav>
</header>
<main class="wrap">
{body}
</main>
<footer class="wrap">© {year} 問達工作室・<a href="{root}blog/feed.xml">RSS</a></footer>
</body>
</html>
"""


@dataclass
class Post:
    src: Path
    slug: str
    title: str
    date: dt.date
    category: str
    summary: str
    body_md: str
    assets: list[str] = field(default_factory=list)


def parse_post(path: Path) -> Post:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        sys.exit(f"{path} 缺少 front matter")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    for key in ("title", "date", "category", "summary"):
        if key not in meta:
            sys.exit(f"{path} front matter 缺少 {key}")
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    return Post(path, slug, meta["title"], dt.date.fromisoformat(meta["date"]),
                meta["category"], meta["summary"], m.group(2))


class Renderer:
    """用一個 headless 瀏覽器把 mermaid 與 figure 區塊轉成圖檔。"""

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._mermaid_js = next((p for p in MERMAID_JS_CANDIDATES if p.exists()), None)

    def close(self):
        self._browser.close()
        self._pw.stop()

    def mermaid(self, code: str, out_svg: Path, out_png: Path):
        if not self._mermaid_js:
            sys.exit("找不到 mermaid.min.js，請先執行：npm install --prefix tools")
        page = self._browser.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=2)
        page.set_content(f"<html><body style='margin:0;background:#FBFDFC'><div id='c' style='display:inline-block;padding:16px'></div></body></html>")
        page.add_script_tag(path=str(self._mermaid_js))
        svg = page.evaluate(
            """async ([code, cfg]) => {
                mermaid.initialize(cfg);
                const { svg } = await mermaid.render('m' + Math.random().toString(36).slice(2), code);
                const c = document.getElementById('c');
                c.innerHTML = svg;
                // 讓 PNG 以 SVG 原本的寬度輸出，避免被縮小
                const el = c.querySelector('svg');
                const w = el.viewBox.baseVal.width;
                el.setAttribute('width', w);
                el.style.maxWidth = 'none';
                // mermaid 回傳的字串在 foreignObject 裡用 HTML 寫法（<br>），
                // 不是合法 XML，用 <img> 載入 .svg 時會整張顯示不出來；改用 XMLSerializer 輸出
                const tmp = document.createElement('div');
                tmp.innerHTML = svg;
                const out = tmp.querySelector('svg');
                // 寫死原本寬度：<img> 不吃 SVG 內的 max-width，width="100%" 會把小圖放大到整欄
                out.setAttribute('width', w);
                return new XMLSerializer().serializeToString(out);
            }""",
            [code, MERMAID_CONFIG],
        )
        out_svg.write_text(svg, encoding="utf-8")
        page.locator("#c").screenshot(path=str(out_png))
        page.close()

    def figure(self, snippet: str, width: int, out_png: Path):
        page = self._browser.new_page(viewport={"width": width + 48, "height": 600}, device_scale_factor=2)
        page.set_content(
            f"<html><head><style>{BASE_CSS} body{{background:#FBFDFC;margin:0}}</style></head>"
            f"<body><div id='c' style='display:inline-block;padding:24px;width:{width + 48}px'>{snippet}</div></body></html>"
        )
        page.wait_for_timeout(200)
        page.locator("#c").screenshot(path=str(out_png))
        page.close()


def render_body(post: Post, out_dir: Path, renderer: Renderer) -> tuple[str, str | None]:
    """把文章 Markdown 轉成 HTML，並在 out_dir 產生圖檔。回傳 (html, 第一張 PNG 檔名)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    figures: dict[str, str] = {}
    counter = {"n": 0}
    first_png: list[str] = []

    def repl(m: re.Match) -> str:
        kind, attrs_raw, content = m.group(1), m.group(2), m.group(3)
        attrs = dict(ATTR_RE.findall(attrs_raw))
        counter["n"] += 1
        n = counter["n"]
        caption = attrs.get("caption", "")
        png = f"fig-{n}.png"
        if kind == "mermaid":
            svg = f"fig-{n}.svg"
            renderer.mermaid(content, out_dir / svg, out_dir / png)
            img = f'<img src="{svg}" alt="{html.escape(caption or "流程圖")}" loading="lazy">'
        else:
            renderer.figure(content, int(attrs.get("width", "720")), out_dir / png)
            img = f'<img src="{png}" alt="{html.escape(caption or "示意圖")}" loading="lazy">'
        first_png.append(png)
        post.assets.append(png)
        cap = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
        key = f"FIGUREPLACEHOLDER{n}X"
        figures[key] = f"<figure>{img}{cap}</figure>"
        return f"\n{key}\n"

    md_src = FENCE_RE.sub(repl, post.body_md)

    # 一般圖片：posts/<檔名>/ 底下的檔案會一起複製
    asset_dir = post.src.with_suffix("")
    if asset_dir.is_dir():
        for f in asset_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, out_dir / f.name)

    body = markdown.markdown(
        md_src,
        extensions=["fenced_code", "tables", "codehilite", "sane_lists", "attr_list"],
        extension_configs={"codehilite": {"guess_lang": False, "css_class": "hl"}},
    )
    for key, fig in figures.items():
        body = body.replace(f"<p>{key}</p>", fig).replace(key, fig)
    return body, (first_png[0] if first_png else None)


def page(title, description, body, root, og_type="website", og_image=None):
    hl_css = HtmlFormatter(style="monokai").get_style_defs(".hl")
    og = f'<meta property="og:image" content="{og_image}">\n' if og_image else ""
    return PAGE.format(title=html.escape(title), description=html.escape(description), body=body,
                       root=root, css=BASE_CSS + hl_css + ".hl pre{background:#1B2B3A}",
                       og_type=og_type, og_image=og, year=dt.date.today().year)


def build_post(post: Post, out_dir: Path, renderer: Renderer, root: str) -> Path:
    body, first_png = render_body(post, out_dir, renderer)
    article = (
        f"<article>\n<h1>{html.escape(post.title)}</h1>\n"
        f'<div class="meta"><span>{post.date.isoformat()}</span><span>{html.escape(post.category)}</span></div>\n'
        f"{body}\n"
        f'<div class="post-end note">問達工作室｜系統救火與自動化・<a href="{root}">服務說明</a>・<a href="{root}blog/">更多文章</a></div>\n'
        f"</article>"
    )
    og_img = f"{SITE_URL}/blog/{post.slug}/{first_png}" if first_png else None
    out = out_dir / "index.html"
    out.write_text(page(f"{post.title}｜問達工作室", post.summary, article, root, "article", og_img), encoding="utf-8")
    return out


def build_all():
    posts = sorted((parse_post(p) for p in POSTS.glob("*.md")), key=lambda p: p.date, reverse=True)
    if BLOG.exists():
        shutil.rmtree(BLOG)
    BLOG.mkdir()
    renderer = Renderer()
    try:
        for p in posts:
            build_post(p, BLOG / p.slug, renderer, "../../")
            print(f"建置：blog/{p.slug}/")
    finally:
        renderer.close()

    items = "\n".join(
        f'<li><span class="d">{p.date.isoformat()}・{html.escape(p.category)}</span>'
        f'<a class="t" href="{p.slug}/">{html.escape(p.title)}</a><p>{html.escape(p.summary)}</p></li>'
        for p in posts
    ) or "<li><p>文章準備中。</p></li>"
    list_body = f"<h1>文章</h1>\n<p class='note'>系統救火、除錯與自動化的實作紀錄。</p>\n<ul class='list'>\n{items}\n</ul>"
    (BLOG / "index.html").write_text(page("文章｜問達工作室", "系統救火、除錯與自動化的實作紀錄。", list_body, "../"), encoding="utf-8")

    # RSS
    rss_items = "\n".join(
        f"<item><title>{html.escape(p.title)}</title><link>{SITE_URL}/blog/{p.slug}/</link>"
        f"<guid>{SITE_URL}/blog/{p.slug}/</guid><pubDate>{dt.datetime.combine(p.date, dt.time(8)).strftime('%a, %d %b %Y %H:%M:%S +0800')}</pubDate>"
        f"<description>{html.escape(p.summary)}</description></item>"
        for p in posts
    )
    (BLOG / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>問達工作室文章</title>'
        f"<link>{SITE_URL}/blog/</link><description>系統救火、除錯與自動化的實作紀錄</description>{rss_items}</channel></rss>\n",
        encoding="utf-8")

    # sitemap
    urls = [f"{SITE_URL}/", f"{SITE_URL}/blog/"] + [f"{SITE_URL}/blog/{p.slug}/" for p in posts]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(f"<url><loc>{u}</loc></url>" for u in urls) + "\n</urlset>\n", encoding="utf-8")

    # 首頁「最新文章」區塊
    index = ROOT / "index.html"
    src = index.read_text(encoding="utf-8")
    latest = "\n".join(
        f'<li><span class="d">{p.date.isoformat()}</span><a href="blog/{p.slug}/">{html.escape(p.title)}</a></li>'
        for p in posts[:3]
    )
    block = (f'<section id="posts"><div class="wrap"><h2>最新文章</h2><ul class="latest">{latest}</ul>'
             f'<p><a href="blog/">看全部文章</a></p></div></section>') if posts else ""
    new = re.sub(r"<!-- POSTS:START -->.*?<!-- POSTS:END -->",
                 f"<!-- POSTS:START -->{block}<!-- POSTS:END -->", src, flags=re.S)
    nav = '<a href="blog/">文章</a>' if posts else ""
    new = re.sub(r"<!-- NAVBLOG:START -->.*?<!-- NAVBLOG:END -->",
                 f"<!-- NAVBLOG:START -->{nav}<!-- NAVBLOG:END -->", new, flags=re.S)
    index.write_text(new, encoding="utf-8")
    print(f"共 {len(posts)} 篇；已更新 blog/index.html、feed.xml、sitemap.xml、首頁最新文章")


def build_preview(md_path: Path, out_dir: Path):
    post = parse_post(md_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = Renderer()
    try:
        out = build_post(post, out_dir, renderer, "https://hn83320589.github.io/wenda-studio/")
    finally:
        renderer.close()
    print(f"預覽：{out}")
    print(json.dumps({"slug": post.slug, "images": post.assets}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, help="只建一篇草稿的預覽")
    ap.add_argument("--out", type=Path, default=ROOT / "drafts/preview")
    a = ap.parse_args()
    if a.preview:
        build_preview(a.preview, a.out)
    else:
        build_all()
