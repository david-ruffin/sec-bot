# test_azure_storage.py
import os
import io
import json
import datetime
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceNotFoundError

# Load environment variables (.env file)
load_dotenv()

def test_azure_storage_connectivity():
    """Test basic Azure Storage connectivity and container existence"""
    print("\n================ TESTING AZURE STORAGE CONNECTIVITY ================\n")
    
    # Get connection string from environment variable
    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        print("ERROR: AZURE_STORAGE_CONNECTION_STRING environment variable is not set!")
        print("Please set it to your Azure Storage connection string and try again.")
        return False
    
    try:
        # Create blob service client from connection string
        print("Creating BlobServiceClient from connection string...")
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        print("✓ Successfully created BlobServiceClient")
        
        # List containers in the storage account
        print("\nListing all containers in the storage account:")
        containers = blob_service_client.list_containers()
        container_names = [container.name for container in containers]
        
        if container_names:
            print(f"Found {len(container_names)} containers: {', '.join(container_names)}")
        else:
            print("No containers found in the storage account.")
        
        return True
    except Exception as e:
        print(f"ERROR connecting to Azure Storage: {str(e)}")
        print("Please check your connection string and network connectivity.")
        return False

def ensure_container_exists(blob_service_client, container_name):
    """Ensure a container exists, creating it if needed"""
    try:
        container_client = blob_service_client.get_container_client(container_name)
        container_client.get_container_properties()
        print(f"✓ Container '{container_name}' already exists")
        return container_client
    except ResourceNotFoundError:
        print(f"Container '{container_name}' does not exist. Creating it now...")
        container_client = blob_service_client.create_container(container_name)
        print(f"✓ Created container '{container_name}'")
        return container_client
    except Exception as e:
        print(f"ERROR accessing container '{container_name}': {str(e)}")
        raise

def test_reference_data_container(blob_service_client):
    """Test the reference-data container functionality"""
    print("\n================ TESTING REFERENCE DATA CONTAINER ================\n")
    container_name = "reference-data"
    
    try:
        # Ensure container exists
        container_client = ensure_container_exists(blob_service_client, container_name)
        
        # Test if company_tickers.json exists
        blob_name = "company_tickers.json"
        blob_client = container_client.get_blob_client(blob_name)
        
        try:
            # Check if company_tickers.json exists
            properties = blob_client.get_blob_properties()
            print(f"✓ '{blob_name}' exists (Size: {properties.size} bytes)")
            
            # Download and verify content
            download_stream = blob_client.download_blob()
            content = download_stream.readall()
            data = json.loads(content)
            
            if isinstance(data, dict) and len(data) > 0:
                sample_companies = list(data.values())[:3]
                print(f"✓ Successfully read company data. Found {len(data)} companies.")
                print("Sample companies:")
                for company in sample_companies:
                    print(f"  - {company['title']} (CIK: {company['cik_str']}, Ticker: {company['ticker']})")
            else:
                print("WARNING: company_tickers.json exists but contains no company data.")
                
        except ResourceNotFoundError:
            print(f"'{blob_name}' does not exist in the container.")
            print("You need to upload company_tickers.json to the reference-data container.")
            
            # Create a small sample file for testing
            sample_data = {
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"}
            }
            
            print("Uploading a sample company_tickers.json file for testing...")
            blob_client.upload_blob(json.dumps(sample_data), overwrite=True)
            print(f"✓ Uploaded a sample '{blob_name}' for testing purposes.")
            
        return True
    except Exception as e:
        print(f"ERROR testing reference-data container: {str(e)}")
        return False

def test_logs_container(blob_service_client):
    """Test the logs container functionality"""
    print("\n================ TESTING LOGS CONTAINER ================\n")
    container_name = "logs"
    
    try:
        # Ensure container exists
        container_client = ensure_container_exists(blob_service_client, container_name)
        
        # Create a test log file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        test_log_name = f"test_log_{timestamp}.log"
        blob_client = container_client.get_blob_client(test_log_name)
        
        # Upload initial content
        initial_content = f"Log file created for testing at {datetime.datetime.now().isoformat()}\n"
        blob_client.upload_blob(initial_content)
        print(f"✓ Created test log file '{test_log_name}'")
        
        # Append to the log file
        try:
            # Read existing content
            download_stream = blob_client.download_blob()
            existing_content = download_stream.readall().decode('utf-8')
            
            # Append new content
            new_content = f"Log entry appended at {datetime.datetime.now().isoformat()}\n"
            full_content = existing_content + new_content
            
            # Upload updated content
            blob_client.upload_blob(full_content, overwrite=True)
            print(f"✓ Successfully appended to log file '{test_log_name}'")
            
        except Exception as e:
            print(f"WARNING: Could not append to log file: {str(e)}")
        
        return True
    except Exception as e:
        print(f"ERROR testing logs container: {str(e)}")
        return False

def test_data_container(blob_service_client):
    """Test the data container functionality (for test results)"""
    print("\n================ TESTING DATA CONTAINER ================\n")
    container_name = "data"
    
    try:
        # Ensure container exists
        container_client = ensure_container_exists(blob_service_client, container_name)
        
        # Test test_results.json functionality
        blob_name = "test_results.json"
        blob_client = container_client.get_blob_client(blob_name)
        
        # Check if test_results.json exists
        try:
            properties = blob_client.get_blob_properties()
            print(f"✓ '{blob_name}' exists (Size: {properties.size} bytes)")
            
            # Download and verify content
            download_stream = blob_client.download_blob()
            content = download_stream.readall()
            data = json.loads(content)
            
            if isinstance(data, list):
                print(f"✓ Successfully read test results. Found {len(data)} results.")
            else:
                print("WARNING: test_results.json exists but doesn't contain a list.")
            
        except ResourceNotFoundError:
            print(f"'{blob_name}' does not exist. Creating a sample file...")
            
            # Create a sample test results file
            sample_data = [
                {
                    "id": f"test-{int(datetime.datetime.now().timestamp())}",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "query": "What are Apple's risk factors?",
                    "company": "Apple",
                    "formType": "10-K",
                    "year": "2023",
                    "status": "success",
                    "analysis": "This is a sample analysis result."
                }
            ]
            
            # Upload the sample file
            content_settings = ContentSettings(content_type="application/json")
            blob_client.upload_blob(json.dumps(sample_data, indent=2), 
                                    content_settings=content_settings, 
                                    overwrite=True)
            print(f"✓ Created a sample '{blob_name}' file")
        
        return True
    except Exception as e:
        print(f"ERROR testing data container: {str(e)}")
        return False

def test_filings_container(blob_service_client):
    """Test the filings container functionality (for PDF files)"""
    print("\n================ TESTING FILINGS CONTAINER ================\n")
    container_name = "filings"
    
    try:
        # Ensure container exists
        container_client = ensure_container_exists(blob_service_client, container_name)
        
        # Create a test PDF file (using a simple text file for testing)
        test_filename = f"test_filing_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        blob_client = container_client.get_blob_client(test_filename)
        
        # Create test content (simulating a PDF)
        test_content = f"This is a test filing content created at {datetime.datetime.now().isoformat()}.\n"
        test_content += "In a real scenario, this would be a PDF file content."
        
        # Upload the test file
        content_settings = ContentSettings(content_type="text/plain")
        blob_client.upload_blob(test_content, content_settings=content_settings)
        print(f"✓ Created test filing '{test_filename}'")
        
        # Get the URL
        url = blob_client.url
        print(f"✓ Filing URL: {url}")
        print("NOTE: In your app, you would use a redirect to this URL to serve the PDF file.")
        
        return True
    except Exception as e:
        print(f"ERROR testing filings container: {str(e)}")
        return False

def run_all_tests():
    """Run all Azure Storage tests"""
    print("\n========================================================")
    print("      AZURE STORAGE TEST FOR SEC FILING ANALYZER")
    print("========================================================\n")
    
    # Test connectivity first
    if not test_azure_storage_connectivity():
        print("\nCONNECTIVITY TEST FAILED. Cannot proceed with other tests.")
        return False
    
    try:
        # Get blob service client
        connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # Run container tests
        results = []
        results.append(("Reference Data Container", test_reference_data_container(blob_service_client)))
        results.append(("Logs Container", test_logs_container(blob_service_client)))
        results.append(("Data Container", test_data_container(blob_service_client)))
        results.append(("Filings Container", test_filings_container(blob_service_client)))
        
        # Print summary
        print("\n========================================================")
        print("                     TEST SUMMARY")
        print("========================================================")
        all_passed = True
        for name, result in results:
            status = "PASSED" if result else "FAILED"
            if not result:
                all_passed = False
            print(f"{name}: {status}")
        
        if all_passed:
            print("\nALL TESTS PASSED!")
            print("Your Azure Storage account is correctly configured for all parts of the SEC Filing Analyzer.")
            return True
        else:
            print("\nSOME TESTS FAILED!")
            print("Please address the issues mentioned above before proceeding.")
            return False
        
    except Exception as e:
        print(f"\nAN ERROR OCCURRED DURING TESTING: {str(e)}")
        return False

if __name__ == "__main__":
    run_all_tests()
