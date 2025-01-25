from flask import Flask, request, jsonify
import requests
import tempfile
import os
from urllib.parse import urlparse, unquote
from pathlib import Path

app = Flask(__name__)

def get_gofile_server():
    """Get the best server from gofile.io"""
    try:
        response = requests.get('https://api.gofile.io/getServer')
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'ok':
            return data['data']['server']
        raise Exception('Failed to get server: ' + data.get('status', 'unknown error'))
    except Exception as e:
        raise Exception(f'Error getting gofile server: {str(e)}')

def upload_to_gofile(file_path):
    """Upload a file to gofile.io"""
    try:
        # Get the best server
        server = get_gofile_server()
        
        # Upload the file
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f'https://{server}.gofile.io/uploadFile', files=files)
            response.raise_for_status()
            
            data = response.json()
            if data['status'] == 'ok':
                return data['data']
            raise Exception('Upload failed: ' + data.get('status', 'unknown error'))
    except Exception as e:
        raise Exception(f'Error uploading to gofile: {str(e)}')

@app.route('/')
def home():
    return 'Service is running. Use /create?url=YOUR_URL to create and upload files to gofile.io.'

@app.route('/create')
def create_zip():
    # Get URL parameter
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400
    
    # Decode URL if it's encoded
    url = unquote(url)
    
    try:
        # Download the file
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Get original filename from URL
        original_filename = os.path.basename(urlparse(url).path)
        if not original_filename:
            original_filename = 'downloaded_file'
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save the downloaded file
            download_path = os.path.join(temp_dir, original_filename)
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Upload to gofile.io
            upload_result = upload_to_gofile(download_path)
            
            return jsonify({
                'status': 'success',
                'download_url': upload_result['downloadPage'],
                'direct_link': upload_result['directLink'],
                'filename': original_filename
            })
    
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)