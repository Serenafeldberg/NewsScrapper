#!/usr/bin/env python3
"""
RSS/HTML-based news scraper for AI and technology news
- Strategy per source: RSS -> RSS auto-discovery -> site scraping
- ALWAYS enriches each item with full article "content" (clean text) from the article page
"""

import feedparser
import logging
from typing import List, Dict, Optional
import json
from datetime import datetime
import re
from urllib.parse import urljoin
import time

import requests
from bs4 import BeautifulSoup

# --------- Logging ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --------- HTTP session ----------
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    })
    s.timeout = 15
    return s

SESSION = make_session()

# --------- Helpers ----------
def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = (text.replace('&amp;', '&')
                .replace('&lt;', '<')
                .replace('&gt;', '>')
                .replace('&quot;', '"')
                .replace('&#8217;', "'")
                .replace('&#8211;', '–')
                .replace('&#8212;', '—'))
    text = re.sub(r'\s+', ' ', text.strip())
    return text

def clamp(s: str, n: int = 300) -> str:
    s = s.strip()
    return (s if len(s) <= n else s[:n].rstrip() + '...')

def iso_from_any(dt_str: Optional[str]) -> Optional[str]:
    if not dt_str:
        return None
    try:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%Z",
                    "%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d"):
            try:
                return datetime.strptime(dt_str, fmt).isoformat()
            except Exception:
                pass
        m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(Z|[+\-]\d{2}:\d{2})?", dt_str)
        if m:
            return dt_str.replace("Z", "+00:00")
    except Exception:
        return None
    return None

def get_soup(url: str) -> Optional[BeautifulSoup]:
    try:
        r = SESSION.get(url, timeout=15)
        if r.status_code >= 400:
            logger.warning(f"HTTP {r.status_code} for {url}")
            return None
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        logger.warning(f"Request error for {url}: {e}")
        return None

def extract_meta(soup: BeautifulSoup, url: str) -> Dict[str, Optional[str]]:
    meta = {"title": None, "description": None, "author": None, "published": None, "canonical": url}
    link_canon = soup.find("link", rel="canonical")
    if link_canon and link_canon.get("href"):
        meta["canonical"] = urljoin(url, link_canon["href"])

    ogt = soup.find("meta", property="og:title")
    if ogt and ogt.get("content"):
        meta["title"] = ogt["content"]
    ogd = soup.find("meta", property="og:description")
    if ogd and ogd.get("content"):
        meta["description"] = ogd["content"]
    art_pub = soup.find("meta", property="article:published_time") or soup.find("meta", attrs={"name": "pubdate"})
    if art_pub and art_pub.get("content"):
        meta["published"] = art_pub["content"]

    auth = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
    if auth and auth.get("content"):
        meta["author"] = auth["content"]

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            txt = tag.string or tag.text
            if not txt:
                continue
            data = json.loads(txt)
            items = data if isinstance(data, list) else [data]
            for obj in items:
                if not isinstance(obj, dict):
                    continue
                typ = obj.get("@type")
                if typ in ("NewsArticle", "Article", "BlogPosting"):
                    meta["title"] = meta["title"] or obj.get("headline")
                    meta["description"] = meta["description"] or obj.get("description")
                    meta["published"] = meta["published"] or obj.get("datePublished") or obj.get("dateCreated")
                    author_obj = obj.get("author")
                    if isinstance(author_obj, dict):
                        meta["author"] = meta["author"] or author_obj.get("name")
                    elif isinstance(author_obj, list) and author_obj:
                        if isinstance(author_obj[0], dict):
                            meta["author"] = meta["author"] or author_obj[0].get("name")
                if typ in ("WebPage",) and obj.get("headline"):
                    meta["title"] = meta["title"] or obj.get("headline")
        except Exception:
            continue

    if not meta["title"]:
        t = soup.find("title")
        if t:
            meta["title"] = t.get_text(strip=True)
    if not meta["description"]:
        p = soup.find("p")
        if p:
            meta["description"] = p.get_text(" ", strip=True)

    meta["title"] = clean_text(meta["title"] or "")
    meta["description"] = clean_text(meta["description"] or "")
    meta["author"] = clean_text(meta["author"] or "") if meta["author"] else None
    meta["published"] = iso_from_any(meta["published"]) if meta["published"] else None
    return meta

def find_rss_links(site_url: str) -> List[str]:
    soup = get_soup(site_url)
    if not soup:
        return []
    rss = []
    for l in soup.find_all("link", rel=lambda x: x and "alternate" in x.lower()):
        typ = (l.get("type") or "").lower()
        href = l.get("href")
        if href and "rss" in typ:
            rss.append(urljoin(site_url, href))
    if not rss:
        guesses = ["feed", "rss", "rss.xml", "feeds", "index.xml", "atom.xml"]
        for g in guesses:
            rss.append(urljoin(site_url.rstrip("/") + "/", g))
    out, seen = [], set()
    for u in rss:
        if u not in seen:
            out.append(u); seen.add(u)
    return out

# --------- Content extraction ----------
def extract_main_content_generic(soup: BeautifulSoup) -> str:
    """
    Heuristics:
      - Prefer <article>, then <main>, then big content containers
      - Collect visible <p> text, skip nav/aside/footer
    """
    if not soup:
        return ""
    candidates = []
    for selector in [
        "article",
        "main",
        '[role="main"]',
        ".article-content", ".post-content", ".entry-content",
        ".content__article-body", ".c-article", ".c-post", ".story-content",
        ".rich-text", ".story-body", ".article__body"
    ]:
        node = soup.select_one(selector)
        if node:
            candidates.append(node)

    if not candidates:
        candidates = [soup.body] if soup.body else [soup]

    def visible_p_tags(root):
        texts = []
        for p in root.find_all("p"):
            if p.find_parent(["nav", "aside", "footer", "header"]):
                continue
            t = p.get_text(" ", strip=True)
            if t and len(t.split()) >= 3:
                texts.append(t)
        return texts

    best_text = ""
    best_len = 0
    for cand in candidates:
        pts = visible_p_tags(cand)
        joined = "\n\n".join(pts)
        if len(joined) > best_len:
            best_text = joined
            best_len = len(joined)
    return best_text.strip()

def extract_main_content_reuters(soup: BeautifulSoup) -> str:
    # Reuters often uses data-testid="paragraph" within article
    if not soup:
        return ""
    parts = []
    for sel in [
        'article [data-testid="paragraph"]',
        'article p',
        '[data-testid="Body"] p',
        '.article-body__content p',
    ]:
        for p in soup.select(sel):
            t = p.get_text(" ", strip=True)
            if t and len(t.split()) >= 3:
                parts.append(t)
        if parts:
            break
    if not parts:
        return extract_main_content_generic(soup)
    return "\n\n".join(parts)

def extract_main_content_ibm(soup: BeautifulSoup) -> str:
    # IBM Think / Newsroom selectors seen frequently
    if not soup:
        return ""
    parts = []
    for sel in [
        "article .ibm--content p",
        "article p",
        ".bx--content p",
        ".ibm-text__container p",
        ".article__body p",
    ]:
        for p in soup.select(sel):
            t = p.get_text(" ", strip=True)
            if t and len(t.split()) >= 3:
                parts.append(t)
        if parts:
            break
    if not parts:
        return extract_main_content_generic(soup)
    return "\n\n".join(parts)

def fetch_article_content(url: str, source_key: str) -> str:
    """
    ALWAYS fetches the article HTML and extracts full-body content.
    This runs for articles discovered via RSS, auto-discovered RSS, or scraped listings.
    """
    soup = get_soup(url)
    if not soup:
        return ""
    # Source-specific overrides
    if source_key.startswith("reuters"):
        return clean_text(extract_main_content_reuters(soup))
    if source_key.startswith("ibm"):
        return clean_text(extract_main_content_ibm(soup))
    # Generic fallback
    return clean_text(extract_main_content_generic(soup))

# --------- Data class ----------
class NewsArticle:
    """Represents a single news article"""
    def __init__(self, title: str, description: str, url: str, source: str,
                 published_date: Optional[str] = None,
                 author: Optional[str] = None,
                 content: Optional[str] = None):
        self.title = title
        self.description = description
        self.url = url
        self.source = source
        self.published_date = published_date
        self.author = author
        self.content = content or ""
    
    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'description': self.description,
            'url': self.url,
            'source': self.source,
            'published_date': self.published_date,
            'author': self.author,
            'content': self.content
        }

# --------- Parsing and scraping ----------
def parse_feed_once(rss_url: str, source_name: str, source_key: str, max_articles: int) -> List[NewsArticle]:
    """
    Parse RSS/Atom feed and ALWAYS enrich each entry by fetching the article page for full content.
    """
    articles: List[NewsArticle] = []
    try:
        logger.info(f"[RSS] Fetching {rss_url}")
        feed = feedparser.parse(rss_url)

        if feed.bozo:
            logger.warning(f"[RSS] Parsing issues for {rss_url}")

        if not feed.entries:
            logger.warning(f"[RSS] No entries for {rss_url}")
            return articles

        for entry in feed.entries[:max_articles]:
            try:
                title = clean_text(entry.get('title', ''))
                if not title or len(title) < 6:
                    continue
                description = clean_text(entry.get('summary', '') or entry.get('description', ''))
                if description:
                    description = re.sub(r'^The post.*?appeared first on.*?\.$', '', description, flags=re.IGNORECASE).strip()
                    description = re.sub(r'^Continue reading.*?$', '', description, flags=re.IGNORECASE).strip()
                    description = clamp(description, 300)
                url = entry.get('link', '')
                if not url:
                    continue

                published_date: Optional[str] = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_date = datetime(*entry.published_parsed[:6]).isoformat()
                    except Exception:
                        pass
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    try:
                        published_date = datetime(*entry.updated_parsed[:6]).isoformat()
                    except Exception:
                        pass

                author = None
                if hasattr(entry, 'author'):
                    author = clean_text(entry.author)
                elif hasattr(entry, 'authors') and entry.authors:
                    author = clean_text(entry.authors[0].get('name', ''))

                # ALWAYS: fetch full content from article page
                content = fetch_article_content(url, source_key)

                articles.append(NewsArticle(
                    title=title,
                    description=description,
                    url=url,
                    source=source_name,
                    published_date=published_date,
                    author=author,
                    content=content
                ))
                time.sleep(0.25)  # be gentle to hosts
            except Exception as e:
                logger.warning(f"[RSS] Error entry {source_name}: {e}")
                continue
    except Exception as e:
        logger.error(f"[RSS] Error fetching {rss_url}: {e}")
    return articles

def scrape_listing_to_articles(listing_url: str,
                               link_filter_regex: str,
                               source_name: str,
                               source_key: str,
                               max_articles: int = 10) -> List[NewsArticle]:
    """
    Scrape listing page and ALWAYS enrich each article with full content.
    """
    soup = get_soup(listing_url)
    if not soup:
        return []

    # Collect candidate links
    hrefs = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        full = urljoin(listing_url, href)
        if re.search(link_filter_regex, full):
            hrefs.add(full)

    candidate_urls, seen = [], set()
    for a in soup.find_all("a", href=True):
        full = urljoin(listing_url, a["href"])
        if full in hrefs and full not in seen:
            candidate_urls.append(full)
            seen.add(full)
        if len(candidate_urls) >= max_articles * 3:
            break

    articles: List[NewsArticle] = []
    for u in candidate_urls:
        if len(articles) >= max_articles:
            break
        try:
            art_soup = get_soup(u)
            if not art_soup:
                continue
            meta = extract_meta(art_soup, u)
            title = meta["title"]
            desc = meta["description"]
            if not title or len(title) < 6:
                continue

            # ALWAYS: full content (source-specific selectors where available)
            if source_key.startswith("reuters"):
                content = clean_text(extract_main_content_reuters(art_soup))
            elif source_key.startswith("ibm"):
                content = clean_text(extract_main_content_ibm(art_soup))
            else:
                content = clean_text(extract_main_content_generic(art_soup))

            art = NewsArticle(
                title=title,
                description=clamp(desc or "", 300),
                url=meta["canonical"] or u,
                source=source_name,
                published_date=meta["published"],
                author=meta["author"],
                content=content
            )
            articles.append(art)
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"[SCRAPE] Failed {u}: {e}")
            continue

    return articles

# --------- Scraper class ----------
class RSSNewsScraper:
    def __init__(self):
        self.sources = {
            'aibusiness': {
                'name': 'AI Business',
                'category': 'AI/Technology',
                'strategies': [
                    {'type': 'rss', 'rss_url': 'https://aibusiness.com/feed'},
                    {'type': 'autodiscover', 'site_url': 'https://aibusiness.com/'}
                ]
            },
            'ainews': {
                'name': 'Artificial Intelligence News',
                'category': 'AI/Technology',
                'strategies': [
                    {'type': 'rss', 'rss_url': 'https://www.artificialintelligence-news.com/feed/'},
                    {'type': 'autodiscover', 'site_url': 'https://www.artificialintelligence-news.com/'}
                ]
            },
            'reuters_tech': {
                'name': 'Reuters Technology',
                'category': 'Technology',
                'strategies': [
                    {'type': 'rss', 'rss_url': 'https://feeds.reuters.com/reuters/technologyNews'},
                    {'type': 'scrape',
                     'listing_url': 'https://www.reuters.com/technology/',
                     'link_regex': r'^https?://www\.reuters\.com/technology/[^#?]+/?$'}
                ]
            },
            'reuters_ai': {
                'name': 'Reuters AI',
                'category': 'AI/Technology',
                'strategies': [
                    {'type': 'scrape',
                     'listing_url': 'https://www.reuters.com/technology/ai/',
                     'link_regex': r'^https?://www\.reuters\.com/technology/ai/[^#?]+/?$'}
                ]
            },
            'ibm_think': {
                'name': 'IBM Think',
                'category': 'AI/Technology',
                'strategies': [
                    {'type': 'autodiscover', 'site_url': 'https://newsroom.ibm.com/'},
                    {'type': 'autodiscover', 'site_url': 'https://www.ibm.com/think'},
                    {'type': 'scrape',
                     'listing_url': 'https://www.ibm.com/think',
                     'link_regex': r'^https?://www\.ibm\.com/(?:think|blog/[^/]+/[^/]+)[^#?]*/?$'}
                ]
            },
            'trendhunter_ai': {
                'name': 'Trend Hunter AI',
                'category': 'AI/Trends',
                'strategies': [
                    {'type': 'rss', 'rss_url': 'https://www.trendhunter.com/rss/technology'},
                    {'type': 'autodiscover', 'site_url': 'https://www.trendhunter.com/'}
                ]
            },
            'techcrunch': {
                'name': 'TechCrunch',
                'category': 'Technology',
                'strategies': [
                    {'type': 'rss', 'rss_url': 'https://techcrunch.com/feed/'},
                    {'type': 'autodiscover', 'site_url': 'https://techcrunch.com/'}
                ]
            },
            'venturebeat_ai': {
                'name': 'VentureBeat AI',
                'category': 'AI/Technology',
                'strategies': [
                    {'type': 'rss', 'rss_url': 'https://venturebeat.com/ai/feed/'},
                    {'type': 'autodiscover', 'site_url': 'https://venturebeat.com/ai/'}
                ]
            },
            'mit_news_ai': {
                'name': 'MIT News AI',
                'category': 'AI/Research',
                'strategies': [
                    {'type': 'rss', 'rss_url': 'https://news.mit.edu/rss/topic/artificial-intelligence2'},
                    {'type': 'autodiscover', 'site_url': 'https://news.mit.edu/topic/artificial-intelligence2'}
                ]
            },
            'openai_blog': {
                'name': 'OpenAI Blog',
                'category': 'AI/Research',
                'strategies': [
                    {'type': 'rss', 'rss_url': 'https://openai.com/blog/rss.xml'},
                    {'type': 'autodiscover', 'site_url': 'https://openai.com/blog'}
                ]
            }
        }

    def is_ai_related(self, title: str, description: str) -> bool:
        ai_keywords = [
            'artificial intelligence',' ai ','machine learning',' ml ','deep learning',
            'neural network','chatgpt','gpt','llm','large language model',
            'automation','robotics','computer vision','nlp','natural language',
            'generative ai','openai','anthropic','claude','bard','gemini','mistral'
        ]
        text = f" {title} {description} ".lower()
        return any(k in text for k in ai_keywords)

    def _run_rss(self, rss_url: str, source_name: str, source_key: str, max_articles: int) -> List[NewsArticle]:
        return parse_feed_once(rss_url, source_name, source_key, max_articles)

    def _run_autodiscover(self, site_url: str, source_name: str, source_key: str, max_articles: int) -> List[NewsArticle]:
        feeds = find_rss_links(site_url)
        logger.info(f"[AUTO] {site_url} discovered feeds: {feeds[:3]}{'...' if len(feeds)>3 else ''}")
        for f in feeds:
            arts = parse_feed_once(f, source_name, source_key, max_articles)
            if arts:
                return arts
        return []

    def _run_scrape(self, listing_url: str, link_regex: str, source_name: str, source_key: str, max_articles: int) -> List[NewsArticle]:
        return scrape_listing_to_articles(listing_url, link_regex, source_name, source_key, max_articles)

    def scrape_source(self, source_key: str, max_articles: int = 10, ai_only: bool = True) -> List[NewsArticle]:
        if source_key not in self.sources:
            logger.error(f"Unknown source: {source_key}")
            return []
        cfg = self.sources[source_key]
        source_name = cfg['name']
        strategies = cfg.get('strategies', [])

        for strat in strategies:
            t = strat.get('type')
            try:
                if t == 'rss':
                    arts = self._run_rss(strat['rss_url'], source_name, source_key, max_articles)
                elif t == 'autodiscover':
                    arts = self._run_autodiscover(strat['site_url'], source_name, source_key, max_articles)
                elif t == 'scrape':
                    arts = self._run_scrape(strat['listing_url'], strat['link_regex'], source_name, source_key, max_articles)
                else:
                    logger.warning(f"Unknown strategy type {t} for {source_key}")
                    arts = []

                # Filter AI-only when the source is general tech
                if ai_only and cfg['category'].lower().startswith('technology'):
                    arts = [a for a in arts if self.is_ai_related(a.title, a.description or "")]

                if arts:
                    logger.info(f"[{source_name}] Strategy '{t}' succeeded with {len(arts)} articles")
                    return arts
                else:
                    logger.info(f"[{source_name}] Strategy '{t}' yielded 0 articles; trying next...")
            except Exception as e:
                logger.error(f"[{source_name}] Strategy '{t}' error: {e}")
                continue

        logger.warning(f"[{source_name}] All strategies failed.")
        return []

    def scrape_all(self, max_articles_per_source: int = 10, ai_only: bool = True) -> Dict[str, List[NewsArticle]]:
        results: Dict[str, List[NewsArticle]] = {}
        total_articles = 0
        logger.info("Starting RSS/HTML news scraping...")
        logger.info("=" * 50)
        for source_key, cfg in self.sources.items():
            try:
                logger.info(f"Scraping {cfg['name']}...")
                articles = self.scrape_source(source_key, max_articles_per_source, ai_only=ai_only)
                results[source_key] = articles
                total_articles += len(articles)
                logger.info(f"✅ {cfg['name']}: {len(articles)} articles")
            except Exception as e:
                logger.error(f"❌ Error scraping {cfg['name']}: {e}")
                results[source_key] = []
        logger.info("=" * 50)
        logger.info(f"Total articles scraped: {total_articles}")
        return results

    def scrape_ai_sources_only(self, max_articles_per_source: int = 10) -> Dict[str, List[NewsArticle]]:
        ai_keys = ['aibusiness','ainews','ibm_think','trendhunter_ai','venturebeat_ai','mit_news_ai','openai_blog']
        results: Dict[str, List[NewsArticle]] = {}
        total_articles = 0
        logger.info("Starting AI-focused RSS/HTML news scraping...")
        logger.info("=" * 50)
        for source_key in ai_keys:
            cfg = self.sources.get(source_key)
            if not cfg:
                results[source_key] = []
                continue
            try:
                logger.info(f"Scraping {cfg['name']}...")
                articles = self.scrape_source(source_key, max_articles_per_source, ai_only=True)
                results[source_key] = articles
                total_articles += len(articles)
                logger.info(f"✅ {cfg['name']}: {len(articles)} articles")
            except Exception as e:
                logger.error(f"❌ Error scraping {cfg['name']}: {e}")
                results[source_key] = []
        logger.info("=" * 50)
        logger.info(f"Total AI articles scraped: {total_articles}")
        return results

    def save_to_json(self, results: Dict[str, List[NewsArticle]], filename: str = "rss_news_results.json"):
        data = {
            'scraped_at': datetime.now().isoformat(),
            'total_articles': sum(len(articles) for articles in results.values()),
            'sources': {}
        }
        for source, articles in results.items():
            src_cfg = self.sources.get(source, {'name': source, 'category': 'Unknown'})
            data['sources'][source] = {
                'name': src_cfg['name'],
                'category': src_cfg['category'],
                'article_count': len(articles),
                'articles': [a.to_dict() for a in articles]
            }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to {filename}")

    def print_summary(self, results: Dict[str, List[NewsArticle]]):
        print("\n🤖 RSS/HTML News Scraper Results")
        print("=" * 50)
        total_articles = 0
        for source_key, articles in results.items():
            src = self.sources.get(source_key, {'name': source_key, 'category': 'Unknown'})
            source_name = src['name']; category = src['category']
            print(f"\n📰 {source_name} ({category})")
            print("-" * 40)
            if not articles:
                print("   No articles found"); continue
            for i, article in enumerate(articles[:3], 1):
                print(f"{i}. {article.title}")
                if article.description:
                    print(f"   📝 {article.description}")
                if article.published_date:
                    print(f"   📅 {article.published_date}")
                if article.author:
                    print(f"   👤 {article.author}")
                print(f"   🔗 {article.url}")
                # content is saved to JSON; we keep console summary compact
                print()
            if len(articles) > 3:
                print(f"   ... and {len(articles) - 3} more articles")
            total_articles += len(articles)
        print(f"\n📊 Total articles: {total_articles}")

# --------- Main ----------
def main():
    scraper = RSSNewsScraper()
    print("🚀 Starting RSS/HTML News Scraper...")
    results = scraper.scrape_ai_sources_only(max_articles_per_source=8)
    scraper.print_summary(results)
    scraper.save_to_json(results)
    return results

if __name__ == "__main__":
    main()
