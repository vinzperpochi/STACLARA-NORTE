"""Vercel serverless entry point for the Flask application."""

from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix

# Vercel imports this module for every warm serverless worker. All required
# credentials are supplied through Vercel environment variables, never source.
app = create_app("production", vercel=True)
app.config["ATTENDANCE_SHARED_CAPTURE"] = True
app.config["DOCUMENT_BROWSER_PDF"] = True
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1)
