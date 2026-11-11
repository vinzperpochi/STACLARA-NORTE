#!/usr/bin/env python3
"""Run Flask database migrations."""

import os
import sys
from app import create_app
from flask_migrate import upgrade

def main():
    """Run database migrations to latest version."""
    print("Loading application...")
    app = create_app(os.getenv('FLASK_CONFIG', 'development'))
    
    with app.app_context():
        print("Running migrations to latest version...")
        try:
            upgrade(revision='heads')
            print("✅ Migrations completed successfully!")
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            sys.exit(1)

if __name__ == '__main__':
    main()