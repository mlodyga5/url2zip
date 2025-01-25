from flask import Flask, request, send_file
import requests
import zipfile
import os
import tempfile
from urllib.parse import urlparse, unquote
from pathlib import Path

app = Flask(__name__)

@app.route('/')
def home():
    return 'Service is running. Use /zip?url=YOUR_URL to download zipped files.'

@app.route('/zip')
def zip_file():
    # Get URL parameter
    url = request.args.get('url')
    if not url:
        return 'URL parameter is required', 400
    
    # Decode URL if it's encoded
    url = unquote(url)
    
    try:
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download the file
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Get original filename from URL
            original_filename = os.path.basename(urlparse(url).path)
            if not original_filename:
                original_filename = 'downloaded_file'
            
            # Save the downloaded file
            download_path = os.path.join(temp_dir, original_filename)
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Create ZIP file
            zip_filename = f'{Path(original_filename).stem}.zip'
            zip_path = os.path.join(temp_dir, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(download_path, original_filename)
            
            # Send the ZIP file
            return send_file(
                zip_path,
                as_attachment=True,
                download_name=zip_filename,
                mimetype='application/zip'
            )
    
    except requests.exceptions.RequestException as e:
        return f'Error downloading file: {str(e)}', 400
    except Exception as e:
        return f'Error processing file: {str(e)}', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)