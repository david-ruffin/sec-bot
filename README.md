# SEC Bot CLI

A Command Line Interface (CLI) application leveraging LangChain and specialized Octagon AI agents to answer financial research questions.

## Features

-   **Natural Language Queries:** Ask questions about public/private companies, SEC filings, earnings calls, financials, stock data, funding, deals, investors, debts, or scrape websites.
-   **Intelligent Agent:** Uses Google Gemini (via LangChain) to understand your question and select the appropriate specialized Octagon agent tool.
-   **Comprehensive Tool Access:** Integrates the full suite of Octagon agents:
    -   `octagon_sec_agent`: Public company SEC filings, CIKs, specific sections.
    -   `octagon_transcripts_agent`: Public company earnings call transcripts and commentary.
    -   `octagon_financials_agent`: Public company financial statement analysis and ratio calculations.
    -   `octagon_stock_data_agent`: Public company stock market data, prices, volume, trends.
    -   `octagon_companies_agent`: Private company information (general info, financials, employees, competitors).
    -   `octagon_funding_agent`: Private company funding rounds, investors, valuations.
    -   `octagon_deals_agent`: Public and private company M&A and IPO transactions.
    -   `octagon_investors_agent`: Investor firm details, criteria, activities.
    -   `octagon_debts_agent`: Private debt activities, borrowers, lenders.
    -   `octagon_scraper_agent`: Extract structured data from specific webpage URLs.
    -   `octagon_deep_research_agent`: Complex/broad research questions aggregating multiple sources.
-   **Direct API Integration:** Communicates directly with the Octagon API (`api.octagonagents.com`) using an OpenAI-compatible interface.
-   **Conversational Memory:** Remembers previous turns in interactive mode for follow-up questions.
-   **Modes:** Supports both interactive chat and single-question non-interactive execution.

## Architecture

-   **Orchestrator LLM:** Google Gemini (`gemini-1.5-pro-latest`) via `langchain-google-genai`.
-   **Agent Framework:** LangChain (`create_tool_calling_agent`, `AgentExecutor`).
-   **Tools:** Custom LangChain `Tool` definitions wrapping calls to specific Octagon agent models.
-   **Octagon API Client:** `langchain_openai.ChatOpenAI` configured to point to the Octagon API endpoint and use the Octagon API key.
-   **Memory:** `langchain.memory.ConversationBufferMemory`.
-   **Interface:** Python standard library (`argparse`, `input`, `print`).

## Setup

1.  **Prerequisites:**
    *   Python 3.9+ recommended.
    *   Access to Google AI API key.
    *   Access to Octagon API key (Sign up at [Octagon AI](https://app.octagonai.co/signup) and generate a key in Settings -> API Keys).

2.  **Clone the Repository (if applicable):**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

3.  **Create Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Create `.env` File:**
    *   Create a file named `.env` in the project root directory.
    *   Add your API keys:
        ```dotenv
        GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
        OCTAGON_API_KEY="YOUR_OCTAGON_API_KEY"
        # Optional: Override default Octagon base URL if needed
        # OCTAGON_API_BASE_URL="https://api.octagonagents.com/v1" 
        ```
    *   **IMPORTANT:** Add `.env` to your `.gitignore` file to avoid committing keys.

## Usage

Ensure your virtual environment is activated (`source .venv/bin/activate`).

**Interactive Mode (with Memory):**

```bash
python sec_bot_cli.py
```

Follow the prompts. Ask your questions. Type `exit` or `quit` to end.

**Non-Interactive Mode (Single Question, No Memory):**

```bash
python sec_bot_cli.py -q "Your question here"
```

Example:
```bash
python sec_bot_cli.py -q "What did Microsoft CEO say about AI in the Q4 2023 earnings call?"
python sec_bot_cli.py -q "What is the CIK for Apple Inc?"
python sec_bot_cli.py -q "What is the employee count for Anthropic (anthropic.com)?"
```

## Project Files

-   `sec_bot_cli.py`: Main application script.
-   `requirements.txt`: Project dependencies.
-   `.env`: Stores API keys (needs to be created).
-   `@roadmap.txt`: Development plan and tasks.
-   `@history.txt`: Log of development changes.
-   `README.md`: This file.

## Future Enhancements (from Roadmap)

-   Address `flake8` linting issues.
-   Refine tool descriptions/prompts for improved agent accuracy.
-   Address `LangChainDeprecationWarning` for memory initialization.
-   Develop web backend (e.g., FastAPI) for Azure deployment.
-   Create web frontend. 
