# Scholar Mail Digest

This system automatically fetches Google Scholar alert emails from Gmail, parses them, scores articles for relevance using an LLM, and generates a Markdown digest report.

## Features

- **Gmail Integration**: Fetches new Scholar alerts since the last run.
- **HTML Parsing**: Extracts article titles, links, and summaries from email content.
- **Deduplication**: Avoids processing the same article multiple times using a title hash.
- **LLM Scoring**: Uses Langchain with configurable LLM providers (OpenAI, Google Gemini) to score articles based on relevance (High, Medium, Low) defined by your interests. Falls back to a MockLLM if API keys are not set.
- **Configurable**: All key settings (keywords, LLM parameters, prompt templates, language) are managed in `config.yml`.
- **Storage**: Saves article data to CSV and optionally SQLite for persistence and easy access.
- **Reporting**: Generates a daily Markdown report of relevant articles, categorized by score.
- **Optional Enrichment**: Can fetch full text snippets for highly relevant articles (disabled by default).
- **CLI Interface**: Uses Typer for easy command-line operations (`fetch`, `report`, `update-ts`).

## Directory Structure

```
scholar_digest/
│  config.yml        # User configuration (keywords, prompts, LLM settings)
│  last_run.txt      # Timestamp of the last successful email fetch (Unix seconds)
│
├─ cli.py            # Typer CLI application entry point
├─ mail_fetcher.py   # Gmail API interaction for fetching emails
├─ parser.py         # HTML parsing logic for Scholar emails
├─ storage.py        # Data persistence (CSV/SQLite), deduplication, timestamp management
├─ scorer.py         # LLM scoring (OpenAI, Google) and optional web content enrichment
├─ report_builder.py # Markdown/HTML report generation using Jinja2
└─ templates/
   └─ report_template.md.j2 # Default Jinja2 template for the Markdown report
└─ README.md         # This file

.gitignore           # Specifies intentionally untracked files (e.g., credentials)
requirements.txt     # Python package dependencies
credentials.json     # Google API credentials for Gmail (SHOULD BE IN .gitignore)
token.json           # Google API token for Gmail (SHOULD BE IN .gitignore, generated on first run)
reports/             # Default directory for generated reports and data files (CSV/DB)
```

## Setup

1.  **Clone the repository (or create files as per above).**

2.  **Install Dependencies**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Google API Credentials (for Gmail)**:
    *   Go to the [Google Cloud Console](https://console.cloud.google.com/).
    *   Create a new project or select an existing one.
    *   Enable the "Gmail API".
    *   Create credentials for a "Desktop app" for an OAuth application. You will get a json file to download.
    *   Download the `credentials.json` file (The download name will be different, but with inside it will store the app's identifier and key) and place it in the root directory of this project (alongside `requirements.txt`).
    *   **Important**: Ensure `credentials.json` and `token.json` (will be generated on first run for Gmail) are listed in your `.gitignore` file.
    The required scopes for Gmail are `https://www.googleapis.com/auth/gmail.readonly`.

4.  **LLM API Keys (OpenAI and/or Google AI)**:
    To use actual LLM scoring, you need to set the respective API keys as environment variables:
    *   For **OpenAI**: Set the `OPENAI_API_KEY` environment variable.
        ```bash
        export OPENAI_API_KEY="your_openai_api_key"
        ```
        (On Windows, use `set OPENAI_API_KEY=your_openai_api_key` in Command Prompt or `$env:OPENAI_API_KEY="your_openai_api_key"` in PowerShell).
    *   For **Google AI (Gemini models)**: Set the `GOOGLE_API_KEY` environment variable.
        ```bash
        export GOOGLE_API_KEY="your_google_ai_api_key"
        ```
        (Adjust for your OS as above).
    *   If these keys are not set, the system will fall back to using the `MockChatLLM` for scoring, which provides placeholder scores.

5.  **Configure `scholar_digest/config.yml`**:
    Open `scholar_digest/config.yml` and customize it to your needs:
    *   `language`: For prompts (e.g., `en`, `zh`). (Seems not integrated, better specify it in prompt)
    *   `prompt_template`: The template for the LLM to score articles. It must request JSON output with `{"score":"High|Medium|Low","reason":"..."}`.
    *   `keywords`: 
        *   `include`: List of keywords that indicate relevance. (will be provided as part of information for llm)
        *   `exclude`: List of keywords that indicate irrelevance (will auto-score as Low).
    *   `llm`:
        *   `model`: Specify the LLM provider and model name using the format `"provider:model_name"`.
            *   Examples: `"openai:gpt-4o"`, `"openai:gpt-3.5-turbo"`,`"google:gemini-1.5-flash-latest"` (The model name should be compatible with ChatOpenAI or Google AI, depending on provider).
            *   If an unsupported provider or format is used (and API keys are set), an error will occur. 
            *   For testing without API calls, you can use `"mock:some-name"` if you uncomment the MockLLM part in `get_llm_instance` in `scorer.py` (currently, it falls back to MockLLM automatically if real LLM init fails).
        *   `temperature`: LLM temperature setting.
    *   `scoring`:
        *   `high_threshold`: The string value from LLM output considered "High" relevance.
        *   `medium_threshold`: The string value for "Medium" relevance.
    *   `enrichment`:
        *   `enable_web_article`: Set to `true` to attempt fetching a snippet of the full article text from the web for highly-rated articles. Defaults to `false`.
    *   `output`:
        *   `report_dir`: Directory where reports and data files (CSV, SQLite DB) will be stored. Defaults to `reports` in the root directory.

## Usage (CLI)

Ensure your virtual environment is activated and API keys are set if you want to use actual LLMs.
Run commands from the root directory of the project (where `requirements.txt` is).

*   **Fetch new emails, process, and generate a report (recommended)**:
    This command reads the `last_run.txt` timestamp to fetch only new emails since the last execution. On the first run (or if `last_run.txt` is missing/empty), it will attempt to fetch all emails with the `label:scholar-alerts`.
    ```bash
    python -m scholar_digest.cli fetch
    ```

*   **Fetch emails from a specific start date/time**:
    You can specify a start time using either a ISO 8601 date/datetime string or a Unix timestamp.
    ```bash
    python -m scholar_digest.cli fetch --since 2023-10-01
    python -m scholar_digest.cli fetch --since 2023-10-01T10:00:00
    python -m scholar_digest.cli fetch --since 1696140000 
    ```

*   **Generate a report from already fetched and scored data**:
    This command does not fetch new emails. It uses the existing data in `reports/scholar_articles.csv`.
    ```bash
    python -m scholar_digest.cli report
    ```

*   **Manually update the last run timestamp**:
    Sets `last_run.txt` to the current time or a specified value.
    ```bash
    python -m scholar_digest.cli update-ts
    python -m scholar_digest.cli update-ts --value 2023-10-05T12:00:00
    python -m scholar_digest.cli update-ts --value 1696492800
    ```

## Authentication Flow (Gmail)

On the first run of any command that requires Gmail access (like `fetch`), your web browser will open, prompting you to log in to your Google account and authorize the application to access your Gmail data (read-only by default).
After successful authentication, a `token.json` file will be created in the root directory. This token will be used for subsequent runs, so you won't need to re-authenticate every time for Gmail access, unless the token expires or scopes change.

## LLM Scoring Notes

- The `scorer.py` now attempts to initialize an LLM based on your `config.yml` (`llm.model` field).
- Ensure `langchain-openai` and/or `langchain-google-genai` are in `requirements.txt` and installed.
- If `OPENAI_API_KEY` (for OpenAI models) or `GOOGLE_API_KEY` (for Google models) are not set in your environment, or if the specified model cannot be loaded, the system will print an error and fall back to using `MockChatLLM` for that run. This mock LLM provides deterministic but very basic scoring based on keywords and is not suitable for production use.
- The `google:gemini-pro` model (and other Google models) require the `GOOGLE_API_KEY`.

## Customization

*   **LLM Integration**: `scholar_digest/scorer.py` handles OpenAI and Google. You can extend `get_llm_instance` to support other Langchain providers.
*   **Report Template**: Edit `scholar_digest/templates/report_template.md.j2` to change the structure or content of the Markdown report.
*   **Storage**: The system uses CSV by default and can also use SQLite. Configure this in `storage.py` if needed.

## Running Tests / Development

Each module (`mail_fetcher.py`, `parser.py`, `storage.py`, `scorer.py`, `report_builder.py`) has an `if __name__ == "__main__":` block with example usage or basic tests. You can run them individually for development and testing, e.g.:
```bash
python scholar_digest/parser.py
# For scorer.py, ensure API keys are set or expect fallback to MockLLM
python scholar_digest/scorer.py 
```
(You might need to adjust paths or ensure `credentials.json` (for Gmail) is accessible and `config.yml` is populated for some of these direct runs).

## TODO / Potential Enhancements

1. Repetition report generation (limited to current run, not historical).
2. Full abstract information gathering (currently will use only the summary from the email).
3. The test of web enrichment function
4. Other source integration (e.g., arXiv, PubMed).