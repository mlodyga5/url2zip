# main.py
from flask import Flask, request, Response
import requests
import base64
import os

app = Flask(__name__)

# Set a large timeout for requests (300 seconds = 5 minutes)
TIMEOUT = 300

@app.route('/enc')
def encode_file():
    url = request.args.get('url')
    if not url:
        return "URL parameter is required", 400
    
    try:
        # Stream the response to handle large files
        response = requests.get(url, stream=True, timeout=TIMEOUT)
        response.raise_for_status()
        
        # Read and encode in chunks
        chunks = []
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                chunks.append(base64.b64encode(chunk).decode('utf-8'))
        
        return ''.join(chunks)
    
    except requests.exceptions.RequestException as e:
        return str(e), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)