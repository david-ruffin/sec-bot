#!/usr/bin/env python3
"""
Simplified logging utility for SEC API projects.
Provides a single log file for all components.
"""

import logging
import os
from datetime import datetime

# Global logger instance
_logger = None

def get_logger(log_dir="Logs"):
    """
    Get a configured logger instance. Creates a new logger if one doesn't exist.
    All components use the same logger to write to a single file.
    
    Args:
        log_dir: Directory to store log file
        
    Returns:
        Configured logger instance
    """
    global _logger
    
    # If logger is already configured, return it
    if _logger is not None:
        return _logger
        
    # Create log directory if it doesn't exist
    log_dir_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), log_dir)
    os.makedirs(log_dir_path, exist_ok=True)
    
    # Create log filename with timestamp
    log_file = os.path.join(log_dir_path, f'sec_filing_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # Configure logger
    _logger = logging.getLogger('sec_filing')
    _logger.setLevel(logging.INFO)
    
    # Create formatters - include component name in the message instead of logger name
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Create file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(file_formatter)
    _logger.addHandler(file_handler)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.WARNING)  # Console only shows WARNING and above
    _logger.addHandler(console_handler)
    
    _logger.info(f"Logger initialized. Logs will be saved to: {log_file}")
    
    return _logger

# Utility function to log section boundaries
def log_section_boundary(section_name, is_start=True):
    """
    Log a boundary marker for a code section (start or end)
    
    Args:
        section_name: Name of the section
        is_start: True if this is the start of a section, False if it's the end
    """
    logger = get_logger()
    boundary = "=" * 50
    if is_start:
        logger.info(f"\n{boundary}\nSTART: {section_name}\n{boundary}")
    else:
        logger.info(f"\n{boundary}\nEND: {section_name}\n{boundary}")