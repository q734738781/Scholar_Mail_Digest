import pandas as pd
import sqlite_utils
import hashlib
import os
import yaml
from datetime import datetime

script_path = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(script_path,"config.yml")
LAST_RUN_FILE = os.path.join(script_path,"last_run.txt")


def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

config = load_config()
REPORT_DIR = config.get('output', {}).get('report_dir', 'reports')
DB_FILE = os.path.join(REPORT_DIR, "scholar_articles.db")
CSV_FILE = os.path.join(REPORT_DIR, "scholar_articles.csv")

def get_last_run_timestamp():
    try:
        with open(LAST_RUN_FILE, "r") as f:
            return float(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None

def update_last_run_timestamp(timestamp):
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    with open(LAST_RUN_FILE, "w") as f:
        f.write(str(timestamp))
    print(f"Updated last_run.txt to: {datetime.fromtimestamp(timestamp)}")

def get_title_hash(title):
    return hashlib.sha256(title.lower().encode('utf-8')).hexdigest()

def save_articles(articles_data, use_sqlite=True):
    """
    Saves new articles to CSV and optionally to SQLite, performing deduplication.
    articles_data is a list of dicts, each dict must have 'title', 'link', 'summary'.
    It can also have 'email_id', 'email_date', 'score', 'reason', 'full_text_summary'.
    """
    if not articles_data:
        print("No new articles to save.")
        return

    os.makedirs(REPORT_DIR, exist_ok=True)

    new_articles_df = pd.DataFrame(articles_data)
    if 'title' not in new_articles_df.columns:
        print("Error: 'title' column missing in articles data.")
        return

    new_articles_df["hash"] = new_articles_df["title"].apply(get_title_hash)
    new_articles_df["added_at"] = datetime.now().isoformat()
    
    # Ensure all expected columns are present, fill with None if not
    expected_cols = ['hash', 'title', 'link', 'summary', 'email_id', 'email_date', 
                     'score', 'reason', 'full_text_summary', 'added_at'] 
    for col in expected_cols:
        if col not in new_articles_df.columns:
            new_articles_df[col] = None
    
    new_articles_df = new_articles_df[expected_cols] # Reorder/select columns

    # --- CSV Storage with Deduplication ---
    if os.path.exists(CSV_FILE):
        try:
            existing_df = pd.read_csv(CSV_FILE)
            if 'hash' not in existing_df.columns and 'title' in existing_df.columns:
                 existing_df["hash"] = existing_df["title"].apply(get_title_hash)
            elif 'hash' not in existing_df.columns:
                # if no hash and no title, we can't reliably deduplicate vs old data
                print("Warning: Existing CSV has no 'hash' or 'title' column for deduplication.")
                existing_df = pd.DataFrame(columns=expected_cols)

            # Deduplicate new_articles_df against itself first
            new_articles_df = new_articles_df.drop_duplicates(subset="hash", keep="first")
            # Then, remove any articles already present in existing_df
            if not existing_df.empty and 'hash' in existing_df.columns:
                new_articles_df = new_articles_df[~new_articles_df["hash"].isin(existing_df["hash"])]
            
            if not new_articles_df.empty:
                combined_df = pd.concat([existing_df, new_articles_df], ignore_index=True)
            else:
                combined_df = existing_df
        except pd.errors.EmptyDataError:
            print(f"Warning: {CSV_FILE} is empty. Starting fresh.")
            # Deduplicate new_articles_df against itself if CSV was empty
            new_articles_df = new_articles_df.drop_duplicates(subset="hash", keep="first")
            combined_df = new_articles_df
        except Exception as e:
            print(f"Error reading or processing existing CSV {CSV_FILE}: {e}. Overwriting with new data after deduplication.")
            new_articles_df = new_articles_df.drop_duplicates(subset="hash", keep="first")
            combined_df = new_articles_df
    else:
        # Deduplicate new_articles_df against itself if CSV doesn't exist
        new_articles_df = new_articles_df.drop_duplicates(subset="hash", keep="first")
        combined_df = new_articles_df

    if not combined_df.empty:
        combined_df.to_csv(CSV_FILE, index=False)
        print(f"{len(new_articles_df)} new unique articles saved to {CSV_FILE}.")
    elif not new_articles_df.empty : # Should not happen if combined_df is empty unless error
        new_articles_df.to_csv(CSV_FILE, index=False)
        print(f"{len(new_articles_df)} new unique articles saved to {CSV_FILE} (CSV was likely empty or corrupted).")
    else:
        print(f"No new unique articles to save to {CSV_FILE}.")


    # --- SQLite Storage with Deduplication ---
    if use_sqlite:
        db = sqlite_utils.Database(DB_FILE)
        table = db["articles"]
        
        # Prepare records for SQLite, ensuring correct types for columns like email_date (timestamp)
        records_to_insert = []
        for record in new_articles_df.to_dict('records'): # new_articles_df is already deduplicated
            # Convert pandas Timestamp to float if necessary for email_date
            if 'email_date' in record and pd.notna(record['email_date']):
                if isinstance(record['email_date'], pd.Timestamp):
                    record['email_date'] = record['email_date'].timestamp()
                # Assume it's already a Unix timestamp (float or int) otherwise
            records_to_insert.append(record)

        if records_to_insert:
            try:
                table.insert_all(records_to_insert, pk="hash", ignore=True)
                print(f"Articles processed for SQLite. New unique articles inserted into {DB_FILE}")
            except Exception as e:
                print(f"Error inserting records into SQLite: {e}")
                # Fallback: try inserting one by one if batch fails (e.g. due to constraint on one row)
                # This is less efficient but more robust for debugging individual row issues.
                # For production, a more sophisticated error handling/logging might be needed.
                inserted_count = 0
                for record in records_to_insert:
                    try:
                        table.insert(record, pk="hash", ignore=True)
                        inserted_count +=1
                    except Exception as e_ind:
                        print(f"Error inserting individual record {record.get('hash', 'N/A')} into SQLite: {e_ind}")
                if inserted_count > 0:
                     print(f"{inserted_count} articles inserted individually into SQLite after batch error.")
        else:
            print(f"No new unique articles to insert into {DB_FILE}.")
            
        # Ensure table has all columns (useful if schema evolves)
        # This is a simple way; a more robust migration system would be better for complex changes.
        # for col in expected_cols:
        #     if not table.has_column(col):
        #         try:
        #             # Attempt to add with a default type; adjust as needed
        #             db.execute(f"ALTER TABLE articles ADD COLUMN {col} TEXT") 
        #             print(f"Added missing column '{col}' to SQLite table 'articles'.")
        #         except Exception as e:
        #             print(f"Could not add column {col} to SQLite: {e}")


def load_all_articles_from_csv():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=['hash', 'title', 'link', 'summary', 'score', 'reason', 'full_text_summary'])
    try:
        df = pd.read_csv(CSV_FILE)
        # Ensure critical columns exist, add them if they don't (e.g. after manual edit)
        for col in ['score', 'reason', 'full_text_summary']:
            if col not in df.columns:
                df[col] = None # or pd.NA
        return df
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=['hash', 'title', 'link', 'summary', 'score', 'reason', 'full_text_summary'])
    except Exception as e:
        print(f"Error loading articles from {CSV_FILE}: {e}")
        return pd.DataFrame(columns=['hash', 'title', 'link', 'summary', 'score', 'reason', 'full_text_summary'])

def update_article_scores_in_csv(scored_articles_df):
    """Updates existing articles in CSV with new scores and reasons."""
    if not os.path.exists(CSV_FILE) or scored_articles_df.empty:
        return

    try:
        existing_df = pd.read_csv(CSV_FILE)
        if 'hash' not in existing_df.columns:
            print("Cannot update scores: 'hash' column missing in CSV.")
            return
        
        # Set hash as index for easy update
        existing_df = existing_df.set_index('hash')
        scored_articles_df = scored_articles_df.set_index('hash')
        
        # Update score and reason where hashes match
        existing_df.update(scored_articles_df[['score', 'reason']])
        
        existing_df.reset_index().to_csv(CSV_FILE, index=False)
        print(f"Updated scores for {len(scored_articles_df)} articles in {CSV_FILE}.")

    except Exception as e:
        print(f"Error updating scores in {CSV_FILE}: {e}")

def update_article_enrichment_in_csv(enriched_articles_df):
    """Updates existing articles in CSV with new full_text_summary."""
    if not os.path.exists(CSV_FILE) or enriched_articles_df.empty:
        return
    
    try:
        existing_df = pd.read_csv(CSV_FILE)
        if 'hash' not in existing_df.columns:
            print("Cannot update enrichment: 'hash' column missing in CSV.")
            return

        existing_df = existing_df.set_index('hash')
        enriched_articles_df = enriched_articles_df.set_index('hash')

        existing_df.update(enriched_articles_df[['full_text_summary']])
        existing_df.reset_index().to_csv(CSV_FILE, index=False)
        print(f"Updated full text summary for {len(enriched_articles_df)} articles in {CSV_FILE}.")
    except Exception as e:
        print(f"Error updating enrichment in {CSV_FILE}: {e}")


if __name__ == '__main__':
    # Example Usage
    os.makedirs(REPORT_DIR, exist_ok=True)

    # Sample articles (mimicking parsed data)
    articles1 = [
        {'email_id': 'e1', 'email_date': datetime(2024,5,20,10,0,0).timestamp(), 'title': 'Test Article 1 for Storage', 'link': 'http://example.com/1', 'summary': 'Summary 1'},
        {'email_id': 'e2', 'email_date': datetime(2024,5,20,11,0,0).timestamp(), 'title': 'Test Article 2: The Sequel', 'link': 'http://example.com/2', 'summary': 'Summary 2 repeats title Test Article 2: The Sequel'},
        {'email_id': 'e3', 'email_date': datetime(2024,5,20,12,0,0).timestamp(), 'title': 'Unique Article 3', 'link': 'http://example.com/3', 'summary': 'Summary 3 is unique'}
    ]
    print("--- First save attempt ---")
    save_articles(articles1, use_sqlite=True)
    # print(f"Last run timestamp: {get_last_run_timestamp()}") # Not updated by save_articles
    # update_last_run_timestamp(datetime.now().timestamp())
    # print(f"Last run timestamp after manual update: {get_last_run_timestamp()}")

    articles2 = [
        {'email_id': 'e4', 'email_date': datetime(2024,5,21,9,0,0).timestamp(), 'title': 'Test Article 1 for Storage', 'link': 'http://example.com/1_new', 'summary': 'Summary 1 updated (but hash is same)'}, # Duplicate title
        {'email_id': 'e5', 'email_date': datetime(2024,5,21,10,0,0).timestamp(), 'title': 'Fresh Article 4', 'link': 'http://example.com/4', 'summary': 'Summary 4 is very fresh'},
    ]
    print("\n--- Second save attempt (with a duplicate title and a new one) ---")
    save_articles(articles2, use_sqlite=True)

    print("\n--- Loading all articles from CSV ---")
    all_df = load_all_articles_from_csv()
    print(all_df[['hash', 'title', 'added_at']])

    # Simulate scoring some articles
    if not all_df.empty and 'hash' in all_df.columns:
        to_score_df = all_df.sample(min(2, len(all_df))).copy() # Score 2 random articles
        to_score_df['score'] = ['High', 'Low'][:len(to_score_df)]
        to_score_df['reason'] = ['Looks promising', 'Not relevant'][:len(to_score_df)]
        print("\n--- Simulating scoring and updating CSV ---")
        print(to_score_df[['hash', 'title', 'score', 'reason']])
        update_article_scores_in_csv(to_score_df[['hash', 'score', 'reason']])
        
        all_df_after_score = load_all_articles_from_csv()
        print("\n--- All articles from CSV after scoring update ---")
        print(all_df_after_score[['hash', 'title', 'score', 'reason', 'added_at']])
    else:
        print("\nSkipping scoring simulation as no articles were loaded or 'hash' column is missing.")

    # Simulate enriching an article
    if not all_df.empty and 'hash' in all_df.columns:
        to_enrich_df = all_df.sample(min(1, len(all_df))).copy()
        to_enrich_df['full_text_summary'] = ['This is a very long summary obtained from the web.'] * len(to_enrich_df)
        print("\n--- Simulating enrichment and updating CSV ---")
        print(to_enrich_df[['hash', 'title', 'full_text_summary']])
        update_article_enrichment_in_csv(to_enrich_df[['hash', 'full_text_summary']])

        all_df_after_enrich = load_all_articles_from_csv()
        print("\n--- All articles from CSV after enrichment update ---")
        print(all_df_after_enrich[['hash', 'title', 'summary', 'full_text_summary', 'score']])
    else:
        print("\nSkipping enrichment simulation as no articles were loaded or 'hash' column is missing.")

    print(f"\nDB file is at: {DB_FILE}")
    print(f"CSV file is at: {CSV_FILE}")
    print(f"Last run file is at: {LAST_RUN_FILE}")
    print(f"To test SQLite, you can use: sqlite3 {DB_FILE} \"SELECT count(*) FROM articles;\"") 