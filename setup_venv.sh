#!/bin/bash
# Setup script to create virtual environment and install dependencies

echo "Setting up virtual environment..."

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install fastapi uvicorn jinja2 python-multipart

echo ""
echo "✓ Setup complete!"
echo ""
echo "To run the web app:"
echo "  1. Activate the virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Run the app:"
echo "     python servery_finder_web.py"
echo ""
echo "  3. Open http://localhost:5001 in your browser"

