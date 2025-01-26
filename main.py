# main.py
import functions_framework
from flask import Request
import requests
import base64

@functions_framework.http
def enc(request: Request):
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {'Access-Control-Allow-Origin': '*'}
    
    url = request.args.get('url')
    if not url:
        return ('URL parameter is required', 400, headers)
    
    try:
        # Stream the response to handle large files
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        
        # Read and encode in chunks
        chunks = []
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                chunks.append(base64.b64encode(chunk).decode('utf-8'))
        
        return (''.join(chunks), 200, headers)
    
    except requests.exceptions.RequestException as e:
        return (str(e), 500, headers)
