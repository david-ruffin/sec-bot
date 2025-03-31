#!/usr/bin/env python3
"""
Simple Flask app to test PDF download and display
"""

import os
from flask import Flask, render_template, send_from_directory, jsonify
from pdf_downloader import download_sec_filing_pdf  # Import from the file we created above

# Initialize Flask app
app = Flask(__name__)

# Create templates directory if it doesn't exist
os.makedirs('templates', exist_ok=True)

# Create a simple HTML template
with open('templates/viewer.html', 'w') as f:
    f.write("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SEC Filing PDF Viewer</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
            h1 { color: #333; }
            #pdfContainer { 
                width: 100%; 
                height: 800px; 
                border: 1px solid #ccc; 
                margin-top: 20px; 
            }
        </style>
    </head>
    <body>
        <h1>SEC Filing PDF Viewer</h1>
        <div id="status"></div>
        <iframe id="pdfContainer" src="{{ pdf_url }}" type="application/pdf"></iframe>
        
        <script>
            // Set status message
            document.getElementById('status').innerText = "{{ status_message }}";
            
            // Check if PDF loaded successfully
            document.getElementById('pdfContainer').onload = function() {
                document.getElementById('status').innerText = "PDF loaded successfully!";
            };
        </script>
    </body>
    </html>
    """)

@app.route('/')
def index():
    """Download and display an Apple 10-K"""
    # Download the PDF
    pdf_path = download_sec_filing_pdf("Apple", "10-K", "2023")
    
    if pdf_path:
        # Extract just the filename
        filename = os.path.basename(pdf_path)
        pdf_url = f"/filings/{filename}"
        status = "PDF downloaded successfully. Loading..."
    else:
        pdf_url = ""
        status = "Failed to download PDF."
    
    # Render the template with PDF URL
    return render_template('viewer.html', pdf_url=pdf_url, status_message=status)

@app.route('/filings/<path:filename>')
def serve_filing(filename):
    """Serve a filing PDF file."""
    return send_from_directory('filings', filename)

@app.route('/status')
def status():
    """Simple status endpoint to test if server is running"""
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # Ensure the filings directory exists
    os.makedirs('filings', exist_ok=True)
    app.run(debug=True, port=5005)