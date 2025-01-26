import functions_framework
from flask import Request, Response
import requests
import base64

@functions_framework.http
def enc(request: Request):
    # Enable CORS
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Content-Type': 'text/plain'
    }
    
    if request.method == 'OPTIONS':
        headers.update({
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        })
        return ('', 204, headers)
    
    url = request.args.get('url')
    if not url:
        return ('URL parameter is required', 400, headers)
    
    try:
        def generate():
            # Stream the download in chunks
            with requests.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                
                # Process and yield chunks
                for chunk in response.iter_content(chunk_size=1024*1024):  # 1MB chunks
                    if chunk:
                        # Encode and yield each chunk
                        yield base64.b64encode(chunk).decode('utf-8')
        
        # Return a streaming response
        return Response(
            generate(),
            status=200,
            headers=headers,
            mimetype='text/plain'
        )
    
    except requests.exceptions.RequestException as e:
        return (f"Error downloading file: {str(e)}", 500, headers)
