"""WSGI entry point: `flask run` (via FLASK_APP=wsgi.py) or `gunicorn wsgi:app`."""
from app import create_app

app = create_app()
