from flask import Flask, request, send_file, jsonify
import requests
import zipfile
import os
import tempfile
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
    
    for file_key, metadata in files.items():
        if current_time - metadata['created_at'] > timedelta(hours=1):
            try:
                os.remove(metadata['path'])
                files_to_remove.append(file_key)
            except OSError:
                pass
    
    for file_key in files_to_remove:
        files.pop(file_key)

def get_safe_filename(url, original_filename):
    """Create a safe, URL-friendly filename"""
    # Clean the filename
    safe_filename = ''.join(c for c in original_filename if c.isalnum() or c in ('-', '_', '.'))
    safe_filename = safe_filename.lower()
    
    # Use just the filename stem
    base_name = Path(safe_filename).stem
    return f"{base_name}.zip"

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
        # Get original filename from URL
        original_filename = os.path.basename(urlparse(url).path)
        if not original_filename:
            original_filename = 'downloaded_file'
        
        # Generate file key based on the URL and filename
        file_key = get_safe_filename(url, original_filename)
        zip_filename = file_key  # file_key already includes .zip extension
        zip_path = os.path.join(STORAGE_DIR, zip_filename)
        
        # Check if file already exists and is not expired
        if file_key in files:
            file_info = files[file_key]
            if datetime.now() - file_info['created_at'] <= timedelta(hours=1):
                # File exists and is not expired, return existing download URL
                return jsonify({
                    'file_key': file_key,
                    'download_url': f'/download/{file_key}',
                    'filename': zip_filename,
                    'expires_in': '1 hour',
                    'reused': True
                })
        
        # Download and process the file
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
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
        files[file_key] = {
            'path': zip_path,
            'filename': zip_filename,
            'created_at': datetime.now()
        }
        
        return jsonify({
            'file_key': file_key,
            'download_url': f'/download/{file_key}',
            'filename': zip_filename,
            'expires_in': '1 hour',
            'reused': False
        })
    
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Error downloading file: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/download/<file_key>')
def download_file(file_key):
    # Clean up old files
    cleanup_old_files()
    
    # Check if file exists
    if file_key not in files:
        return jsonify({'error': 'File not found or expired'}), 404
    
    file_info = files[file_key]
    
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