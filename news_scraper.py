#!/usr/bin/env python3
"""
News Scraper Genérico
- Por defecto: corre todas las categorías
- Con flag: corre solo categorías específicas
- URLs definidos en categories_config.json
"""

import argparse
import sys
from enhanced_category_scraper import EnhancedCategoryScraper

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='News Scraper - Extrae noticias por categoría',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python3 news_scraper.py                    # Correr todas las categorías
  python3 news_scraper.py --category Marketing  # Solo Marketing
  python3 news_scraper.py --category "AI/Tech"  # Solo AI/Tech
  python3 news_scraper.py --category Marketing --category "AI/Tech"  # Múltiples categorías
        """
    )
    
    parser.add_argument(
        '--category', '-c',
        action='append',
        help='Categoría específica a procesar (puede usarse múltiples veces)'
    )
    
    parser.add_argument(
        '--list-categories', '-l',
        action='store_true',
        help='Listar categorías disponibles y salir'
    )
    
    return parser.parse_args()

def list_available_categories():
    """List available categories from config"""
    try:
        import json
        with open('categories_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print("📂 Categorías disponibles:")
        print("=" * 30)
        for category_name, category_data in config['categories'].items():
            print(f"• {category_name}")
            print(f"  📝 {category_data['description']}")
            print(f"  🔗 {len(category_data['urls'])} URLs")
            print()
    except FileNotFoundError:
        print("❌ No se encontró categories_config.json")
    except Exception as e:
        print(f"❌ Error leyendo configuración: {e}")

def main_cli():
    """Main CLI function"""
    args = parse_arguments()
    
    # List categories and exit
    if args.list_categories:
        list_available_categories()
        return
    
    # Determine categories to scrape
    if args.category:
        categories_to_scrape = args.category
        print(f"🎯 Procesando categorías: {', '.join(categories_to_scrape)}")
    else:
        categories_to_scrape = None
        print("🔄 Procesando todas las categorías")
    
    # Run scraper
    try:
        scraper = EnhancedCategoryScraper()
        
        if categories_to_scrape:
            # Scrape specific categories
            results = {}
            for category in categories_to_scrape:
                articles = scraper.scrape_category(category, max_articles_per_source=8)
                results[category] = articles
        else:
            # Scrape all categories
            results = scraper.scrape_all_categories(max_articles_per_source=8)
        
        scraper.results = results
        
        # Print summary
        scraper.print_summary()
        
        # Save results
        print(f"\n💾 Saving results to organized folders...")
        scraper.save_results()
        
        if results:
            print(f"\n✅ Scraping completado exitosamente!")
            total_articles = sum(len(articles) for articles in results.values())
            print(f"📊 Total de artículos: {total_articles}")
        else:
            print("❌ No se encontraron artículos")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️  Scraping cancelado por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error durante el scraping: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main_cli()
