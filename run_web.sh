#!/bin/bash
# Script to run the web app with the correct Python version

# Try to find Python with FastAPI installed
if python3.11 -c "import fastapi" 2>/dev/null; then
    echo "Using Python 3.11 (FastAPI found)"
    python3.11 servery_finder_web.py
elif python3 -c "import fastapi" 2>/dev/null; then
    echo "Using Python 3 (FastAPI found)"
    python3 servery_finder_web.py
else
    echo "FastAPI not found in any Python version."
    echo ""
    echo "To install FastAPI, use one of these methods:"
    echo ""
    echo "Option 1: Use virtual environment (recommended):"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo "  python servery_finder_web.py"
    echo ""
    echo "Option 2: Install for current user:"
    echo "  python3 -m pip install --user fastapi uvicorn jinja2 python-multipart"
    echo ""
    echo "Option 3: Install with --break-system-packages (not recommended):"
    echo "  python3 -m pip install --break-system-packages fastapi uvicorn jinja2 python-multipart"
fi

