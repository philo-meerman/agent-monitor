# Contributing to Agent Monitor

Thank you for your interest in contributing! This guide covers everything you need to set up your development environment and follow our standards.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/philo-meerman/agent-monitor.git
cd agent-monitor

# Run setup script
chmod +x scripts/setup-hooks.sh
./scripts/setup-hooks.sh

# Verify everything works
pytest tests/ test_app.py -v
```

**Time to complete:** ~5 minutes

---

## Prerequisites

### Required Software

| Software | Version | Install |
|----------|---------|---------|
| Python | 3.9+ | `brew install python@3.11` |
| Docker | Latest | [docker.com](https://docker.com) |
| Git | Latest | `brew install git` |
| Homebrew | Latest | [brew.sh](https://brew.sh) |

### Development Tools

| Tool | Purpose | Install |
|------|---------|---------|
| pre-commit | Git hooks | `brew install pre-commit` |
| gitleaks | Secret detection | `brew install gitleaks` |
| ruff | Python linting/formatting | `brew install ruff` |
| mypy | Type checking | `pip install mypy` |
| shellcheck | Shell script linting | `brew install shellcheck` |
| shfmt | Shell script formatting | `brew install shfmt` |

Install all at once:
```bash
brew install python@3.11 docker pre-commit gitleaks ruff shellcheck shfmt
```

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/philo-meerman/agent-monitor.git
cd agent-monitor
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Install Pre-commit Hooks

```bash
pre-commit install
```

This automatically runs on every `git commit`. To test manually:
```bash
pre-commit run --all-files
```

### 4. Copy Environment File

```bash
cp .env.example .env
# Edit .env with your API keys
```

---

## Development Workflow

### Running the Dashboard

```bash
# Activate virtual environment
source .venv/bin/activate

# Run Flask app
python app.py
```

Access at http://localhost:5001

### Running Tests

```bash
# All tests
pytest tests/ test_app.py -v

# Specific test file
pytest tests/test_upgrade_agent.py -v

# With coverage
pytest --cov=. tests/ test_app.py
```

### Code Quality Checks

Pre-commit hooks run automatically on commit. To run manually:

```bash
# All checks
pre-commit run --all-files

# Specific hook
pre-commit run ruff --all-files
pre-commit run mypy --all-files
pre-commit run gitleaks --all-files
```

### Git Workflow

1. **Create a branch** for your changes:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** following the [Code Standards](#code-standards)

3. **Run tests** before committing:
   ```bash
   pytest tests/ test_app.py -v
   ```

4. **Commit** (hooks run automatically):
   ```bash
   git add .
   git commit -m "feat: add your feature"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feat/your-feature-name
   ```

---

## Code Standards

### Python

- **Formatter:** ruff (follows black style)
- **Line length:** 88 characters
- **Indentation:** 4 spaces
- **Import order:** ruff handles this automatically

Run formatter:
```bash
ruff format .
ruff check --fix .
```

### Shell Scripts

- **Formatter:** shfmt (2-space indent, sr quotes)
- **ShellCheck:** Must pass all checks
- **Style:** `set -euo pipefail` at top of every script

Format shell scripts:
```bash
shfmt -w -i=2 -sr -ci *.sh
```

### Type Annotations

We use mypy for type checking:
```python
def greet(name: str) -> str:
    return f"Hello, {name}"
```

Run type checker:
```bash
mypy upgrade_agent app.py --ignore-missing-imports
```

---

## Testing

### Test Structure

```
tests/
├── conftest.py          # Pytest fixtures
├── test_upgrade_agent.py
└── ...

test_app.py              # Flask app tests
```

### Writing Tests

```python
def test_something():
    """Test description."""
    result = my_function(input)
    assert result == expected
```

### Running Tests

```bash
# All tests
pytest tests/ test_app.py -v

# Watch mode (requires pytest-watch)
ptw

# Specific test
pytest tests/test_upgrade_agent.py::test_function -v
```

---

## Submitting Changes

### Pull Request Process

1. **Fork** the repository
2. **Create** a feature branch: `feat/your-feature`
3. **Write** tests for your changes
4. **Ensure** all tests pass: `pytest tests/ test_app.py -v`
5. **Ensure** hooks pass: `pre-commit run --all-files`
6. **Submit** a pull request

### Commit Message Format

```
type(scope): description

feat: add new feature
fix: bug fix
docs: documentation changes
style: formatting changes
refactor: code refactoring
test: adding tests
chore: maintenance tasks
```

Examples:
```
feat(dashboard): add agent status cards
fix(logs): handle missing timestamps
docs(readme): update installation instructions
```

### CI Pipeline

All PRs must pass:

| Check | Description |
|-------|-------------|
| Lint | ruff format + check |
| Type Check | mypy type checking |
| Tests | pytest |
| Secrets | gitleaks scan |
| Shell | shellcheck + shfmt |

---

## Troubleshooting

### Pre-commit Hooks Failing

```bash
# Update hook versions
pre-commit autoupdate

# Skip hooks temporarily (not for PRs)
git commit --no-verify

# Run hooks manually to debug
pre-commit run --all-files -v
```

### Import Errors

```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Port Already in Use

```bash
# Find process using port 5001
lsof -i :5001

# Kill it
kill -9 <PID>
```

---

## Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [Pre-commit Documentation](https://pre-commit.com/)
- [GitHub Actions](https://docs.github.com/en/actions)

---

Questions? Open an issue or reach out!
