import yaml
import pandas as pd
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
import os # For API keys

import time
import random
from newspaper import Article as NewspaperArticle # For web enrichment
from readability import Document as ReadabilityDocument # For web enrichment

CONFIG_FILE = "scholar_digest/config.yml"

def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

 

# Pydantic model for JSON output parsing
class ArticleScore(BaseModel):
    score: str = Field(description="The relevance score: High, Medium, or Low")
    reason: str = Field(description="A brief reason for the assigned score")

def get_llm_instance(llm_config):
    model_identifier = llm_config.get("model", "openai:gpt-3.5-turbo") # Default to openai
    temperature = llm_config.get("temperature", 0.2)
    model_kwargs = llm_config.get("model_kwargs", {})

    provider, model_name = model_identifier.split(":", 1) if ":" in model_identifier else ("openai", model_identifier)

    

    if provider.lower() == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set for OpenAI models.")
        print(f"Using OpenAI model: {model_name} with temperature: {temperature}")
        return ChatOpenAI(model_name=model_name, temperature=temperature, openai_api_key=api_key, **model_kwargs)
    elif provider.lower() == "google":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set for Google models.")
        print(f"Using Google model: {model_name} with temperature: {temperature}")
        # For Google, model_name is often just like 'gemini-pro'
        return ChatGoogleGenerativeAI(model=model_name, temperature=temperature, google_api_key=api_key, convert_system_message_to_human=True, **model_kwargs)
    # Add other providers here as elif blocks
    # Example MockLLM as fallback or for testing if no provider matches
    # elif provider.lower() == "mock":
    #     print(f"Using MockLLM: {model_name} with temperature: {temperature}")
    #     return MockChatLLM(model_name=model_name, temperature=temperature)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Supported: openai, google.")

# Mock LLM class for demonstration/testing if actual LLMs are not configured
class MockChatLLM:
    def __init__(self, model_name="mock-model", temperature=0.2):
        self.model_name = model_name
        self.temperature = temperature
        print(f"MockLLM initialized: {model_name}, temp: {temperature}")

    def invoke(self, prompt_input):
        time.sleep(random.uniform(0.1, 0.3))
        text_input = ""
        if isinstance(prompt_input, dict) and 'text' in prompt_input: # Compatibility with old test
            text_input = prompt_input.get('text', '').lower()
        elif hasattr(prompt_input, 'to_messages'): # Langchain prompt value
            messages = prompt_input.to_messages()
            for msg in messages:
                if hasattr(msg, 'content') and isinstance(msg.content, str):
                    text_input += msg.content.lower() + " "
        
        score = "Low"
        reason = "Mock reason: Default low relevance."
        if "catalyst" in text_input or "dft" in text_input or "single-atom" in text_input or "co2rr" in text_input:
            score = "High"
            reason = "Mock reason: Contains primary keywords."
        elif "review" in text_input:
            score = "Medium"
            reason = "Mock reason: Appears to be a review article."
        if "battery" in text_input or "biomass" in text_input:
            score = "Low"
            reason = "Mock reason: Contains exclusion keywords (mock)."
        return {"score": score, "reason": reason}

def score_articles(articles_df):
    """
    Scores articles based on title and summary using an LLM.
    articles_df should be a pandas DataFrame with at least 'title' and 'summary' columns.
    Returns a DataFrame with added 'score' and 'reason' columns.
    """
    config = load_config()
    
    prompt_template_str = config.get("prompt_template", "")
    llm_config = config.get("llm", {})
    
    try:
        llm = get_llm_instance(llm_config)
    except ValueError as e:
        print(f"Error initializing LLM: {e}. Falling back to MockLLM for this run.")
        # Fallback to MockLLM if actual LLM setup fails (e.g. API key missing)
        llm = MockChatLLM(model_name=llm_config.get("model", "mock-fallback"), temperature=llm_config.get("temperature", 0.2))
    except ImportError as e:
        print(f"ImportError for LLM: {e}. Ensure langchain-openai and langchain-google-genai are installed. Falling back to MockLLM.")
        llm = MockChatLLM(model_name=llm_config.get("model", "mock-import-fallback"), temperature=llm_config.get("temperature", 0.2))


    parser = JsonOutputParser(pydantic_object=ArticleScore)
    
    prompt = PromptTemplate(
        template=prompt_template_str + "\n{format_instructions}\nArticle Title: {title}\nArticle Summary: {summary}",
        input_variables=["title", "summary"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    
    chain = prompt | llm | parser
    
    results = []
    if articles_df.empty:
        print("No articles to score.")
        return articles_df

    print(f"Scoring {len(articles_df)} articles using LLM ({llm_config.get('model')})...")

    # Parallel processing support
    scoring_cfg = config.get('scoring', {}) or {}
    parallel_cfg = scoring_cfg.get('parallel', {}) or {}
    enable_parallel = bool(parallel_cfg.get('enable', False))
    max_workers = int(parallel_cfg.get('workers', 4))

    include_keywords = config.get('keywords', {}).get('include', [])
    exclude_keywords = config.get('keywords', {}).get('exclude', [])

    def score_one(row_dict):
        title_local = str(row_dict.get('title') if pd.notna(row_dict.get('title')) else "")
        summary_local = str(row_dict.get('summary') if pd.notna(row_dict.get('summary')) else "")
        text_to_check_local = (title_local + " " + summary_local).lower()

        if exclude_keywords:
            for ex_kw in exclude_keywords:
                if ex_kw.lower() in text_to_check_local:
                    return {'hash': row_dict.get('hash'), 'score': 'Low', 'reason': f'Auto-excluded by keyword: {ex_kw}'}
        try:
            response_local = chain.invoke({"title": title_local, "summary": summary_local})
            return {'hash': row_dict.get('hash'), 'score': response_local['score'], 'reason': response_local['reason']}
        except Exception as e_local:
            print(f"Error scoring article '{title_local[:50]}...': {e_local}")
            return {'hash': row_dict.get('hash'), 'score': 'Error', 'reason': str(e_local)}

    if enable_parallel and max_workers > 1:
        print(f"Parallel scoring enabled: workers={max_workers}")
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            rows = [row._asdict() if hasattr(row, "_asdict") else row.to_dict() for _, row in articles_df.iterrows()]
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_hash = {executor.submit(score_one, row_dict): row_dict.get('hash') for row_dict in rows}
                for future in as_completed(future_to_hash):
                    try:
                        result = future.result()
                        if result is not None:
                            results.append(result)
                    except Exception as e:
                        print(f"Unexpected error in parallel worker: {e}")
        except Exception as e:
            print(f"Parallel scoring failed, falling back to sequential processing. Error: {e}")
            for _, row in articles_df.iterrows():
                results.append(score_one(row.to_dict()))
    else:
        for _, row in articles_df.iterrows():
            results.append(score_one(row.to_dict()))
    
    scored_df = pd.DataFrame(results)
    
    if 'hash' in articles_df.columns and not scored_df.empty and 'hash' in scored_df.columns:
        # Ensure 'hash' in scored_df is not all None if it came from rows where scoring was skipped
        scored_df_filtered = scored_df.dropna(subset=['hash'])
        if not scored_df_filtered.empty:
            articles_df = articles_df.merge(scored_df_filtered, on='hash', how='left', suffixes= ('','_update'))
            
            # Consolidate score and reason columns after merge
            if 'score_update' in articles_df.columns:
                articles_df['score'] = articles_df['score_update'].fillna(articles_df['score'])
                articles_df.drop(columns=['score_update'], inplace=True)
            if 'reason_update' in articles_df.columns:
                articles_df['reason'] = articles_df['reason_update'].fillna(articles_df['reason'])
                articles_df.drop(columns=['reason_update'], inplace=True)
    elif not scored_df.empty:
        if len(articles_df) == len(scored_df):
            articles_df['score'] = scored_df['score']
            articles_df['reason'] = scored_df['reason']
        else:
            print("Warning: Could not reliably merge scores due to missing hash or length mismatch, and no hash column in input.")

    return articles_df

def enrich_articles_with_web_content(articles_df):
    """
    Fetches full article text using newspaper3k or readability-lxml and generates a summary.
    Updates articles_df with a 'full_text_summary' column.
    """
    config = load_config()
    if not config.get('enrichment', {}).get('enable_web_article', False):
        print("Web article enrichment is disabled in config.")
        if 'full_text_summary' not in articles_df.columns:
             articles_df['full_text_summary'] = pd.NA
        return articles_df

    if articles_df.empty or 'link' not in articles_df.columns:
        print("No articles or links available for enrichment.")
        if 'full_text_summary' not in articles_df.columns:
             articles_df['full_text_summary'] = pd.NA
        return articles_df

    print(f"Enriching {len(articles_df)} articles with web content...")
    full_summaries = []
    for index, row in articles_df.iterrows():
        url = row['link']
        if pd.isna(url):
            print(f"  Skipping enrichment for article with no link (index {index}).")
            full_summaries.append(pd.NA)
            continue

        print(f"Fetching and parsing: {url}")
        full_summary = "Could not retrieve full text." # Default
        try:
            article = NewspaperArticle(url)
            article.download()
            article.parse()
            if article.text:
                full_summary = article.text[:1000] + "..." if len(article.text) > 1000 else article.text
                print(f"  Successfully parsed with newspaper3k. Length: {len(article.text)}")
            else:
                import requests
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                doc = ReadabilityDocument(response.content)
                from bs4 import BeautifulSoup
                cleaned_html = doc.summary()
                soup = BeautifulSoup(cleaned_html, 'html.parser')
                text_content = soup.get_text(separator=' ', strip=True)
                if text_content:
                    full_summary = text_content[:1000] + "..." if len(text_content) > 1000 else text_content
                    print(f"  Successfully parsed with readability-lxml. Length: {len(text_content)}")
                else:
                    print(f"  Could not extract text with readability-lxml either.")

        except Exception as e:
            print(f"  Error fetching/parsing article {url}: {e}")
            full_summary = f"Error retrieving full text: {str(e)[:100]}"
        
        full_summaries.append(full_summary)
    
    articles_df['full_text_summary'] = full_summaries
    return articles_df

if __name__ == '__main__':
    # Ensure OPENAI_API_KEY and GOOGLE_API_KEY are set in your environment to test actual LLMs
    # Otherwise, it will use MockLLM or fail if MockLLM is commented out in get_llm_instance
    
    # Create a sample DataFrame mimicking data from storage.py
    sample_data = {
        'hash': ['h1', 'h2', 'h3', 'h4', 'h5'],
        'title': [
            'Revolutionary Single-Atom Catalyst for CO2RR via Advanced DFT',
            'A Comprehensive Review of Modern Battery Technologies',
            'Exploring the Potential of Biomass in Energy Production',
            'Unrelated Study on Penguin Behavior in Antarctica',
            'Deep Learning for Catalyst Design: A new Frontier'
        ],
        'summary': [
            'This paper details a new single-atom catalyst (SAC) that shows remarkable performance for CO2RR. DFT calculations support the findings.',
            'This review covers lithium-ion, solid-state, and flow batteries. Excludes DFT.',
            'Biomass conversion processes and their viability for sustainable energy. Excludes catalyst research.',
            'A field study observing Adélie penguin mating rituals. No mention of catalysts or DFT.',
            'Utilizing recurrent neural networks and DFT simulations to predict novel catalyst structures for CO2RR.'
        ],
        'link': [
            'http://example.com/catalyst-dft', 
            'http://example.com/battery-review', 
            'http://example.com/biomass-article', 
            'http://example.com/penguin-study',
            'http://example.com/ai-catalyst'
        ]
    }
    sample_articles_df = pd.DataFrame(sample_data)

    print("--- Scoring Articles --- ")
    # To test a specific provider, you can temporarily modify the config loaded by score_articles
    # or, more directly for this test, override the llm_config passed to get_llm_instance.
    # Example: config['llm']['model'] = 'openai:gpt-3.5-turbo' or 'google:gemini-pro'
    # Make sure API keys are set in your environment.
    
    # Test with default from config.yml (or MockLLM if API keys missing/config incorrect)
    print("\nTesting with LLM specified in config.yml (or fallback MockLLM)")
    scored_df_config = score_articles(sample_articles_df.copy()) 
    print(scored_df_config[['title', 'score', 'reason']])

    # --- Test with Mock LLM explicitly (if you want to ensure it works) ---
    # print("\n--- Scoring Articles (with explicit Mock LLM) ---")
    # original_config = load_config()
    # temp_mock_config = original_config.copy()
    # temp_mock_config['llm'] = {"model": "mock:my-mock", "temperature": 0.1}
    # # Temporarily write a mock config for scorer to load
    # with open(CONFIG_FILE, 'w', encoding='utf-8') as f_temp_mock:
    #     yaml.dump(temp_mock_config, f_temp_mock)
    # scored_df_mock = score_articles(sample_articles_df.copy()) 
    # print(scored_df_mock[['title', 'score', 'reason']])
    # # Restore original config
    # with open(CONFIG_FILE, 'w', encoding='utf-8') as f_orig:
    #    yaml.dump(original_config, f_orig)
    # print("Restored original config.yml")

    print("\n--- Enriching Articles with Web Content (if enabled in config.yml) ---")
    config_check = load_config()
    enriched_df_final = scored_df_config # Use the DataFrame from the config/fallback LLM run
    if config_check.get('enrichment', {}).get('enable_web_article', False):
        print("Web enrichment is ENABLED in config.yml, proceeding with test...")
        enriched_df_final = enrich_articles_with_web_content(enriched_df_final.copy())
        print(enriched_df_final[['title', 'full_text_summary']])
    else:
        print("Web enrichment is DISABLED in config.yml. Skipping web enrichment test.")
        if 'full_text_summary' not in enriched_df_final.columns:
            enriched_df_final['full_text_summary'] = pd.NA
        print(enriched_df_final[['title', 'full_text_summary']])