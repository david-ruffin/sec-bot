#!/usr/bin/env python3
"""
Simple script to test PDF download logic using Azure Storage
"""

import os
import json
from dotenv import load_dotenv
from sec_api import QueryApi, PdfGeneratorApi
from azure.storage.blob import BlobServiceClient

# Load environment variables
load_dotenv()

# Get API keys and storage info from environment variables
SEC_API_KEY = os.getenv("SEC_API_KEY")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "filings")

if not SEC_API_KEY:
    raise ValueError("SEC_API_KEY environment variable is not set")

if not AZURE_STORAGE_CONNECTION_STRING:
    raise ValueError("AZURE_STORAGE_CONNECTION_STRING environment variable is not set")

def download_sec_filing_pdf(company_name, form_type, year):
    """Download an SEC filing as PDF and save to Azure Storage"""
    print(f"Downloading {form_type} filing for {company_name} from {year}...")
    
    # Initialize API clients
    query_api = QueryApi(api_key=SEC_API_KEY)
    pdf_generator_api = PdfGeneratorApi(api_key=SEC_API_KEY)
    
    # Initialize Azure Blob Storage client
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    
    # Create container if it doesn't exist
    try:
        container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
        if not container_client.exists():
            print(f"Creating container: {AZURE_STORAGE_CONTAINER_NAME}")
            container_client.create_container()
    except Exception as e:
        print(f"Error with storage container: {str(e)}")
        return None
    
    # Step 1: Find company CIK
    company_tickers_path = "reference_data/company_tickers.json"
    try:
        with open(company_tickers_path, 'r') as f:
            company_data = json.load(f)
    except FileNotFoundError:
        print(f"Company tickers file not found at {company_tickers_path}")
        return None
    
    # Search for the company by name or ticker
    company_info = None
    for _, info in company_data.items():
        if (company_name.lower() in info['title'].lower() or 
            company_name.lower() == info['ticker'].lower()):
            company_info = info
            break
    
    if not company_info:
        print(f"Could not find company information for: {company_name}")
        return None
    
    cik = str(company_info['cik_str'])
    company_title = company_info['title']
    print(f"Found company: {company_title} (CIK: {cik})")
    
    # Step 2: Search for the filing
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    query = {
        "query": {
            "query_string": {
                "query": f"cik:{cik} AND formType:\"{form_type}\" AND filedAt:[{start_date} TO {end_date}]"
            }
        },
        "from": "0",
        "size": "1",
        "sort": [{"filedAt": {"order": "desc"}}]
    }
    
    print(f"Searching for {form_type} filings for {company_title} (CIK: {cik}) in {year}...")
    
    try:
        filing_data = query_api.get_filings(query)
        
        if 'filings' not in filing_data or not filing_data['filings']:
            print(f"No {form_type} filings found for {company_title} (CIK: {cik}) in {year}")
            return None
        
        filing = filing_data['filings'][0]
        sec_url = filing.get('linkToFilingDetails')
        filing_date = filing.get('filedAt')
        
        print(f"Found {form_type} filing dated {filing_date}")
        print(f"SEC URL: {sec_url}")
        
        # Step 3: Generate PDF
        print("Converting filing to PDF format...")
        pdf_content = pdf_generator_api.get_pdf(sec_url)
        print(f"PDF generated successfully, size: {len(pdf_content)} bytes")
        
        # Create a filename from metadata
        date_str = filing_date.split('T')[0]
        blob_name = f"{cik}_{form_type}_{year}_{date_str}.pdf"
        
        # Upload to Azure Storage
        print(f"Uploading to Azure Storage container '{AZURE_STORAGE_CONTAINER_NAME}' as '{blob_name}'")
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(pdf_content, overwrite=True)
        
        # For testing, also save locally
        local_dir = "filings"
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, blob_name)
        with open(local_path, "wb") as f:
            f.write(pdf_content)
        print(f"PDF also saved locally to: {local_path}")
        
        # Return the blob name (not the full path)
        return blob_name
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

if __name__ == "__main__":
    # Test with default values
    company = "Apple"
    form_type = "10-K"
    year = "2023"
    
    blob_name = download_sec_filing_pdf(company, form_type, year)
    
    if blob_name:
        print(f"Success! PDF uploaded to Azure Storage as: {blob_name}")
        
        # Generate a SAS URL for testing
        try:
            blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
            container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
            blob_client = container_client.get_blob_client(blob_name)
            
            # Get the URL
            blob_url = blob_client.url
            print(f"PDF URL: {blob_url}")
            
            # For very simple testing, you could generate a SAS URL with limited time validity
            # from azure.storage.blob import generate_blob_sas, BlobSasPermissions
            # from datetime import datetime, timedelta
            # 
            # sas_token = generate_blob_sas(
            #     account_name=blob_service_client.account_name,
            #     container_name=AZURE_STORAGE_CONTAINER_NAME,
            #     blob_name=blob_name,
            #     account_key=blob_service_client.credential.account_key,
            #     permission=BlobSasPermissions(read=True),
            #     expiry=datetime.utcnow() + timedelta(hours=1)
            # )
            # sas_url = f"{blob_url}?{sas_token}"
            # print(f"SAS URL (valid for 1 hour): {sas_url}")
            
        except Exception as e:
            print(f"Error getting blob URL: {str(e)}")
    else:
        print("Failed to download and upload PDF.")