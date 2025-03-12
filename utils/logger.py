#!/usr/bin/env python3
"""
Logging utility for SEC API projects.
Provides logging functionality with Azure Blob Storage support.
"""

import logging
import os
from datetime import datetime
import sys

# Import Azure Storage SDK
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceNotFoundError

# Global logger instance
_logger = None
_current_log_blob = None

class AzureBlobHandler(logging.Handler):
    """Custom logging handler that writes logs to Azure Blob Storage."""
    
    def __init__(self, connection_string, container_name, blob_name):
        """Initialize the handler."""
        super().__init__()
        self.connection_string = connection_string
        self.container_name = container_name
        self.blob_name = blob_name
        
        # Create a buffer to accumulate log messages
        self.log_buffer = []
        self.buffer_size = 10
        
        # Initialize the blob service and container
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        
        # Create the container if it doesn't exist
        try:
            self.container_client.get_container_properties()
        except ResourceNotFoundError:
            self.blob_service_client.create_container(container_name)
            
        # Create the log blob if it doesn't exist
        self.blob_client = self.container_client.get_blob_client(blob_name)
        try:
            self.blob_client.get_blob_properties()
        except ResourceNotFoundError:
            initial_content = f"=== Log started at {datetime.now().isoformat()} ===\n\n"
            self.blob_client.upload_blob(initial_content, overwrite=True)
    
    def emit(self, record):
        """Process a log record."""
        log_entry = self.format(record) + '\n'
        self.log_buffer.append(log_entry)
        
        if len(self.log_buffer) >= self.buffer_size:
            self.flush()
    
    def flush(self):
        """Flush the buffer to Azure Blob Storage."""
        if not self.log_buffer:
            return
            
        try:
            # Get existing content
            download_stream = self.blob_client.download_blob()
            existing_content = download_stream.readall().decode('utf-8')
                
            # Append new log entries
            new_content = existing_content + ''.join(self.log_buffer)
            
            # Upload updated content
            self.blob_client.upload_blob(new_content, overwrite=True)
            
            # Clear the buffer
            self.log_buffer = []
        except Exception as e:
            # Print error but don't fall back to local logging
            sys.stderr.write(f"Error writing to Azure log: {str(e)}\n")
            raise

def get_logger(log_dir="logs"):
    """
    Get a configured logger instance that writes to Azure Blob Storage.
    
    Args:
        log_dir: Container name to store log files
        
    Returns:
        Configured logger instance
    """
    global _logger, _current_log_blob
    
    # If logger is already configured, return it
    if _logger is not None:
        return _logger
    
    # Check if we have Azure Storage configuration
    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    
    if not connection_string:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING environment variable is not set. Cannot initialize logger.")
    
    # Create logger
    _logger = logging.getLogger('sec_filing')
    _logger.setLevel(logging.INFO)
    
    # Create formatter
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Create a log blob name with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _current_log_blob = f"sec_filing_{timestamp}.log"
    
    # Create and add the Azure Blob handler
    azure_handler = AzureBlobHandler(connection_string, log_dir, _current_log_blob)
    azure_handler.setFormatter(log_formatter)
    _logger.addHandler(azure_handler)
    
    # Also add a console handler for local visibility
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.WARNING)
    _logger.addHandler(console_handler)
    
    _logger.info(f"Logger initialized with Azure Blob Storage. Logs saved to container '{log_dir}', blob '{_current_log_blob}'")
    
    return _logger

def get_current_log_name():
    """Get the name of the current log blob."""
    global _current_log_blob
    return _current_log_blob

def log_section_boundary(section_name, is_start=True):
    """Log a boundary marker for a code section."""
    logger = get_logger()
    boundary = "=" * 50
    if is_start:
        logger.info(f"\n{boundary}\nSTART: {section_name}\n{boundary}")
    else:
        logger.info(f"\n{boundary}\nEND: {section_name}\n{boundary}")