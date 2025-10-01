#!/usr/bin/env python3
"""
News Scraper Genérico
- Por defecto: corre todas las categorías
- Con flag: corre solo categorías específicas
- URLs definidos en categories_config.json
"""

import argparse
import sys
import json # <--- IMPORTACIÓN NECESARIA PARA JSON
from enhanced_category_scraper import EnhancedCategoryScraper

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='News Scraper - Extrae noticias por categoría',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python3 news_scraper.py                  # Correr todas las categorías
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

# --- NUEVA FUNCIÓN PARA IMPRIMIR JSON PURO A STDOUT ---
def print_final_json(results):
    """Imprime el resultado final en formato JSON a stdout (para n8n/curl)."""
    try:
        json_output = json.dumps(results, ensure_ascii=False, indent=None)
        sys.stdout.write(json_output)
        sys.stdout.flush() # Asegura que el JSON se escriba inmediatamente
    except Exception as e:
        sys.stderr.write(f"❌ Error al escribir el JSON a stdout: {e}\n")
        sys.exit(1)
# ----------------------------------------------------

def list_available_categories():
    """List available categories from config"""
    try:
        # Importamos json aquí solo si se usa, pero ya está arriba
        with open('categories_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # ***** CAMBIOS: Usar sys.stderr.write para los logs *****
        sys.stderr.write("📂 Categorías disponibles:\n")
        sys.stderr.write("=" * 30 + "\n")
        for category_name, category_data in config['categories'].items():
            sys.stderr.write(f"• {category_name}\n")
            sys.stderr.write(f"  📝 {category_data['description']}\n")
            sys.stderr.write(f"  🔗 {len(category_data['urls'])} URLs\n")
            sys.stderr.write("\n")
    except FileNotFoundError:
        sys.stderr.write("❌ No se encontró categories_config.json\n")
    except Exception as e:
        sys.stderr.write(f"❌ Error leyendo configuración: {e}\n")

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
        # [CORREGIDO]
        sys.stderr.write(f"🎯 Procesando categorías: {', '.join(categories_to_scrape)}\n")
    else:
        categories_to_scrape = None
        # [CORREGIDO] La línea que causaba el error con el emoji '🔄'
        sys.stderr.write("🔄 Procesando todas las categorías\n")
    
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
        
        # Print summary (ASUME que print_summary() ha sido corregido en el otro archivo)
        scraper.print_summary()
        
        # Save results
        # [CORREGIDO]
        sys.stderr.write(f"\n💾 Saving results to organized folders...\n")
        scraper.save_results()
        
        if results:
            # AHORA IMPRIMIMOS EL JSON A STDOUT
            print_final_json(results)
            
            # Mensajes de éxito y métricas (logs a stderr)
            # [CORREGIDO]
            sys.stderr.write(f"\n✅ Scraping completado exitosamente!\n")
            total_articles = sum(len(articles) for articles in results.values())
            sys.stderr.write(f"📊 Total de artículos: {total_articles}\n")
        else:
            # [CORREGIDO]
            sys.stderr.write("❌ No se encontraron artículos\n")
            sys.exit(1)
            
    except KeyboardInterrupt:
        # [CORREGIDO]
        sys.stderr.write("\n⏹️  Scraping cancelado por el usuario\n")
        sys.exit(1)
    except Exception as e:
        # [CORREGIDO]
        sys.stderr.write(f"❌ Error durante el scraping: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    main_cli()
