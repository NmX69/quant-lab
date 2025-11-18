from flask import Flask, send_from_directory, abort, Response
import os

app = Flask(__name__)

# Serve every file and subfolder in the current directory
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_file(path):
    # Security: prevent going above the repo root
    safe_path = os.path.abspath(os.path.join('.', path))
    if not safe_path.startswith(os.path.abspath('.')):
        abort(403)
    
    if os.path.isdir(safe_path):
        # Simple directory listing if no index.html
        files = os.listdir(safe_path)
        html = "<html><body><h2>Quant Lab Repository</h2><ul>"
        for f in sorted(files):
            html += f"<li><a href='/{os.path.join(path, f).replace(os.sep, '/')}'>{f}</a></li>"
        html += "</ul></body></html>"
        return html
    
    # ── STREAMING FIX FOR LARGE FILES ──
    def generate():
        with open(safe_path, 'rb') as f:
            while chunk := f.read(4096):
                yield chunk
    return Response(generate(), mimetype='text/plain' if path.endswith('.py') or path.endswith('.txt') else 'application/octet-stream')

if __name__ == '__main__':
    print("Quant Lab repo serving on http://localhost and public IP port 80")
    app.run(host='0.0.0.0', port=80, threaded=True)
# serve.py v1.2