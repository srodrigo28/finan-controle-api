"""Entrada WSGI para o gunicorn: `gunicorn wsgi:application`."""
from app import create_app

application = create_app()
