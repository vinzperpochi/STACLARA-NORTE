"""Vercel serverless entry point for the Flask application."""

from app import create_app

# Vercel imports this module for every warm serverless worker. All required
# credentials are supplied through Vercel environment variables, never source.
app = create_app("production")
