import os
import sys
from pathlib import Path

# Add project root to sys.path so app.py and other modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app

# Vercel looks for the WSGI application object 'app'
if __name__ == "__main__":
    app.run(debug=True)
