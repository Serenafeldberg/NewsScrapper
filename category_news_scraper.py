#!/usr/bin/env python3
"""
Multi-Category News Scraper
- Organizes news by categories (AI, Marketing, etc.)
- Creates separate folders and JSON files for each category
- Flexible URL input system
"""

import feedparser
import logging
from typing import List, Dict, Optional
import json
from datetime import datetime
import re
from urllib.parse import urljoin
import time
import os
from pathlib import Path

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
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
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

def get_soup(url: str) -> Optional[BeautifulSoup]:
    """Get BeautifulSoup object from URL"""
    try:
        response = SESSION.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def extract_meta(soup: BeautifulSoup, url: str) -> Dict[str, Optional[str]]:
    """Extract metadata from page"""
    meta = {"title": None, "description": None, "author": None, "published": None, "canonical": url}
    
    # Canonical
    link_canon = soup.find("link", rel="canonical")
    if link_canon and link_canon.get("href"):
        meta["canonical"] = urljoin(url, link_canon["href"])

    # OpenGraph
    ogt = soup.find("meta", property="og:title")
    if ogt and ogt.get("content"):
        meta["title"] = ogt["content"]

    ogd = soup.find("meta", property="og:description")
    if ogd and ogd.get("content"):
        meta["description"] = ogd["content"]

    # Article meta
    art_pub = soup.find("meta", property="article:published_time") or soup.find("meta", attrs={"name": "pubdate"})
    if art_pub and art_pub.get("content"):
        meta["published"] = art_pub["content"]

    # Author
    auth = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
    if auth and auth.get("content"):
        meta["author"] = auth["content"]

    # Fallback <title> and first <p>
    if not meta["title"]:
        t = soup.find("title")
        if t:
            meta["title"] = t.get_text(" ", strip=True)

    if not meta["description"]:
        p = soup.find("p")
        if p:
            meta["description"] = p.get_text(" ", strip=True)

    # Cleanup
    meta["title"] = clean_text(meta["title"] or "")
    meta["description"] = clean_text(meta["description"] or "")
    meta["author"] = clean_text(meta["author"] or "")
    
    return meta

def extract_main_content(soup: BeautifulSoup) -> str:
    """Extract main content from page"""
    if not soup:
        return ""
    
    # Remove unwanted elements
    for unwanted in soup.select('script, style, nav, aside, footer, header, .advertisement, .ad, .sidebar, .comments, .social-share'):
        unwanted.decompose()
    
    candidates = []
    selectors = [
        "article",
        "main",
        '[role="main"]',
        ".article-content", ".post-content", ".entry-content", ".article-body",
        ".content__article-body", ".c-article", ".c-post", ".story-content",
        ".rich-text", ".story-body", ".article__body", ".post-body",
        ".entry-body", ".content-body", ".article-text", ".post-text",
        "[data-testid='article-content']", "[data-testid='story-content']",
        ".content", ".main-content", ".article-main", ".post-main"
    ]
    
    for selector in selectors:
        nodes = soup.select(selector)
        for node in nodes:
            if node and node not in candidates:
                candidates.append(node)

    if not candidates:
        candidates = [soup.body] if soup.body else [soup]

    def extract_text_content(root):
        texts = []
        for p in root.find_all("p"):
            if p.find_parent(["nav", "aside", "footer", "header", ".advertisement", ".ad", ".sidebar"]):
                continue
            text = p.get_text(" ", strip=True)
            if text and len(text.split()) >= 5:
                texts.append(text)
        return texts

    best_text = ""
    best_len = 0
    for cand in candidates:
        texts = extract_text_content(cand)
        if texts:
            joined = "\n\n".join(texts)
            if len(joined) > best_len:
                best_text = joined
                best_len = len(joined)
    
    return clean_text(best_text.strip())

def find_rss_links(site_url: str) -> List[str]:
    """Find RSS links from a site"""
    soup = get_soup(site_url)
    if not soup:
        return []
    
    rss = []
    for link in soup.find_all("link"):
        href = link.get("href")
        typ = link.get("type", "").lower()
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

# --------- Data class ----------
class NewsArticle:
    def __init__(self, title: str, description: str, url: str, source: str, category: str,
                 published_date: Optional[str] = None,
                 author: Optional[str] = None,
                 content: Optional[str] = None):
        self.title = title
        self.description = description
        self.url = url
        self.source = source
        self.category = category
        self.published_date = published_date
        self.author = author
        self.content = content or ""
    
    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'description': self.description,
            'url': self.url,
            'source': self.source,
            'category': self.category,
            'published_date': self.published_date,
            'author': self.author,
            'content': self.content
        }

# --------- Scraping functions ----------
def scrape_rss_feed(rss_url: str, source_name: str, category: str, max_articles: int = 15) -> List[NewsArticle]:
    """Scrape articles from RSS feed"""
    articles = []
    try:
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            logger.warning(f"No entries found in RSS feed: {rss_url}")
            return articles
        
        for entry in feed.entries[:max_articles]:
            try:
                title = clean_text(entry.title) if hasattr(entry, 'title') else ""
                description = clean_text(entry.summary) if hasattr(entry, 'summary') else ""
                url = entry.link if hasattr(entry, 'link') else ""
                
                if not title or not url:
                    continue
                
                # Extract content from article page
                soup = get_soup(url)
                content = ""
                if soup:
                    content = extract_main_content(soup)
                    if len(content) > 3000:
                        content = content[:3000] + "..."
                
                published_date = None
                if hasattr(entry, 'published'):
                    published_date = entry.published
                
                author = None
                if hasattr(entry, 'authors') and entry.authors:
                    author = clean_text(entry.authors[0].get('name', ''))
                
                articles.append(NewsArticle(
                    title=title,
                    description=description,
                    url=url,
                    source=source_name,
                    category=category,
                    published_date=published_date,
                    author=author,
                    content=content
                ))
                
                time.sleep(0.5)  # Be respectful
                
            except Exception as e:
                logger.warning(f"Error processing RSS entry: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error parsing RSS feed {rss_url}: {e}")
    
    return articles

def scrape_website_articles(site_url: str, source_name: str, category: str, max_articles: int = 15) -> List[NewsArticle]:
    """Scrape articles from website directly"""
    articles = []
    
    # First try to find RSS feed
    rss_links = find_rss_links(site_url)
    for rss_url in rss_links:
        logger.info(f"Trying RSS feed: {rss_url}")
        rss_articles = scrape_rss_feed(rss_url, source_name, category, max_articles)
        if rss_articles:
            return rss_articles
    
    # If no RSS, try to scrape the main page
    soup = get_soup(site_url)
    if not soup:
        return articles
    
    # Look for article links
    article_links = []
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if href and ('article' in href.lower() or 'news' in href.lower() or 'blog' in href.lower()):
            full_url = urljoin(site_url, href)
            if full_url not in article_links:
                article_links.append(full_url)
                if len(article_links) >= max_articles * 2:  # Get extra in case some fail
                    break
    
    # Process each article link
    for url in article_links[:max_articles]:
        try:
            soup = get_soup(url)
            if not soup:
                continue
            
            meta = extract_meta(soup, url)
            content = extract_main_content(soup)
            
            if len(content) > 3000:
                content = content[:3000] + "..."
            
            if meta["title"] and len(meta["title"]) > 10:
                articles.append(NewsArticle(
                    title=meta["title"],
                    description=meta["description"],
                    url=url,
                    source=source_name,
                    category=category,
                    published_date=meta["published"],
                    author=meta["author"],
                    content=content
                ))
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.warning(f"Error processing article {url}: {e}")
            continue
    
    return articles

# --------- Main scraper class ----------
class CategoryNewsScraper:
    def __init__(self):
        self.categories = {}
        self.results = {}
    
    def add_category(self, category_name: str, urls: List[str]):
        """Add a category with its URLs"""
        self.categories[category_name] = urls
        logger.info(f"Added category '{category_name}' with {len(urls)} URLs")
    
    def scrape_category(self, category_name: str, max_articles_per_source: int = 15) -> List[NewsArticle]:
        """Scrape all sources in a category"""
        if category_name not in self.categories:
            logger.error(f"Category '{category_name}' not found")
            return []
        
        all_articles = []
        urls = self.categories[category_name]
        
        logger.info(f"Scraping category: {category_name}")
        logger.info(f"URLs: {urls}")
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Processing {i}/{len(urls)}: {url}")
            
            # Extract source name from URL
            source_name = url.split('//')[1].split('/')[0].replace('www.', '')
            
            # Try RSS first, then direct scraping
            articles = scrape_rss_feed(url, source_name, category_name, max_articles_per_source)
            if not articles:
                articles = scrape_website_articles(url, source_name, category_name, max_articles_per_source)
            
            all_articles.extend(articles)
            logger.info(f"Found {len(articles)} articles from {source_name}")
            
            time.sleep(1)  # Delay between sources
        
        return all_articles
    
    def scrape_all_categories(self, max_articles_per_source: int = 15) -> Dict[str, List[NewsArticle]]:
        """Scrape all categories"""
        self.results = {}
        
        for category_name in self.categories:
            logger.info(f"\n{'='*50}")
            logger.info(f"Scraping category: {category_name}")
            logger.info(f"{'='*50}")
            
            articles = self.scrape_category(category_name, max_articles_per_source)
            self.results[category_name] = articles
            
            logger.info(f"✅ {category_name}: {len(articles)} articles")
        
        return self.results
    
    def save_results(self, output_dir: str = "news_by_category"):
        """Save results to organized folder structure"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        for category_name, articles in self.results.items():
            # Create category folder (replace slashes and spaces with underscores)
            safe_name = category_name.lower().replace(' ', '_').replace('/', '_')
            category_path = output_path / safe_name
            category_path.mkdir(parents=True, exist_ok=True)
            
            # Save JSON file
            json_file = category_path / f"{safe_name}_news.json"
            
            data = {
                'category': category_name,
                'scraped_at': datetime.now().isoformat(),
                'total_articles': len(articles),
                'articles': [article.to_dict() for article in articles]
            }
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved {len(articles)} articles to {json_file}")
    
    def print_summary(self):
        """Print summary of all results"""
        print("\n" + "="*60)
        print("📰 MULTI-CATEGORY NEWS SCRAPER RESULTS")
        print("="*60)
        
        total_articles = 0
        for category_name, articles in self.results.items():
            print(f"\n📂 {category_name.upper()}")
            print("-" * 40)
            print(f"   Total articles: {len(articles)}")
            
            if articles:
                for i, article in enumerate(articles[:3], 1):
                    print(f"   {i}. {article.title}")
                    if article.description:
                        desc = article.description[:100] + "..." if len(article.description) > 100 else article.description
                        print(f"      📝 {desc}")
                    if article.content:
                        content_preview = article.content[:150] + "..." if len(article.content) > 150 else article.content
                        print(f"      📄 {content_preview}")
                    print(f"      🔗 {article.url}")
                    print()
                
                if len(articles) > 3:
                    print(f"   ... and {len(articles) - 3} more articles")
            
            total_articles += len(articles)
        
        print(f"\n📊 TOTAL ARTICLES ACROSS ALL CATEGORIES: {total_articles}")

# --------- Example usage ----------
def main():
    """Example usage with your marketing URLs"""
    scraper = CategoryNewsScraper()
    
    # Add your marketing category
    marketing_urls = [
        "https://www.marketingbrew.com/?utm_source=chatgpt.com",
        "https://www.marketingdive.com/?utm_source=chatgpt.com", 
        "https://www.cxtoday.com/?utm_source=chatgpt.com",
        "https://digitalmarketinginstitute.com/blog/digital-marketing-trends-2025",
        "https://www.digitalcommerce360.com/?utm_source=chatgpt.com"
    ]
    
    scraper.add_category("Marketing", marketing_urls)
    
    # You can add more categories like this:
    # scraper.add_category("AI", ["https://aibusiness.com", "https://www.artificialintelligence-news.com"])
    # scraper.add_category("Technology", ["https://techcrunch.com", "https://www.theverge.com"])
    
    # Scrape all categories
    results = scraper.scrape_all_categories(max_articles_per_source=15)
    
    # Print summary
    scraper.print_summary()
    
    # Save to organized folders
    scraper.save_results()
    
    return results

if __name__ == "__main__":
    main()
