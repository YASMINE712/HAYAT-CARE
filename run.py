"""Start the website and background scheduler together."""
import os
import threading
from waitress import serve
from worker import run_worker

def serve_app(app=None):
    if app is None:
        from app import app
    stop = threading.Event()
    worker = threading.Thread(target=run_worker, args=(app.extensions['store'], stop), daemon=True)
    worker.start()
    try:
        serve(app, host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '5000')))
    finally:
        stop.set()
        worker.join(timeout=20)


if __name__ == '__main__':
    serve_app()
