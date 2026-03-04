import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
import mistune
import yaml
import os
from datetime import datetime

CONFIG_FILE = "scholar_digest/config.yml"
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates") # Store templates in scholar_digest/templates
DEFAULT_TEMPLATE = "report_template.md.j2"

def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_articles_for_report(csv_file_path, article_hashes: set = None):
    """
    Loads articles from CSV, filters by score thresholds, and optionally by article hashes.
    Sorts them by score and then by email_date.
    If article_hashes is provided, only articles with matching hashes are included.
    """
    config = load_config()
    scoring_config = config.get('scoring', {})
    high_threshold = scoring_config.get('high_threshold', 'High')
    medium_threshold = scoring_config.get('medium_threshold', 'Medium')

    try:
        df = pd.read_csv(csv_file_path)
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_file_path}")
        return pd.DataFrame()
    except pd.errors.EmptyDataError:
        print(f"Warning: CSV file at {csv_file_path} is empty.")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error reading CSV {csv_file_path}: {e}")
        return pd.DataFrame()

    if 'score' not in df.columns:
        print("Warning: 'score' column not found in CSV. Cannot filter by score.")
        return df

    score_order = [high_threshold, medium_threshold, 'Low']
    df['score_cat'] = pd.Categorical(df['score'], categories=score_order, ordered=True)

    report_articles_df = df[df['score'].isin([high_threshold, medium_threshold])].copy()

    if article_hashes is not None and 'hash' in report_articles_df.columns:
        report_articles_df = report_articles_df[report_articles_df['hash'].isin(article_hashes)].copy()
        print(f"Filtered report to {len(report_articles_df)} article(s) matching provided hashes.")

    report_articles_df.sort_values(by=['score_cat', 'email_date'], ascending=[True, False], inplace=True)

    if 'email_date' in report_articles_df.columns:
        report_articles_df['email_date_readable'] = report_articles_df['email_date'].apply(
            lambda x: datetime.fromtimestamp(x).strftime('%Y-%m-%d %H:%M') if pd.notna(x) else 'N/A'
        )

    return report_articles_df

def generate_markdown_report(articles_df, template_name=DEFAULT_TEMPLATE):
    """Generates a Markdown report from a DataFrame of articles using a Jinja2 template."""
    if articles_df.empty:
        return "No articles to report."

    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    template_path = os.path.join(TEMPLATES_DIR, template_name)

    # Create a default template if it doesn't exist
    if not os.path.exists(template_path):
        default_md_template_content = """
# Scholar Digest Report - {{ today_date }}

## High Relevance
{% for article in articles %}
{% if article.score == high_threshold %}
### [{{ article.title }}]({{ article.link }})
- **Score**: {{ article.score }}
- **Reason**: {{ article.reason }}
{% if article.summary %}- **Scholar Summary**: {{ article.summary }}{% endif %}
{% if article.full_text_summary %}- **Full Text Snippet**: {{ article.full_text_summary | replace('\n', ' ') | truncate(250) }}{% endif %}
{% if article.email_date_readable %}- **Email Date**: {{ article.email_date_readable }}{% endif %}
{% endif %}
{% endfor %}

## Medium Relevance
{% for article in articles %}
{% if article.score == medium_threshold %}
### [{{ article.title }}]({{ article.link }})
- **Score**: {{ article.score }}
- **Reason**: {{ article.reason }}
{% if article.summary %}- **Scholar Summary**: {{ article.summary }}{% endif %}
{% if article.full_text_summary %}- **Full Text Snippet**: {{ article.full_text_summary | replace('\n', ' ') | truncate(250) }}{% endif %}
{% if article.email_date_readable %}- **Email Date**: {{ article.email_date_readable }}{% endif %}
{% endif %}
{% endfor %}

Report generated on: {{ generation_time }}
        """
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(default_md_template_content)
        print(f"Created default template: {template_path}")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(['html', 'xml', 'md'])
    )
    template = env.get_template(template_name)

    config = load_config()
    scoring_config = config.get('scoring', {})
    template_vars = {
        "articles": articles_df.to_dict(orient='records'),
        "today_date": datetime.now().strftime("%Y-%m-%d"),
        "generation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "high_threshold": scoring_config.get('high_threshold', 'High'),
        "medium_threshold": scoring_config.get('medium_threshold', 'Medium')
    }
    
    markdown_output = template.render(template_vars)
    return markdown_output

def save_report(markdown_content, output_filename_base="scholar_digest_report"):
    """Saves the markdown content to a file in the configured report directory."""
    config = load_config()
    report_dir = config.get('output', {}).get('report_dir', 'reports')
    os.makedirs(report_dir, exist_ok=True)
    
    # Filename with date: YYYY-MM-DD.md
    # report_filename_md = os.path.join(report_dir, f"{datetime.now().strftime('%Y-%m-%d')}.md")
    # Or more specific if generating multiple times a day / testing:
    report_filename_md = os.path.join(report_dir, f"{output_filename_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")

    with open(report_filename_md, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    print(f"Markdown report saved to: {report_filename_md}")

    # Optional: Convert to HTML using Mistune and save
    # html_output = mistune.html(markdown_content)
    # report_filename_html = os.path.join(report_dir, f"{output_filename_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    # with open(report_filename_html, 'w', encoding='utf-8') as f:
    #     f.write(html_output)
    # print(f"HTML report saved to: {report_filename_html}")
    return report_filename_md


if __name__ == "__main__":
    # Create a dummy CSV for testing
    config_main = load_config()
    main_report_dir = config_main.get('output', {}).get('report_dir', 'reports')
    os.makedirs(main_report_dir, exist_ok=True)
    dummy_csv_path = os.path.join(main_report_dir, "scholar_articles.csv") # Ensure it uses the configured path

    sample_report_data = {
        'hash': ['h1', 'h2', 'h3', 'h4', 'h5'],
        'title': [
            'High Impact Catalyst Research', 
            'Medium Relevance DFT Study', 
            'Low Priority Biomass Paper', 
            'Another High Score Article', 
            'Secondary Medium Article'
        ],
        'link': [
            'http://example.com/high1', 
            'http://example.com/medium1', 
            'http://example.com/low1', 
            'http://example.com/high2', 
            'http://example.com/medium2'
        ],
        'summary': [
            'Summary for high impact catalyst.', 
            'Summary for medium DFT study.', 
            'Summary for low biomass paper.', 
            'Summary for another high score.', 
            'Summary for second medium article.'
        ],
        'score': ['High', 'Medium', 'Low', 'High', 'Medium'], # Assuming these match config thresholds
        'reason': ['Excellent match', 'Relevant field', 'Out of scope', 'Good keywords', 'Related topic'],
        'email_date': [
            datetime(2024,5,20,10,0,0).timestamp(), 
            datetime(2024,5,19,11,0,0).timestamp(), 
            datetime(2024,5,18,12,0,0).timestamp(), 
            datetime(2024,5,20,9,0,0).timestamp(), 
            datetime(2024,5,19,10,0,0).timestamp()
        ],
        'full_text_summary': ['Full text snippet 1...', 'Full text snippet 2...', '', 'Full text snippet 4...', None]
    }
    sample_df = pd.DataFrame(sample_report_data)
    sample_df.to_csv(dummy_csv_path, index=False)
    print(f"Created dummy CSV for report generation: {dummy_csv_path}")

    # 1. Load articles for the report (all relevant articles)
    print("\n--- Loading all relevant articles for report --- ")
    articles_to_report_all = get_articles_for_report(dummy_csv_path)
    if not articles_to_report_all.empty:
        print(f"Loaded {len(articles_to_report_all)} articles for the report:")
        print(articles_to_report_all[['title', 'score', 'email_date_readable']])
    else:
        print("No articles loaded for the report test.")

    # Test with hash filter (e.g., only specific articles)
    print("\n--- Loading articles for report with hash filter --- ")
    test_hashes = {'h1', 'h4'}
    articles_to_report_filtered = get_articles_for_report(dummy_csv_path, article_hashes=test_hashes)
    if not articles_to_report_filtered.empty:
        print(f"Loaded {len(articles_to_report_filtered)} articles for the filtered report (hashes={test_hashes}):")
        print(articles_to_report_filtered[['title', 'score', 'email_date_readable']])
    else:
        print(f"No articles loaded for the filtered report (hashes={test_hashes}).")

    # 2. Generate Markdown (using all articles from the first load for this example)
    print("\n--- Generating Markdown Report (using all loaded articles from original test) --- ")
    if not articles_to_report_all.empty:
        markdown_report_content = generate_markdown_report(articles_to_report_all)
        print(f"Markdown report content generated (length: {len(markdown_report_content)}).")
        
        # 3. Save Report
        print("\n--- Saving Report --- ")
        saved_file = save_report(markdown_report_content, output_filename_base="daily_scholar_digest")
        print(f"Report generation process complete. Main file: {saved_file}")

        # Optional: Convert to HTML (example)
        # html_output = mistune.html(markdown_report_content)
        # html_file_path = saved_file.replace(".md", ".html")
        # with open(html_file_path, 'w', encoding='utf-8') as f_html:
        #     f_html.write(html_output)
        # print(f"HTML version saved to: {html_file_path}")
    else:
        print("Skipping report generation and saving as no articles were loaded in the initial test.")

    # To test the template creation, remove the template file from scholar_digest/templates directory
    # and re-run. 