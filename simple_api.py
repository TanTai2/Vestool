#!/usr/bin/env python3
"""Simple API server to serve apps.json and versions data."""
from flask import Flask, jsonify, send_from_directory, Response
from flask_cors import CORS
import os
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

DATA_DIR = '/root/VesTool/data'

@app.route('/api/apps')
def get_apps():
    """Serve apps.json"""
    apps_file = os.path.join(DATA_DIR, 'apps.json')
    if not os.path.exists(apps_file):
        return jsonify([])
    with open(apps_file, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))

@app.route('/api/versions/<app_id>')
def get_versions(app_id):
    """Serve version data for an app"""
    safe_id = app_id.replace('.', '_')
    version_file = os.path.join(DATA_DIR, 'versions', f'{safe_id}.json')
    if not os.path.exists(version_file):
        return jsonify([])
    with open(version_file, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))

@app.route('/api/apk/<filename>')
def serve_apk(filename):
    """Serve APK files"""
    apk_dir = os.path.join(DATA_DIR, 'apks')
    if not os.path.exists(os.path.join(apk_dir, filename)):
        return "Not found", 404
    
    def generate():
        with open(os.path.join(apk_dir, filename), 'rb') as f:
            while chunk := f.read(65536):
                yield chunk
    
    file_size = os.path.getsize(os.path.join(apk_dir, filename))
    return Response(
        generate(),
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(file_size),
            'Content-Type': 'application/vnd.android.package-archive',
        }
    )

@app.route('/data/<path:path>')
def serve_data(path):
    """Serve static data files"""
    return send_from_directory(DATA_DIR, path)

@app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'endpoints': ['/api/apps', '/api/versions/<app_id>', '/api/apk/<filename>']
    })

if __name__ == '__main__':
    print("Starting API server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
