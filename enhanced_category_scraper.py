#!/usr/bin/env python3
"""
Enhanced Category Scraper that uses the original scraper logic for AI/Tech
"""

import json
from pathlib import Path
from datetime import datetime
import sys # <--- ¡IMPORTACIÓN CRUCIAL!
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
            # [CORREGIDO]
            sys.stderr.write(f"❌ Archivo de configuración {self.config_file} no encontrado.\n")
            return {}
        except Exception as e:
            # [CORREGIDO]
            sys.stderr.write(f"❌ Error leyendo configuración: {e}\n")
            return {}
    
    def scrape_category(self, category_name: str, max_articles_per_source: int = 15):
        """Scrape a specific category using the best method"""
        if category_name not in self.categories:
            # [CORREGIDO]
            sys.stderr.write(f"❌ Categoría '{category_name}' no encontrada\n")
            return []
        
        # [CORREGIDO]
        sys.stderr.write(f"🔄 Scraping {category_name}...\n")
        
        # For AI/Tech, use the original scraper logic
        if category_name == "AI/Tech":
            return self._scrape_ai_tech_enhanced(max_articles_per_source)
        else:
            # For other categories, use the regular category scraper
            return self._scrape_other_category(category_name, max_articles_per_source)
    
    def _scrape_ai_tech_enhanced(self, max_articles_per_source: int):
        """Use the original scraper for AI/Tech to get all 29 articles"""
        # [CORREGIDO]
        sys.stderr.write("🤖 Using enhanced AI/Tech scraper...\n")
        
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
        
        # [CORREGIDO]
        sys.stderr.write(f"✅ AI/Tech: {len(all_articles)} articles (enhanced)\n")
        return all_articles
    
    def _scrape_other_category(self, category_name: str, max_articles_per_source: int):
        """Use regular category scraper for other categories"""
        # [CORREGIDO]
        sys.stderr.write(f"📰 Using regular scraper for {category_name}...\n")
        
        # Use the regular category scraper
        category_scraper = CategoryNewsScraper()
        category_scraper.add_category(category_name, self.categories[category_name]['urls'])
        
        articles = category_scraper.scrape_category(category_name, max_articles_per_source)
        
        # Convert to dict format
        return [article.to_dict() for article in articles]
    
    def scrape_all_categories(self, max_articles_per_source: int = 15):
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
            
            # [CORREGIDO]
            sys.stderr.write(f"💾 Saved {len(articles)} articles to {json_file}\n")
    
    def print_summary(self):
        """Print summary of results"""
        # [CORREGIDO - TODAS las líneas]
        sys.stderr.write("\n" + "="*60 + "\n")
        sys.stderr.write("📰 ENHANCED CATEGORY NEWS SCRAPER RESULTS\n")
        sys.stderr.write("="*60 + "\n")
        
        total_articles = 0
        for category_name, articles in self.results.items():
            sys.stderr.write(f"\n📂 {category_name.upper()}\n")
            sys.stderr.write("-" * 40 + "\n")
            sys.stderr.write(f"   Total articles: {len(articles)}\n")
            
            if articles:
                for i, article in enumerate(articles[:3], 1):
                    sys.stderr.write(f"   {i}. {article['title']}\n")
                    if article.get('description'):
                        desc = article['description'][:100] + "..." if len(article['description']) > 100 else article['description']
                        sys.stderr.write(f"     📝 {desc}\n")
                    sys.stderr.write(f"     🔗 {article['url']}\n")
                
                if len(articles) > 3:
                    sys.stderr.write(f"   ... and {len(articles) - 3} more articles\n")
            
            total_articles += len(articles)
        
        sys.stderr.write(f"\n📊 TOTAL ARTICLES ACROSS ALL CATEGORIES: {total_articles}\n")

# NOTA IMPORTANTE: Dejamos esta sección 'main' como estaba, ya que el archivo news_scraper.py
# será el que llame a esta clase e imprima el JSON final a stdout.
def main():
    """Main function"""
    scraper = EnhancedCategoryScraper()
    
    # Scrape all categories
    results = scraper.scrape_all_categories(max_articles_per_source=15)
    scraper.results = results
    
    # Print summary
    scraper.print_summary()
    
    # Save results
    sys.stderr.write(f"\n💾 Saving results to organized folders...\n")
    scraper.save_results()
    
    sys.stderr.write(f"\n✅ Scraping complete! Check the 'news_by_category' folder for results.\n")
    
    # No devolvemos el JSON aquí, dejamos que news_scraper.py lo haga
    # Si ejecutaras este script directamente, esta línea sería un log que contamina stdout, 
    # pero como news_scraper.py llama a main_cli(), este bloque no se ejecuta.
    # return results

if __name__ == "__main__":
    main()
