"""
Run the Kakinada Eat Street app with Waitress WSGI server.
Waitress handles streaming responses (SSE) properly on Windows
without the ConnectionResetError [WinError 10054] issue.
"""
import os
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from waitress import serve
from app import app
from models import db

if __name__ == '__main__':
    # Safe for existing SQLite databases; it creates only missing tables.
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    print("=" * 55, flush=True)
    print("  Kakinada Eat Street — Starting Server", flush=True)
    print(f"  URL: http://localhost:{port}", flush=True)
    print(f"  AI:  http://localhost:{port}/ai-test", flush=True)
    print("=" * 55, flush=True)
    try:
        serve(
            app,
            host='0.0.0.0',
            port=port,
            threads=8,           # 8 threads — handles concurrent Ollama calls
            channel_timeout=300, # 5 min timeout for long SSE streams
            cleanup_interval=30,
        )
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr, flush=True)

