from flask import Flask, request, send_file, jsonify
import requests
import zipfile
import os
import tempfile
import uuid
from urllib.parse import urlparse, unquote
from pathlib import Path
from datetime import datetime, timedelta

app = Flask(__name__)

# Create a directory for storing zip files
STORAGE_DIR = os.path.join(tempfile.gettempdir(), 'zip_storage')
os.makedirs(STORAGE_DIR, exist_ok=True)

# Store file metadata
files = {}

def cleanup_old_files():
    """Remove files older than 1 hour"""
    current_time = datetime.now()
    files_to_remove = []
    
    for file_id, metadata in files.items():
        if current_time - metadata['created_at'] > timedelta(hours=1):
            try:
                os.remove(metadata['path'])
                files_to_remove.append(file_id)
            except OSError:
                pass
    
    for file_id in files_to_remove:
        files.pop(file_id)

@app.route('/')
def home():
    return 'Service is running. Use /create?url=YOUR_URL to create zip files.'

@app.route('/create')
def create_zip():
    # Clean up old files
    cleanup_old_files()
    
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
        
        # Generate unique ID for this file
        file_id = str(uuid.uuid4())
        zip_filename = f'{Path(original_filename).stem}.zip'
        zip_path = os.path.join(STORAGE_DIR, f'{file_id}_{zip_filename}')
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save the downloaded file
            download_path = os.path.join(temp_dir, original_filename)
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Create ZIP file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(download_path, original_filename)
        
        # Store file metadata
        files[file_id] = {
            'path': zip_path,
            'filename': zip_filename,
            'created_at': datetime.now()
        }
        
        # Generate download URL
        download_url = f'/download/{file_id}'
        
        return jsonify({
            'file_id': file_id,
            'download_url': download_url,
            'filename': zip_filename,
            'expires_in': '1 hour'
        })
    
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/download/<file_id>')
def download_file(file_id):
    # Clean up old files
    cleanup_old_files()
    
    # Check if file exists
    if file_id not in files:
        return jsonify({'error': 'File not found or expired'}), 404
    
    file_info = files[file_id]
    
    try:
        return send_file(
            file_info['path'],
            as_attachment=True,
            download_name=file_info['filename'],
            mimetype='application/zip'
        )
    except Exception as e:
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)