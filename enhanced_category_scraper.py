#!/usr/bin/env python3
"""
Enhanced Category Scraper that uses the original scraper logic for AI/Tech
"""

import json
from pathlib import Path
from datetime import datetime
from rss_news_scraper import RSSNewsScraper
from category_news_scraper import CategoryNewsScraper

class EnhancedCategoryScraper:
    def __init__(self, config_file: str = "categories_config.json"):
        self.config_file = config_file
        self.categories = self._load_config()
        self.results = {}
        
    def _load_config(self):
        """Load categories from configuration file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config['categories']
        except FileNotFoundError:
            print(f"❌ Archivo de configuración {self.config_file} no encontrado.")
            return {}
        except Exception as e:
            print(f"❌ Error leyendo configuración: {e}")
            return {}
    
    def scrape_category(self, category_name: str, max_articles_per_source: int = 5):
        """Scrape a specific category using the best method"""
        if category_name not in self.categories:
            print(f"❌ Categoría '{category_name}' no encontrada")
            return []
        
        print(f"🔄 Scraping {category_name}...")
        
        # For AI/Tech, use the original scraper logic
        if category_name == "AI/Tech":
            return self._scrape_ai_tech_enhanced(max_articles_per_source)
        else:
            # For other categories, use the regular category scraper
            return self._scrape_other_category(category_name, max_articles_per_source)
    
    def _scrape_ai_tech_enhanced(self, max_articles_per_source: int):
        """Use the original scraper for AI/Tech to get all 29 articles"""
        print("🤖 Using enhanced AI/Tech scraper...")
        
        # Use the original RSS scraper
        rss_scraper = RSSNewsScraper()
        ai_results = rss_scraper.scrape_ai_sources_only(max_articles_per_source=max_articles_per_source)
        
        # Convert to the category format
        all_articles = []
        for source, articles in ai_results.items():
            for article in articles:
                article_dict = article.to_dict()
                article_dict['category'] = 'AI/Tech'  # Ensure category is set
                all_articles.append(article_dict)
        
        print(f"✅ AI/Tech: {len(all_articles)} articles (enhanced)")
        return all_articles
    
    def _scrape_other_category(self, category_name: str, max_articles_per_source: int):
        """Use regular category scraper for other categories"""
        print(f"📰 Using regular scraper for {category_name}...")
        
        # Use the regular category scraper
        category_scraper = CategoryNewsScraper()
        category_scraper.add_category(category_name, self.categories[category_name]['urls'])
        
        articles = category_scraper.scrape_category(category_name, max_articles_per_source)
        
        # Convert to dict format
        return [article.to_dict() for article in articles]
    
    def scrape_all_categories(self, max_articles_per_source: int = 5):
        """Scrape all categories"""
        all_results = {}
        
        for category_name in self.categories.keys():
            articles = self.scrape_category(category_name, max_articles_per_source)
            all_results[category_name] = articles
        
        return all_results
    
    def save_results(self, output_dir: str = "news_by_category"):
        """Save results to organized folders"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        for category_name, articles in self.results.items():
            safe_name = category_name.lower().replace(' ', '_').replace('/', '_')
            category_path = output_path / safe_name
            category_path.mkdir(parents=True, exist_ok=True)
            
            json_file = category_path / f"{safe_name}_news.json"
            
            data = {
                'category': category_name,
                'scraped_at': datetime.now().isoformat(),
                'total_articles': len(articles),
                'articles': articles
            }
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Saved {len(articles)} articles to {json_file}")
    
    def print_summary(self):
        """Print summary of results"""
        print("\n" + "="*60)
        print("📰 ENHANCED CATEGORY NEWS SCRAPER RESULTS")
        print("="*60)
        
        total_articles = 0
        for category_name, articles in self.results.items():
            print(f"\n📂 {category_name.upper()}")
            print("-" * 40)
            print(f"   Total articles: {len(articles)}")
            
            if articles:
                for i, article in enumerate(articles[:3], 1):
                    print(f"   {i}. {article['title']}")
                    if article.get('description'):
                        desc = article['description'][:100] + "..." if len(article['description']) > 100 else article['description']
                        print(f"      📝 {desc}")
                    print(f"      🔗 {article['url']}")
                
                if len(articles) > 3:
                    print(f"   ... and {len(articles) - 3} more articles")
            
            total_articles += len(articles)
        
        print(f"\n📊 TOTAL ARTICLES ACROSS ALL CATEGORIES: {total_articles}")

def main():
    """Main function"""
    scraper = EnhancedCategoryScraper()
    
    # Scrape all categories
    results = scraper.scrape_all_categories(max_articles_per_source=8)
    scraper.results = results
    
    # Print summary
    scraper.print_summary()
    
    # Save results
    print(f"\n💾 Saving results to organized folders...")
    scraper.save_results()
    
    print(f"\n✅ Scraping complete! Check the 'news_by_category' folder for results.")
    
    return results

if __name__ == "__main__":
    main()
