"""
SEC Filing Analyzer
Analyzes SEC filings based on user queries with sophisticated document processing
"""

import os
import json
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

# Import SEC-API libraries
from sec_api import QueryApi, ExtractorApi, XbrlApi, FullTextSearchApi

# Import LangChain components
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage

# Use HuggingFace embeddings when available to avoid rate limits
try:
    from langchain_huggingface import HuggingFaceEmbeddings
    HUGGINGFACE_AVAILABLE = True
except ImportError:
    HUGGINGFACE_AVAILABLE = False

# Import OpenAI embeddings
from langchain_openai import OpenAIEmbeddings

# Import FAISS for vector similarity search
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

# Initialize logger
logger = logging.getLogger('sec_analyzer')

# Section mapping for 10-K filings
SEC_10K_SECTIONS = {
    "1": {
        "name": "Business", 
        "keywords": ["business", "overview", "operations"],
        "description": "Contains information about the company's business operations, subsidiaries, markets, regulations, labor issues, operating costs, seasonal factors, and insurance matters."
    },
    "1A": {
        "name": "Risk Factors", 
        "keywords": ["risk", "factors", "uncertainties"],
        "description": "Details potential risks, external threats, possible future failures, and other risks disclosed to warn investors about factors that could affect business performance."
    },
    "1B": {
        "name": "Unresolved Staff Comments", 
        "keywords": ["unresolved", "staff", "comments"],
        "description": "Explains any comments received from SEC staff on previously filed reports that have not been resolved after an extended period of time."
    },
    "1C": {
        "name": "Cybersecurity", 
        "keywords": ["cybersecurity", "cyber", "security"],
        "description": "Explains risk management strategies for cybersecurity threats, processes for assessing and managing risks, previous incidents, and board oversight of cybersecurity matters."
    },
    "2": {
        "name": "Properties", 
        "keywords": ["properties", "facilities", "real estate"],
        "description": "Lists significant physical properties and assets of the company, including manufacturing facilities, office buildings, and land holdings."
    },
    "3": {
        "name": "Legal Proceedings", 
        "keywords": ["legal", "proceedings", "litigation"],
        "description": "Discloses significant pending lawsuits or other legal proceedings that could impact the company's financial position or operations."
    },
    "7": {
        "name": "MD&A", 
        "keywords": ["management", "discussion", "analysis", "MD&A"],
        "description": "Management's detailed discussion of operations, comparing current period versus prior periods, explaining financial condition, liquidity, capital resources, and often includes sustainability initiatives, environmental programs, and ESG information."
    },
    "7A": {
        "name": "Quantitative and Qualitative Disclosures", 
        "keywords": ["quantitative", "qualitative", "market risk"],
        "description": "Forward-looking assessments of market risks, including sensitivity analyses for interest rates, foreign exchange, commodities, and other risks."
    },
    "8": {
        "name": "Financial Statements", 
        "keywords": ["financial", "statements", "notes", "accounting"],
        "description": "Contains the core financial statements (balance sheet, income statement, cash flows), independent auditor's report, accounting policies, and explanatory notes."
    }
}

def determine_apis_to_use(query: str) -> List[str]:
    """Determine which SEC APIs to use based on query content."""
    query = query.lower()
    
    # Always use these
    apis_to_use = []
    
    # Financial terms for XBRL API
    financial_terms = [
        "revenue", "profit", "income", "earnings", "balance", 
        "cash flow", "assets", "liabilities", "financial", "accounting",
        "eps", "ebitda", "sales", "margin", "debt", "equity", "dividend",
        "fiscal", "quarter", "segment", "tax", "expense", "capital"
    ]
    
    # Section terms for Extractor API
    section_terms = [
        "risk factors", "management discussion", "md&a", "business",
        "legal", "properties", "item 1", "item 7", "item 1a",
        "overview", "strategy", "competition", "regulation", "litigation",
        "executive", "officers", "directors", "corporate governance",
        "outlook", "operations", "trends", "segment", "geographic"
    ]
    
    # Simple check for each API type
    needs_xbrl = any(term in query for term in financial_terms)
    needs_extractor = any(term in query for term in section_terms)
    
    # If nothing matches, use both for completeness
    if not needs_xbrl and not needs_extractor:
        logger.info(f"No specific match found for query: '{query}'. Using both APIs.")
        return ["XbrlToJsonApi", "ExtractorApi"]
    
    # Otherwise, add only the needed APIs
    if needs_xbrl:
        logger.info(f"Financial terms detected in query: '{query}'. Using XBRL API.")
        apis_to_use.append("XbrlToJsonApi")
    if needs_extractor:
        logger.info(f"Section terms detected in query: '{query}'. Using Extractor API.")
        apis_to_use.append("ExtractorApi")
    
    return apis_to_use

def extract_section(filing_url: str, item: str, sec_api_key: str) -> Optional[str]:
    """Extract a specific section from a filing using the Extractor API."""
    logger.info(f"Extracting section {item} from {filing_url}")
    
    try:
        extractor_api = ExtractorApi(api_key=sec_api_key)
        section_text = extractor_api.get_section(filing_url, item, "text")
        
        if section_text:
            logger.info(f"Successfully extracted section {item}")
            return section_text
        else:
            logger.warning(f"No content found for section {item}")
            return None
            
    except Exception as e:
        logger.error(f"Error extracting section {item}: {str(e)}")
        # Re-raise rate limit exceptions to be handled by the caller
        if "429" in str(e) or "rate limit" in str(e).lower():
            raise
        return None

def extract_multiple_sections(filing_url: str, items: List[str], sec_api_key: str) -> Dict[str, str]:
    """Extract multiple sections with rate limiting and retry logic."""
    if not filing_url or not items:
        return {}
    
    # Define worker function with retry logic
    def extract_worker(item):
        max_retries = 3
        base_delay = 2  # Start with a 2-second delay
        
        for attempt in range(max_retries):
            try:
                # Add delay between requests to avoid rate limiting
                if attempt > 0:
                    # Exponential backoff: 2s, 4s, 8s...
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"Retry attempt {attempt+1} for item {item}, waiting {delay}s")
                    time.sleep(delay)
                
                content = extract_section(filing_url, item, sec_api_key)
                return item, content
                
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Rate limited (429) for item {item}, will retry")
                    continue  # Try again with longer delay
                else:
                    logger.error(f"Failed to extract {item} after {attempt+1} attempts: {str(e)}")
                    return item, None
    
    # Process items sequentially to avoid overwhelming the API
    results = {}
    for item in items:
        # Add a small delay between each item request to avoid rate limiting
        time.sleep(1)  
        item, content = extract_worker(item)
        if content:  # Only add if content was found
            results[item] = content
    
    return results

def get_xbrl_data(accession_no: str, sec_api_key: str) -> Optional[Dict]:
    """Get structured XBRL data from a filing with retry logic."""
    logger.info(f"Getting XBRL data for accession number: {accession_no}")
    
    # Initialize retry parameters
    max_retries = 3
    base_delay = 2  # Start with a 2-second delay
    
    for attempt in range(max_retries):
        try:
            # Add delay before retries
            if attempt > 0:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retry attempt {attempt+1} for XBRL data, waiting {delay}s")
                time.sleep(delay)
            
            # Initialize the XbrlApi client
            xbrl_api = XbrlApi(api_key=sec_api_key)
            
            logger.debug(f"Sending XBRL API request for {accession_no}, attempt {attempt+1}")
            # The API expects the accession number as a parameter, it will handle formatting
            data = xbrl_api.xbrl_to_json(accession_no=accession_no)
            
            # Check if we got actual data
            if data and isinstance(data, dict) and len(data) > 0:
                logger.info(f"Successfully received XBRL data for {accession_no}")
                return data
            else:
                logger.warning(f"Received empty or invalid XBRL data for {accession_no}")
                # If we got an empty response, try again
                continue
                
        except Exception as e:
            logger.error(f"Error getting XBRL data for {accession_no}: {str(e)}")
            # Check for rate limit errors to apply retry logic
            if "429" in str(e) or "rate limit" in str(e).lower():
                if attempt < max_retries - 1:
                    continue
            elif "404" in str(e) or "not found" in str(e).lower():
                logger.warning(f"XBRL data not found for {accession_no}")
                return None
            
            if attempt < max_retries - 1:
                continue
            else:
                return None
    
    logger.error(f"Failed to get XBRL data after {max_retries} attempts")
    return None

def try_direct_document_access(filing_url: str, sec_api_key: str = None) -> Optional[str]:
    """Access document content directly using SEC-API.io with CIK and accession number.
    
    This method extracts the CIK and accession number from a URL and uses these 
    to access the filing directly through SEC-API.io without referencing SEC.gov.
    
    Args:
        filing_url: URL of the filing on SEC.gov
        sec_api_key: SEC API key for authentication
        
    Returns:
        Document content as text if successful, None otherwise
    """
    if not filing_url or not sec_api_key:
        return None
        
    # Try multiple patterns to extract CIK and accession number from URL
    cik_match = re.search(r'edgar/data/([0-9]+)', filing_url)
    
    # First try to match the standard format with dashes
    acc_match = re.search(r'([0-9]+-[0-9]+-[0-9]+)', filing_url)
    
    # If that fails, try to match the format without dashes
    if not acc_match:
        # Looking for accession like '000032019323000106' in URLs without dashes
        # Typically these are 18 digits, with a pattern of 10-2-6 digits
        acc_no_dashes_match = re.search(r'/([0-9]{10}[0-9]{2}[0-9]{6})/', filing_url)
        
        if acc_no_dashes_match:
            # Add dashes to format it as 10-2-6 for consistent handling
            raw_acc = acc_no_dashes_match.group(1)
            if len(raw_acc) == 18:
                accession_no = f"{raw_acc[0:10]}-{raw_acc[10:12]}-{raw_acc[12:]}"
                acc_match = True  # Not the actual match object but we just need a truthy value
    
    if not cik_match or not acc_match:
        logger.warning(f"Could not extract CIK or accession number from URL: {filing_url}")
        return None
        
    cik = cik_match.group(1)
    
    # If acc_match is not a match object, we've already formatted the accession number
    if isinstance(acc_match, bool):
        # We've already formatted it above
        pass
    else:
        accession_no = acc_match.group(1)
    
    logger.info(f"Extracted CIK: {cik}, Accession Number: {accession_no}")
    
    try:
        # Initialize the SEC-API.io QueryApi
        query_api = QueryApi(api_key=sec_api_key)
        
        # Prepare the query
        query = {
            "query": {
                "query_string": {
                    "query": f"cik:{cik} AND accessionNumber:{accession_no.replace('-', '')}"}
            },
            "from": "0",
            "size": "1"
        }
        
        logger.debug(f"Querying SEC-API for filing with CIK:{cik}, Accession:{accession_no}")
        filing_data = query_api.get_filings(query)
        
        if not filing_data.get('filings') or len(filing_data['filings']) == 0:
            logger.warning(f"No filing found for CIK:{cik}, Accession:{accession_no}")
            return None
            
        filing = filing_data['filings'][0]
        
        # Try to get the text URL from the filing
        text_url = None
        for doc_file in filing.get('documentFormatFiles', []):
            if doc_file.get('type') == 'Complete submission text file':
                text_url = doc_file.get('documentUrl')
                break
        
        if not text_url:
            logger.warning(f"Could not find text URL for filing")
            return None
            
        # Get the actual document content - use requests as the SEC-API doesn't have
        # a specific method for this, and we're accessing SEC.gov directly
        logger.debug(f"Retrieving document content from {text_url}")
        import requests  # Import here to minimize usage
        
        max_retries = 2
        base_delay = 1
        
        for attempt in range(max_retries):
            try:
                # Add exponential backoff for retries
                if attempt > 0:
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"Retry attempt {attempt+1} for document content, waiting {delay}s")
                    time.sleep(delay)
                
                doc_response = requests.get(text_url, timeout=30)
                
                if doc_response.status_code == 200:
                    content = doc_response.text
                    if content and len(content) > 100:  # Basic validation
                        logger.info(f"Successfully retrieved document content ({len(content)} characters)")
                        return content
                    else:
                        logger.warning(f"Retrieved unusable document content (length: {len(content) if content else 0})")
                        if attempt < max_retries - 1:
                            continue
                elif doc_response.status_code in (429, 503):  # Rate limit or service unavailable
                    logger.warning(f"Code {doc_response.status_code} on attempt {attempt+1}, retrying after {delay}s")
                    if attempt < max_retries - 1:
                        continue
                else:
                    logger.warning(f"Failed to get document content: {doc_response.status_code}")
                    if attempt < max_retries - 1:
                        continue
            except Exception as e:
                logger.warning(f"Error retrieving document content: {str(e)}")
                if attempt < max_retries - 1:
                    continue
        
        logger.warning(f"All attempts to retrieve document content failed")
        return None
            
    except Exception as e:
        logger.error(f"Error accessing document: {str(e)}")
        return None

def chunk_document(document_text: str, chunk_size=800, overlap=200) -> List[str]:
    """Split document into overlapping chunks for processing."""
    if not document_text:
        return []
        
    # First, try to split by common section delimiters
    chunks = []
    
    # Split by Item X.X patterns first (SEC document structure)
    # Pattern to match common section headers in SEC filings
    section_pattern = re.compile(r'(^|\n\s*)(ITEM|Item)\s+\d+(\.\d+)?[\s\-\.:]+', re.MULTILINE)
    
    # Find all section matches
    section_matches = list(section_pattern.finditer(document_text))
    
    # If we found sections, use them as chunk boundaries
    if section_matches:
        logger.info(f"Found {len(section_matches)} section headers for chunking")
        
        # Process each section
        for i, match in enumerate(section_matches):
            start_pos = match.start()
            
            # Determine end position (next section or end of document)
            if i < len(section_matches) - 1:
                end_pos = section_matches[i+1].start()
            else:
                end_pos = len(document_text)
            
            # Get the section content
            section_content = document_text[start_pos:end_pos].strip()
            
            # Skip very short sections
            if len(section_content) < 50:
                continue
                
            # For very large sections, further break them down into overlapping chunks
            if len(section_content) > chunk_size * 1.5:
                # Get the section header for context
                header_end = section_content.find('\n')
                if header_end == -1:
                    header_end = min(100, len(section_content))
                
                section_header = section_content[:header_end].strip()
                
                # Break the section into chunks
                pos = header_end
                while pos < len(section_content):
                    # Include section header with each chunk for context
                    chunk_text = section_header + "\n\n"
                    
                    # Add the chunk content
                    end = min(pos + chunk_size, len(section_content))
                    chunk_text += section_content[pos:end]
                    
                    chunks.append(chunk_text)
                    
                    # Move position with overlap
                    pos += chunk_size - overlap
                    if pos >= len(section_content):
                        break
            else:
                # Add the entire section as one chunk
                chunks.append(section_content)
    else:
        # No section headers found, fall back to simple chunking
        logger.info("No section headers found, using simple chunking")
        pos = 0
        while pos < len(document_text):
            end = min(pos + chunk_size, len(document_text))
            
            # Try to find a paragraph break to make cleaner chunks
            if end < len(document_text):
                # Look for paragraph break within a window
                window_size = min(100, end - pos)
                paragraph_break = document_text[end-window_size:end].rfind('\n\n')
                if paragraph_break != -1:
                    end = end - window_size + paragraph_break
            
            chunks.append(document_text[pos:end])
            
            # Move position with overlap
            pos += (end - pos) - overlap
            
    logger.info(f"Created {len(chunks)} chunks from document")
    return chunks

def fallback_keyword_search(query: str, chunks: List[str], top_k=3) -> List[str]:
    """Fallback method that uses simple keyword matching when vector search fails."""
    logger.info(f"Using fallback keyword search for query: {query}")
    
    # Break query into keywords
    query_keywords = query.lower().split()
    
    # Score chunks based on keyword occurrence
    chunk_scores = []
    for chunk in chunks:
        score = sum(1 for keyword in query_keywords if keyword in chunk.lower())
        chunk_scores.append((chunk, score))
    
    # Sort by score (highest first) and take top_k
    chunk_scores.sort(key=lambda x: x[1], reverse=True)
    
    # Return just the top_k chunks
    top_chunks = [chunk for chunk, _ in chunk_scores[:top_k]]
    logger.info(f"Fallback search found {len(top_chunks)} chunks")
    
    return top_chunks


def determine_relevant_sections(query_topic: str) -> List[str]:
    """Determine the most relevant sections based on the query topic.
    
    Uses semantic matching between the query topic and section descriptions
    to identify which 2-3 sections are most likely to contain relevant information.
    
    Args:
        query_topic: The topic or question to find relevant sections for
        
    Returns:
        List of section item numbers (2-3 most relevant sections)
    """
    # Default sections if we can't determine relevance
    default_sections = ["1", "7", "1A"]
    
    if not query_topic:
        logger.warning("No query topic provided, using default sections")
        return default_sections
    
    # Normalize the query
    query_lower = query_topic.lower()
    
    # Special cases for common query types
    if any(term in query_lower for term in ["financial", "revenue", "profit", "earnings", "income", "loss", "balance", "cash flow"]):
        return ["7", "8"]
    
    if any(term in query_lower for term in ["risk", "risks", "challenges", "threats", "concerns", "uncertainties"]):
        return ["1A", "7"]
    
    if any(term in query_lower for term in ["leadership", "executive", "ceo", "management", "board", "director"]):
        return ["10", "11"]
    
    if any(term in query_lower for term in ["legal", "lawsuit", "litigation", "settlement", "court", "proceedings"]):
        return ["3", "1A"]
    
    if any(term in query_lower for term in ["business", "operation", "product", "service", "market", "customer", "competition"]):
        return ["1", "7"]
    
    if any(term in query_lower for term in ["property", "real estate", "facilities", "location"]):
        return ["2"]
    
    if any(term in query_lower for term in ["cyber", "security", "data breach", "hack", "privacy"]):
        return ["1A", "1C"]
        
    # Score each section based on keyword matches
    section_scores = {}
    for item, section_info in SEC_10K_SECTIONS.items():
        score = 0
        
        # Match section name
        if section_info["name"].lower() in query_lower:
            score += 10
        
        # Match keywords
        if "keywords" in section_info:
            for keyword in section_info["keywords"]:
                if keyword.lower() in query_lower:
                    score += 5
                # Partial match (for multi-word keywords)
                elif any(part.lower() in query_lower for part in keyword.split()):
                    score += 2
        
        # Match based on description if available
        if "description" in section_info and section_info["description"]:
            desc_words = section_info["description"].lower().split()
            # Count matching words between query and description
            matching_words = sum(1 for word in query_lower.split() if word in desc_words)
            score += matching_words
        
        section_scores[item] = score
    
    # Get top 3 sections with scores > 0, or default sections
    relevant_sections = [item for item, score in sorted(section_scores.items(), key=lambda x: x[1], reverse=True) if score > 0][:3]
    
    if not relevant_sections:
        logger.warning(f"No relevant sections found for query: {query_topic}. Using defaults.")
        return default_sections
        
    logger.info(f"Identified relevant sections for query '{query_topic}': {relevant_sections}")
    return relevant_sections

def find_relevant_chunks(query: str, chunks: List[str], openai_api_key: str, top_k=3) -> List[Tuple[str, float]]:
    """Find the most relevant chunks using vector similarity."""
    if not query or not chunks:
        return []
        
    logger.info(f"Finding most relevant chunks for query: {query}")
    
    # Limit the number of chunks to process to avoid rate limits
    max_chunks_to_process = 500  # Set a reasonable limit
    if len(chunks) > max_chunks_to_process:
        logger.warning(f"Too many chunks ({len(chunks)}), sampling down to {max_chunks_to_process}")
        
        # Prioritize chunks that might have keywords related to the query
        query_keywords = query.lower().split()
        scored_chunks = []
        
        for i, chunk in enumerate(chunks):
            # Simple keyword matching score
            keyword_score = sum(1 for keyword in query_keywords if keyword in chunk.lower())
            scored_chunks.append((i, keyword_score, chunk))
        
        # Sort by keyword score and take top chunks, plus some random ones for diversity
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        top_by_keywords = [chunks[idx] for idx, _, _ in scored_chunks[:max_chunks_to_process//2]]
        
        # Add some random chunks for diversity (in case keyword matching isn't sufficient)
        import random
        random_indices = random.sample(range(len(chunks)), min(max_chunks_to_process//2, len(chunks) - max_chunks_to_process//2))
        random_chunks = [chunks[i] for i in random_indices if chunks[i] not in top_by_keywords]
        
        # Combine and ensure we're within limit
        chunks_to_process = top_by_keywords + random_chunks
        if len(chunks_to_process) > max_chunks_to_process:
            chunks_to_process = chunks_to_process[:max_chunks_to_process]
    else:
        chunks_to_process = chunks
    
    logger.info(f"Processing {len(chunks_to_process)} chunks for embedding")
    
    # Choose embeddings engine
    if HUGGINGFACE_AVAILABLE:
        try:
            # Try using HuggingFace embeddings first
            embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            logger.info("Using HuggingFace embeddings model")
        except Exception as e:
            # Fall back to OpenAI if HuggingFace has an error
            logger.warning(f"Error with HuggingFace embeddings: {str(e)}")
            logger.warning("Falling back to OpenAI embeddings")
            embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
    else:
        # If HuggingFace isn't available, use OpenAI
        logger.warning("HuggingFace embeddings not available, using OpenAI embeddings")
        embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
    
    # Use FAISS if available
    if FAISS_AVAILABLE:
        try:
            from langchain.docstore.document import Document
            from langchain.vectorstores import FAISS
            
            # Convert chunks to documents
            documents = [Document(page_content=chunk) for chunk in chunks_to_process]
            
            # Create vectorstore
            try:
                vectorstore = FAISS.from_documents(documents, embeddings)
                logger.info("Successfully created FAISS vectorstore")
                
                # Create a retriever
                retriever = vectorstore.as_retriever(search_kwargs={"k": top_k})
                
                # Perform the search
                retrieved_docs = retriever.get_relevant_documents(query)
                logger.info(f"Retrieved {len(retrieved_docs)} documents from FAISS search")
                
                # Create the result tuples with relevance scores
                matched_chunks = []
                for i, doc in enumerate(retrieved_docs):
                    content = doc.page_content
                    
                    # Calculate a dummy score since FAISS retriever doesn't return scores
                    # The earlier in the results, the higher the score
                    similarity = 1.0 - (i * 0.1)  # Simple scoring based on position
                    matched_chunks.append((content, similarity))
                
                return matched_chunks
                
            except Exception as e:
                logger.warning(f"FAISS vectorstore error: {str(e)}")
                logger.warning("Falling back to keyword-based search")
        except Exception as e:
            logger.error(f"Error in vector search setup: {str(e)}")
    
    # Fallback to keyword search if FAISS failed or isn't available
    fallback_chunks = fallback_keyword_search(query, chunks_to_process, top_k)
    
    # Convert to format with similarity scores
    return [(chunk, 1.0 - (i * 0.1)) for i, chunk in enumerate(fallback_chunks)]

def extract_document_content(filing_url: str, filing: Dict, query_topic: str, sec_api_key: str) -> Optional[str]:
    """Extract document content using the most appropriate method based on query type."""
    logger.info(f"Smart document extraction for query topic: {query_topic}")
    
    # Initialize content container
    full_content = ""
    
    # APPROACH 1: Try direct document access first using SEC-API.io
    direct_content = try_direct_document_access(filing_url, sec_api_key)
    if direct_content:
        logger.info(f"Successfully extracted document content via SEC-API.io ({len(direct_content)} characters)")
        return direct_content
    
    # APPROACH 2: Try targeted section-based extraction
    # Determine most relevant sections based on query topic
    relevant_sections = determine_relevant_sections(query_topic)
    logger.info(f"Extracting targeted sections for query: {relevant_sections}")
    
    # Extract only the most relevant 2-3 sections
    section_contents = extract_multiple_sections(filing_url, relevant_sections, sec_api_key)
    
    if section_contents and len(section_contents) > 0:
        # Combine extracted sections
        for item, content in section_contents.items():
            if content and len(content.strip()) > 0:
                section_name = SEC_10K_SECTIONS.get(item, {}).get("name", f"Section {item}")
                full_content += f"\n\nITEM {item}. {section_name.upper()}\n\n"
                full_content += content
        
        if full_content.strip():
            logger.info(f"Successfully extracted targeted sections ({len(full_content)} characters)")
        else:
            logger.warning(f"Retrieved sections had no usable content for query: {query_topic}")
    
    # APPROACH 3: Add XBRL data for financial/accounting queries
    query_topic_lower = query_topic.lower() if query_topic else ""
    if "accounting" in query_topic_lower or "financ" in query_topic_lower or "guidance" in query_topic_lower:
        logger.info(f"Adding XBRL data for financial/accounting query")
        if "accessionNo" in filing:
            try:
                xbrl_data = get_xbrl_data(filing["accessionNo"], sec_api_key)
                if xbrl_data:
                    full_content += "\n\nFINANCIAL STATEMENT DATA (XBRL):\n\n"
                    
                    # Focus on key financial statements for readability
                    statement_keys = ["StatementsOfIncome", "BalanceSheets", "StatementsOfCashFlows"]
                    for key in statement_keys:
                        if key in xbrl_data:
                            full_content += f"{key}:\n"
                            statement_data = json.dumps(xbrl_data[key], indent=2)
                            full_content += statement_data + "\n\n"
            except Exception as e:
                logger.warning(f"Could not add XBRL data: {str(e)}")
    
    if full_content:
        logger.info(f"Successfully extracted document content ({len(full_content)} characters)")
        return full_content
    else:
        logger.error("All document extraction methods failed")
        return None

def generate_response(query: str, context_data: Dict, openai_api_key: str) -> str:
    """Generate a response based on the query and retrieved context."""
    logger.info(f"Generating response for query: {query}")
    
    # Get total context data size
    context_size = 0
    context_str = ""
    
    # Add filing metadata
    metadata = context_data.get("metadata", {})
    context_str += f"Filing: {metadata.get('form_type')} for {metadata.get('company_title')} ({metadata.get('cik')})\n"
    context_str += f"Filed on: {metadata.get('filing_date', 'unknown date')}\n"
    context_str += f"For year: {metadata.get('year', 'unknown year')}\n\n"
    
    # Add chunks of content
    chunks = context_data.get("chunks", [])
    for i, (chunk, score) in enumerate(chunks):
        context_str += f"--- Document Chunk {i+1} (Relevance: {score:.2f}) ---\n\n"
        context_str += chunk + "\n\n"
        
    # Add XBRL data
    xbrl_data = context_data.get("xbrl_data", {})
    if xbrl_data:
        context_str += "--- Financial Data (XBRL) ---\n"
        
        # Focus on key financial statements
        financial_statements = ["StatementsOfIncome", "BalanceSheets", "StatementsOfCashFlows"]
        
        for statement in financial_statements:
            if statement in xbrl_data:
                context_str += f"{statement}:\n"
                # Convert dictionary to string, limiting size
                statement_data = json.dumps(xbrl_data[statement], indent=2)
                statement_preview = statement_data[:3000] + "..." if len(statement_data) > 3000 else statement_data
                context_str += f"{statement_preview}\n\n"
    
    # Get total context size
    logger.info(f"Total context size: {len(context_str)} characters")
    
    # Limit context data to avoid token limits
    if len(context_str) > 12000:
        logger.info("Context too large, truncating...")
        context_str = context_str[:5000] + "\n[...content truncated...]\n" + context_str[-5000:]
    
    # Detect query topic for specialized handling
    query_lower = query.lower()
    
    # Identify query categories
    is_financial = any(word in query_lower for word in ["financial", "revenue", "profit", "earnings", "income", "balance", "statement"])
    is_risk = any(word in query_lower for word in ["risk", "threat", "uncertainty", "litigation", "legal"])
    is_governance = any(word in query_lower for word in ["governance", "board", "executive", "management", "compensation"])
    
    # Base prompt
    base_prompt = f"""
    Based on the following information from SEC filings, answer this question:
    
    Question: {query}
    
    Filing Information:
    {context_str}
    
    You are a financial expert answering questions about SEC filings.
    All answers must be truthful, accurate, and based ONLY on the data provided.
    If the data does not fully answer the question, explicitly state what's missing.
    
    IMPORTANT GUIDELINES FOR YOUR RESPONSE:
    1. Begin your response by stating the filing date and company information
    2. Include specific facts and figures from the filing when relevant
    3. Be clear about which section or data source you're referencing
    4. Write in a conversational, helpful tone
    5. If the information is incomplete, acknowledge that
    """
    
    # Add specialized instructions based on query type
    specialized_instructions = ""
    
    if is_financial:
        specialized_instructions = """
        FINANCIAL GUIDELINES:
        - Extract and present specific financial metrics and figures
        - Compare current values with previous periods when available
        - Note any significant changes or trends
        - Present data in a structured format when appropriate
        """
    elif is_risk:
        specialized_instructions = """
        RISK FACTOR GUIDELINES:
        - Identify key risks mentioned in the filing
        - Connect risks to business operations and performance
        - Note any mitigation strategies mentioned
        """
    elif is_governance:
        specialized_instructions = """
        GOVERNANCE GUIDELINES:
        - Extract information about board composition and committees
        - Note executive compensation structures
        - Include information about corporate governance policies
        """
    
    # Combine prompt components
    prompt = base_prompt + specialized_instructions
    
    try:
        # Initialize LLM
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        
        llm = ChatOpenAI(
            model=openai_model,
            openai_api_key=openai_api_key,
            temperature=0.0
        )
        
        # Generate response
        messages = [HumanMessage(content=prompt)]
        response = llm.invoke(messages).content
        
        logger.info(f"Generated response of {len(response)} characters")
        return response
        
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return f"Error generating response: {str(e)}"

def analyze_sec_filing(query: str, filing_metadata: Dict, sec_api_key: str, openai_api_key: str) -> str:
    """Main function to analyze SEC filings based on a user query."""
    logger.info(f"Analyzing SEC filing for query: '{query}'")
    
    # Extract query topic (might be extracted parameter or the whole query)
    query_topic = filing_metadata.get("query_topic", query)
    
    # Step 1: Determine which APIs to use based on the query
    apis_to_use = determine_apis_to_use(query)
    logger.info(f"APIs selected for query: {apis_to_use}")
    
    # Step 2: Collect data from selected APIs
    context_data = {"metadata": filing_metadata}
    
    # Extract document content
    filing_url = filing_metadata.get("filing_url")
    if filing_url:
        document_text = extract_document_content(
            filing_url, 
            filing_metadata, 
            query_topic,
            sec_api_key
        )
        
        if document_text:
            # Chunk the document
            chunks = chunk_document(document_text)
            
            if chunks:
                # Find relevant chunks
                relevant_chunks = find_relevant_chunks(
                    query, 
                    chunks, 
                    openai_api_key,
                    top_k=5  # Get top 5 chunks
                )
                
                if relevant_chunks:
                    context_data["chunks"] = relevant_chunks
    
    # Get XBRL data if needed
    if "XbrlToJsonApi" in apis_to_use and filing_metadata.get("accession_no"):
        xbrl_data = get_xbrl_data(filing_metadata["accession_no"], sec_api_key)
        if xbrl_data:
            context_data["xbrl_data"] = xbrl_data
    
    # Step 3: Generate response based on collected data
    response = generate_response(query, context_data, openai_api_key)
    
    return response