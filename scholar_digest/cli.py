import typer
from datetime import datetime
import os
import pandas as pd
import yaml

# Relative imports for sibling modules
from scholar_digest import mail_fetcher
from scholar_digest import parser
from scholar_digest import storage
from scholar_digest import scorer
from scholar_digest import report_builder

app = typer.Typer()

script_path = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(script_path,"config.yml")

def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

@app.command()
def fetch(since: str = None):
    """Fetch new Google Scholar emails, process, score, and generate a report."""
    typer.echo("Starting fetch process...")
    config = load_config()
    
    start_timestamp = None
    if since:
        try:
            start_timestamp = float(since)
            typer.echo(f"Fetching emails since user-provided timestamp: {datetime.fromtimestamp(start_timestamp)}")
        except ValueError:
            try:
                start_timestamp = datetime.fromisoformat(since).timestamp()
                typer.echo(f"Fetching emails since user-provided date: {datetime.fromtimestamp(start_timestamp)}")
            except ValueError:
                typer.echo(f"Error: Invalid date format for --since: {since}. Please use YYYY-MM-DD or Unix timestamp.")
                raise typer.Exit(code=1)
    else:
        start_timestamp = storage.get_last_run_timestamp()
        if start_timestamp:
            typer.echo(f"Fetching new emails since last run: {datetime.fromtimestamp(start_timestamp)}")
        else:
            typer.echo("No last run timestamp found. Fetching all Google Scholar alert emails.")

    # 1. Fetch emails
    typer.echo("Step 1: Fetching emails...")
    raw_emails = mail_fetcher.get_scholar_alert_emails(
        last_run_timestamp=start_timestamp,
        proxy_config=config.get('proxy')
    )
    if not raw_emails:
        typer.echo("No new emails found. Exiting.")
        raise typer.Exit()
    typer.echo(f"Fetched {len(raw_emails)} raw email(s).")

    # 2. Parse emails
    typer.echo("Step 2: Parsing emails...")
    all_parsed_articles = []
    latest_email_date_ts = None
    for email_data in raw_emails:
        parsed_from_email = parser.parse_scholar_email_html(email_data['body_html'])
        for article in parsed_from_email:
            article['email_id'] = email_data['id']
            article['email_date'] = email_data['date'] # This is already a timestamp
            all_parsed_articles.append(article)
        if latest_email_date_ts is None or email_data['date'] > latest_email_date_ts:
            latest_email_date_ts = email_data['date']
            
    if not all_parsed_articles:
        typer.echo("No articles found in fetched emails. Exiting.")
        if latest_email_date_ts: # Still update timestamp if emails were fetched but no articles found
             storage.update_last_run_timestamp(latest_email_date_ts)
        raise typer.Exit()
    typer.echo(f"Parsed {len(all_parsed_articles)} articles from emails.")
    # TODO: Get full abstract for articles (emails will only provide some)

    # 3. Save articles (includes deduplication)
    typer.echo("Step 3: Storing articles...")
    # save_articles expects a list of dicts. It handles deduplication against existing CSV/DB.
    storage.save_articles(all_parsed_articles, use_sqlite=True) # Or use config for sqlite preference
    
    # After saving, new articles are in the CSV. We need to load them for scoring.
    # For efficiency, ideally, save_articles would return the *newly added* articles DataFrame.
    # For now, we load all, then filter out already scored ones before sending to LLM.
    articles_for_scoring_df = storage.load_all_articles_from_csv()
    if articles_for_scoring_df.empty:
        typer.echo("No articles available in storage for scoring. This might be an error or all were duplicates.")
        if latest_email_date_ts:
            storage.update_last_run_timestamp(latest_email_date_ts)
        raise typer.Exit()

    # Filter out articles that already have a score (unless we want to re-score)
    # Assuming 'score' column exists and is None/NaN for unscored articles
    if 'score' in articles_for_scoring_df.columns:
        unscored_articles_df = articles_for_scoring_df[articles_for_scoring_df['score'].isna()].copy()
    else:
        unscored_articles_df = articles_for_scoring_df.copy()
        unscored_articles_df['score'] = None # Ensure column exists
        unscored_articles_df['reason'] = None

    if unscored_articles_df.empty:
        typer.echo("No new (unscored) articles found in storage to send to LLM.")
    else:
        typer.echo(f"{len(unscored_articles_df)} articles need scoring.")
        # 4. Score articles
        typer.echo("Step 4: Scoring articles...")
        scored_articles_df = scorer.score_articles(unscored_articles_df) # This returns a DF with new scores
        storage.update_article_scores_in_csv(scored_articles_df[scored_articles_df['score'].notna()])
        typer.echo(f"Scored {len(scored_articles_df[scored_articles_df['score'].notna()])} articles.")

    # 5. Optional Enrichment (if enabled)
    articles_for_enrichment_df = storage.load_all_articles_from_csv()
    if config.get('enrichment', {}).get('enable_web_article', False):
        typer.echo("Step 5: Enriching articles with web content (if enabled and not already done)...")
        # Filter articles that need enrichment (e.g., no full_text_summary or specific scores)
        if 'full_text_summary' not in articles_for_enrichment_df.columns:
            articles_for_enrichment_df['full_text_summary'] = None
        
        needs_enrichment_df = articles_for_enrichment_df[
            articles_for_enrichment_df['full_text_summary'].isna() &
            articles_for_enrichment_df['score'].isin([config['scoring']['high_threshold'], config['scoring']['medium_threshold']])
        ].copy()

        if not needs_enrichment_df.empty:
            enriched_df = scorer.enrich_articles_with_web_content(needs_enrichment_df)
            storage.update_article_enrichment_in_csv(enriched_df[enriched_df['full_text_summary'].notna()])
            typer.echo(f"Enriched {len(enriched_df[enriched_df['full_text_summary'].notna()])} articles.")
        else:
            typer.echo("No articles requiring web enrichment.")
    else:
        typer.echo("Step 5: Web enrichment disabled in config.")

    # 6. Build Report
    typer.echo("Step 6: Building report...")
    
    csv_file_path = os.path.join(config.get('output', {}).get('report_dir', 'reports'), "scholar_articles.csv")

    # Pass start_timestamp directly to get_articles_for_report
    # report_builder.get_articles_for_report will handle the filtering.
    articles_for_report_df = report_builder.get_articles_for_report(csv_file_path, start_timestamp=start_timestamp)

    if articles_for_report_df.empty:
        # Message depends on whether filtering was active
        if start_timestamp:
            typer.echo(f"No articles found for reporting on or after {datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d %H:%M:%S')}.")
        else:
            typer.echo("No articles found suitable for reporting by get_articles_for_report.")
        # report_main will also print its own "No articles suitable" message if it receives an empty df, but this gives more context.
        _generate_report_logic(articles_df=articles_for_report_df, config=config) # Call _generate_report_logic even if empty, it will handle it
    else:
        typer.echo(f"Proceeding to generate report with {len(articles_for_report_df)} article(s).")
        _generate_report_logic(articles_df=articles_for_report_df, config=config)

    # 7. Update last run timestamp
    if latest_email_date_ts:
        storage.update_last_run_timestamp(latest_email_date_ts)
    else:
        # Fallback if no new emails but process ran (e.g. only report was generated)
        # However, fetch command should always have a latest_email_date if it gets new emails.
        # If no emails, it exits earlier. If emails but no articles, timestamp still updated.
        # This case might not be hit in typical flow of fetch.
        # Consider updating with current time if the goal is just to mark a run.
        # For now, only update if new emails were actually processed.
        typer.echo("No new email date to update timestamp with (should not happen if emails were fetched).")

    typer.echo("Fetch process completed successfully.")

def _generate_report_logic(articles_df: pd.DataFrame = None, config: dict = None): # Renamed and no longer a Typer command, added config
    """
    Core logic to generate a report from scored data.
    If articles_df is provided, it's used directly. Otherwise, articles are loaded from CSV.
    """
    if config is None: # Load config if not passed (e.g. for standalone testing if ever needed)
        config = load_config()

    report_data_df = None

    if articles_df is not None: # Called from fetch command or new report_command
        if articles_df.empty:
            # This message will be preceded by more specific messages from fetch or report_command
            typer.echo("Report logic: Provided article list is empty.")
        else:
            typer.echo(f"Report logic: Generating report using {len(articles_df)} provided article(s).")
        report_data_df = articles_df
    else: # Should not happen if called by report_command, which pre-loads
        typer.echo("Report logic: No articles DataFrame provided. Attempting to load all from CSV.")
        csv_file = os.path.join(config.get('output', {}).get('report_dir', 'reports'), "scholar_articles.csv")
        # In standalone mode, no start_timestamp is passed, so it gets all reportable articles
        report_data_df = report_builder.get_articles_for_report(csv_file) # No start_timestamp

    if report_data_df is None or report_data_df.empty:
        typer.echo("No articles suitable for reporting were found to generate markdown.")
        # No typer.Exit() here, let the caller decide if it's fatal
        return

    markdown_content = report_builder.generate_markdown_report(report_data_df)
    report_file = report_builder.save_report(markdown_content, output_filename_base="scholar_digest_report")
    typer.echo(f"Report generated: {report_file}")


@app.command(name="report")
def report_command(): # New Typer command for standalone report
    """Generate a report from existing scored data."""
    typer.echo("Standalone report generation initiated...")
    config = load_config()
    csv_file = os.path.join(config.get('output', {}).get('report_dir', 'reports'), "scholar_articles.csv")
    
    # Load all reportable articles, no timestamp filter for standalone report
    articles_to_report_df = report_builder.get_articles_for_report(csv_file_path=csv_file) 
    
    if articles_to_report_df.empty:
        typer.echo("No articles suitable for reporting were found in the CSV.")
        # typer.Exit() # Exiting here might be too abrupt if other cleanup is needed.
        # _generate_report_logic will also state no articles found.
    
    _generate_report_logic(articles_df=articles_to_report_df, config=config)


@app.command(name="update-ts")
def update_timestamp_command(timestamp_val: str = typer.Option(None, "--value", help="Timestamp value (Unix or YYYY-MM-DD HH:MM:SS). Defaults to now.")):
    """Manually update the last run timestamp."""
    ts_to_set = None
    if timestamp_val:
        try:
            ts_to_set = float(timestamp_val)
        except ValueError:
            try:
                # More flexible date parsing
                ts_to_set = datetime.fromisoformat(timestamp_val.replace(" ", "T")).timestamp()
            except ValueError:
                typer.echo(f"Error: Invalid timestamp format: {timestamp_val}. Use Unix seconds or ISO (e.g., YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS).")
                raise typer.Exit(code=1)
    else:
        ts_to_set = datetime.now().timestamp()
    
    storage.update_last_run_timestamp(ts_to_set)
    # typer.echo(f"Last run timestamp manually updated to: {datetime.fromtimestamp(ts_to_set)}") # Redundant, update_last_run_timestamp prints this


if __name__ == "__main__":
    # This allows running `python -m scholar_digest.cli fetch` for example
    # For direct execution `python scholar_digest/cli.py`, the imports might need adjustment
    # if scholar_digest is not in PYTHONPATH. The typical usage is via the module.
    app() 