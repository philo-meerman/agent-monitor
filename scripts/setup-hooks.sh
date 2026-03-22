#!/bin/bash
# Setup pre-commit hooks for agent-monitor
# Run once after cloning

set -euo pipefail

echo "Installing pre-commit hooks..."

# Check if brew is available
if ! command -v brew &> /dev/null; then
    echo "Error: Homebrew is required. Install from https://brew.sh"
    exit 1
fi

# Install tools
echo "Installing development tools..."
brew install pre-commit gitleaks shellcheck shfmt || true

# Install Python dependencies
echo "Installing Python dependencies..."
if command -v python3.11 &> /dev/null; then
    python3.11 -m venv .venv
else
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt -q
pip install -r requirements-dev.txt -q

# Install pre-commit hooks
echo "Installing git hooks..."
pre-commit install

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. source .venv/bin/activate"
echo "  2. cp .env.example .env  # Add your keys"
echo "  3. pytest tests/ test_app.py -v  # Verify setup"
