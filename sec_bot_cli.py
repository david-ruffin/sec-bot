import sys
import os
import re # Import regex
import argparse # Import argparse
from dotenv import load_dotenv
import json # Import standard json library
import requests  # Import requests
from langchain_google_genai import ChatGoogleGenerativeAI # Re-import Google LLM
from langchain_openai import ChatOpenAI  # Use ChatOpenAI for Octagon
from langchain_core.messages import HumanMessage
from langchain_core.exceptions import OutputParserException # Import specific exceptions
import openai # Import openai for APIError
from langchain.agents import AgentExecutor, create_tool_calling_agent # Use create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # Import prompt components
from langchain_core.tools import Tool # Import BaseTool for custom tools
from langchain.memory import ConversationBufferMemory # Import memory

# Load environment variables from .env file
load_dotenv()

def clean_response(text: str) -> str:
    """Removes citation markers like [1], [2], etc. from the text."""
    # Remove bracketed numbers
    cleaned_text = re.sub(r'\s*\[\d+\]', '', text)
    # Remove common leading tool/result markers if present
    cleaned_text = re.sub(r'^Tool: \w+, Result: ', '', cleaned_text)
    return cleaned_text.strip()

def test_direct_api_call(prompt: str, model_name: str = "octagon-sec-agent"):
    """Makes a direct HTTP POST request to the Octagon API."""
    octagon_api_key = os.getenv("OCTAGON_API_KEY")
    octagon_base_url = os.getenv("OCTAGON_API_BASE_URL", "https://api.octagonagents.com/v1")
    api_url = f"{octagon_base_url}/chat/completions"  # Standard OpenAI path

    if not octagon_api_key:
        print("Error: OCTAGON_API_KEY not found.", file=sys.stderr)
        return None

    headers = {
        "Authorization": f"Bearer {octagon_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": True  # Set stream to True
    }

    print(f"\n--- Direct API Test (Streaming) ---")
    print(f"URL: {api_url}")
    print(f"Headers: Authorization=Bearer ***, Content-Type=application/json")
    print(f"Payload: {payload}")
    print(f"----------------------------------")

    full_response_content = ""
    try:
        with requests.post(api_url, headers=headers, json=payload, timeout=60, stream=True) as response:
            response.raise_for_status()
            print(f"Direct API Response Status: {response.status_code}")
            print(f"Streaming Response Chunks:")
            for chunk in response.iter_lines():
                if chunk:
                    chunk_str = chunk.decode('utf-8')
                    print(chunk_str)
                    if chunk_str.startswith("data:"):
                        data_str = chunk_str[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            # Use standard json library
                            data_json = json.loads(data_str)
                            delta_content = data_json.get('choices', [{}])[0].get('delta', {}).get('content')
                            if delta_content:
                                full_response_content += delta_content
                        except json.JSONDecodeError:
                            print(f"  (Could not decode JSON: {data_str})", file=sys.stderr)
            
            print(f"\n--- End of Stream ---")
            print(f"Reconstructed Content: {full_response_content}")
            return full_response_content

    except requests.exceptions.RequestException as e:
        print(f"Error during direct API call: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"Response Status: {e.response.status_code}", file=sys.stderr)
            try:
                print(f"Response Body: {e.response.text}", file=sys.stderr)
            except Exception:
                pass
        return None
    except Exception as e:
        print(f"An unexpected error occurred during direct API call: {e}", file=sys.stderr)
        return None

def initialize_octagon_client(model_name: str):
    """Initialize the Octagon client using ChatOpenAI.

    Args:
        model_name: The specific Octagon agent model to use 
                    (e.g., 'octagon-sec-agent').

    Returns:
        An instance of ChatOpenAI configured for Octagon.
    """
    octagon_api_key = os.getenv("OCTAGON_API_KEY")
    octagon_base_url = os.getenv("OCTAGON_API_BASE_URL", "https://api.octagonagents.com/v1")

    if not octagon_api_key:
        print("Error: OCTAGON_API_KEY not found in .env file.", file=sys.stderr)
        sys.exit(1)

    try:
        client = ChatOpenAI(
            model=model_name,
            openai_api_key=octagon_api_key,
            openai_api_base=octagon_base_url,
            temperature=0.1 # Lower temperature for factual tasks
        )
        # Reduce console noise during runs
        # print(f"Octagon Client initialized for tool: {model_name}")
        return client
    except Exception as e:
        print(f"Error initializing Octagon client for {model_name}: {e}", file=sys.stderr)
        sys.exit(1)

def initialize_google_llm():
    """Initialize the Google Generative AI LLM client for the agent."""
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("Error: GOOGLE_API_KEY not found.", file=sys.stderr)
        sys.exit(1)
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro-latest", google_api_key=google_api_key)
        print("Google LLM (Agent Brain) Initialized successfully.")
        return llm
    except Exception as e:
        print(f"Error initializing Google LLM: {e}", file=sys.stderr)
        sys.exit(1)

def run_octagon_agent_stream(model_name: str, prompt: str) -> str:
    """Initializes a client for a specific Octagon model and streams the result."""
    client = initialize_octagon_client(model_name)
    full_response_content = ""
    error_message = f"Error executing {model_name}"
    try:
        message = HumanMessage(content=prompt)
        for chunk in client.stream([message]):
            chunk_content = chunk.content or ""
            full_response_content += chunk_content
        if not full_response_content:
            return f"{error_message}: Received empty response."
        return clean_response(full_response_content)
    except Exception as e:
        # Reduce noise, agent executor handles errors
        # print(f"\nError in {model_name} stream: {e}", file=sys.stderr)
        return f"{error_message}: {e}"

# --- Octagon Tool Definitions --- 

# Define tools using the helper function
sec_tool = Tool(
    name="octagon_sec_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-sec-agent", prompt),
    description="Use ONLY for questions about **PUBLIC** company SEC filings (like 10-K, 10-Q, 8-K), financial data reported IN filings, risk factors, CIK numbers, filing dates, or specific sections FROM filings. Input requires the PUBLIC company name/ticker. Example: 'What is the CIK for Apple Inc?' or 'What were MSFT risk factors in their 2023 10-K?'."
)

transcripts_tool = Tool(
    name="octagon_transcripts_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-transcripts-agent", prompt),
    description="Use ONLY for questions about **PUBLIC** company earnings call transcripts or investor commentary. Ask about executive statements, financial guidance, analyst questions, or topics discussed during calls. Input requires the company name and call period. Example: 'What did Microsoft CEO say about AI in the Q4 2023 earnings call?'."
)

financials_tool = Tool(
    name="octagon_financials_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-financials-agent", prompt),
    description="Use ONLY for financial statement analysis, calculating specific financial metrics, or comparing ratios for **PUBLIC** companies based on reported financials. Input requires the company, metric/ratio, and time period. Example: 'Compare the gross margins of Apple and Microsoft for fiscal year 2023'."
)

stock_data_tool = Tool(
    name="octagon_stock_data_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-stock-data-agent", prompt),
    description="Use ONLY for questions about **PUBLIC** company stock market data. Ask about stock price movements, trading volumes, market trends, valuation metrics, technical indicators, or benchmark comparisons. Input requires the company/ticker and time period. Example: 'How has NVDA stock performed compared to the S&P 500 over the last 6 months?'."
)

companies_tool = Tool(
    name="octagon_companies_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-companies-agent", prompt),
    description="Use ONLY for questions about **PRIVATE** company information (companies NOT listed on stock exchanges), like general info, financials, employee trends, sector analysis, or competitors. Providing the website URL improves results. Example: 'What is the employee count for Anthropic (anthropic.com)?' DO NOT use for public companies like Microsoft or Apple."
)

funding_tool = Tool(
    name="octagon_funding_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-funding-agent", prompt),
    description="Use ONLY for questions about **PRIVATE** company startup funding rounds, investors, valuations, and investment trends. Providing the website URL improves results. Example: 'What was OpenAI (openai.com) latest funding round size?'."
)

deals_tool = Tool(
    name="octagon_deals_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-deals-agent", prompt),
    description="Use this tool to research M&A (mergers and acquisitions) and IPO (initial public offering) transactions, prices, and valuations for both **PUBLIC and PRIVATE** companies. Specify companies involved. Example: 'What was the acquisition price when Microsoft acquired GitHub?'."
)

investors_tool = Tool(
    name="octagon_investors_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-investors-agent", prompt),
    description="Use this tool to look up information about specific **INVESTORS** (VC firms, PE firms, etc.), their investment criteria, activities, or check sizes. Providing the website URL improves results. Example: 'What is the typical check size for QED Investors (qedinvestors.com)?'"
)

debts_tool = Tool(
    name="octagon_debts_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-debts-agent", prompt),
    description="Use this tool to analyze **PRIVATE DEBT** activities, borrowers, and lenders. Example: 'List debt activities for borrower American Tower' or 'Compile debt activities for lender ING Group in Q4 2024'."
)

scraper_tool = Tool(
    name="octagon_scraper_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-scraper-agent", prompt),
    description="Use this tool ONLY to extract structured data fields or tables from a **SPECIFIC WEBPAGE URL**. Clearly state what info to extract and provide the full URL. Example: 'Extract property prices from zillow.com/san-francisco-ca/'. DO NOT use for general questions."
)

deep_research_tool = Tool(
    name="octagon_deep_research_agent",
    func=lambda prompt: run_octagon_agent_stream("octagon-deep-research-agent", prompt),
    description="Use this tool for **COMPLEX or BROAD** research questions requiring aggregation from multiple sources or analysis of trends/impacts. Use other tools first if the question fits their specific purpose. Example: 'Research the financial impact of Apple privacy changes on digital advertising companies'."
)

# --- Agent Setup --- 

def create_agent_executor(llm: ChatGoogleGenerativeAI, tools: list, memory: ConversationBufferMemory):
    """Creates the LangChain agent executor with memory."""
    # Define the prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful financial research assistant. Use the available tools to answer the user's questions accurately. Remember previous questions and answers in this conversation. Do not make up information."),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Create the agent using create_tool_calling_agent
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    # Create the agent executor
    agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools, 
        memory=memory,
        verbose=True
    )
    print("LangChain Agent Executor created with Memory.")
    return agent_executor

# --- Main Application Logic --- 
def get_agent_answer(agent_executor: AgentExecutor, question: str, chat_history: list) -> str:
    """Gets an answer from the LangChain agent executor, including chat history."""
    error_message = "Sorry, I encountered an error processing your request with the agent."
    try:
        # Include chat_history in the invoke call
        response = agent_executor.invoke({
            "input": question, 
            "chat_history": chat_history 
        })
        return response.get("output", error_message + " (No output found)")
    except Exception as e:
        print(f"\nError invoking agent: {e}", file=sys.stderr)
        return error_message + f": {e}"

def run_interactive_mode(agent_executor: AgentExecutor, memory: ConversationBufferMemory):
    """Runs the CLI in interactive mode with memory."""
    print("Welcome to SEC Bot CLI! Ask me your financial research questions.")
    print("(Using Google Gemini Agent with Octagon Tools and Memory)")
    print("Type 'exit' or 'quit' to end.")
    while True:
        try:
            user_question = input("> ")
            if user_question.lower() in ['exit', 'quit']:
                print("Exiting SEC Bot. Goodbye!")
                break
            if not user_question:
                continue
            print(f"Processing question: '{user_question}'...")
            
            # Get current chat history from memory FOR the invoke call
            current_history = memory.chat_memory.messages
            
            # Invoke the agent, which will use and update memory
            answer = get_agent_answer(agent_executor, user_question, current_history)
            print(f"Bot: {answer}")

        except EOFError:
            print("\nExiting SEC Bot. Goodbye!")
            break
        except KeyboardInterrupt:
            print("\nExiting SEC Bot. Goodbye!")
            break
        except Exception as e:
            print(f"An unexpected error occurred during interactive processing: {e}", file=sys.stderr)

def main():
    """Main function to handle argument parsing and run modes."""
    parser = argparse.ArgumentParser(description="SEC Bot CLI - Ask questions using Octagon agents.")
    parser.add_argument("-q", "--question", type=str, help="Ask a single question and exit (no memory).")
    args = parser.parse_args()

    print("Initializing SEC Bot with LangChain Agent and Memory...")
    llm = initialize_google_llm()
    
    tools = [
        sec_tool, transcripts_tool, financials_tool, stock_data_tool,
        companies_tool, funding_tool, deals_tool, investors_tool,
        debts_tool, scraper_tool, deep_research_tool
    ]
    
    # Initialize memory
    # return_messages=True is important for MessagesPlaceholder
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    
    # Create the agent executor with memory
    agent_executor = create_agent_executor(llm, tools, memory)

    if args.question:
        # Non-interactive mode - runs WITHOUT memory for simplicity
        # If memory is needed here, the invocation logic would need adjustment
        print(f"Processing question (non-interactive, no memory): '{args.question}'...")
        try:
            # Invoke directly without chat_history for single-shot question
            response = agent_executor.invoke({"input": args.question})
            answer = response.get("output", "Sorry, encountered an error.")
            print(f"\nAgent Answer:\n{answer}") 
        except Exception as e:
             print(f"\nError invoking agent: {e}", file=sys.stderr)
    else:
        # Interactive mode with memory
        run_interactive_mode(agent_executor, memory)

if __name__ == "__main__":
    main()

# --- test_direct_api_call function --- 
# ... (remains the same for reference) ...
