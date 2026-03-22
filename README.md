# Agent Monitor

A unified dashboard to monitor both your AI/LLM agents and system automation agents.

## Features

- **System Agents Dashboard**: Monitor and view logs for system automation scripts (e.g., brew maintenance)
- **Langfuse Integration**: Self-hosted observability platform for AI/LLM agents
- **Auto-refresh**: Dashboard updates automatically every 10 seconds
- **Pretty-printed Logs**: Color-coded log viewer for easy reading
- **Auto-start**: Dashboard runs at login via launchd

## Components

### 1. System Agent Dashboard (Flask)
- Runs on `http://localhost:5001`
- Shows agent status cards with success/failure indicators
- Displays last run timestamps
- Log viewer with filtering

### 2. Langfuse v3 (AI Agent Observability)
- Runs on `http://localhost:3000`
- Traces for LLM calls
- Token usage and cost tracking
- Quality evaluation
- Includes: Web, Worker, PostgreSQL, ClickHouse, Redis, MinIO

## Setup

### Prerequisites

- Python 3.8+
- Docker Desktop (for Langfuse)

### Install Dependencies

```bash
cd ~/GitHub/agent-monitor
pip install -r requirements.txt
```

### Run Dashboard

```bash
python app.py
```

Access the dashboard at: http://localhost:5001

### Setup Langfuse (Optional - for AI agents)

```bash
cd ~/GitHub/agent-monitor
chmod +x setup-langfuse.sh
./setup-langfuse.sh
```

Access Langfuse at: http://localhost:3000
MinIO Console at: http://localhost:9090 (admin/minioadmin)

### Enable Auto-start (Optional)

```bash
cp launchd/com.user.agent-dashboard.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.agent-dashboard.plist
```

## Usage

### System Agents

The dashboard automatically monitors agents that write to log files. Currently configured:

- **Brew Maintenance**: Monitors `~/.brew-maintenance.log`

To add more agents:
1. Update `app.py` to parse your agent's log file
2. Add the agent to the `AGENTS` list

### AI Agents

To integrate Langfuse with your AI agents:

```python
from langfuse import observe

@observe(as_type="agent")
def your_agent():
    # Your agent code
    pass
```

Set environment variables:
```bash
export LANGFUSE_HOST="http://localhost:3000"
export LANGFUSE_PUBLIC_KEY="your-public-key"
export LANGFUSE_SECRET_KEY="your-secret-key"
```

## Project Structure

```
agent-monitor/
├── app.py                      # Flask backend
├── test_app.py                 # Flask app tests
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Development dependencies
├── pyproject.toml             # Ruff + mypy configuration
├── .editorconfig              # Code style configuration
├── .pre-commit-config.yaml   # Pre-commit hooks
├── .github/workflows/ci.yml   # GitHub Actions CI
├── run-dashboard.sh           # Dashboard runner script
├── setup-langfuse.sh          # Langfuse setup script
├── scripts/
│   └── setup-hooks.sh          # Dev environment setup
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   └── test_upgrade_agent.py   # Agent tests
├── upgrade_agent/              # Upgrade agent module
├── templates/
│   ├── index.html              # Dashboard UI
│   └── logs.html               # Log viewer UI
└── .vscode/
    ├── settings.json           # VS Code settings
    └── extensions.json         # Recommended extensions
```

## Development

### Quick Start

```bash
# Clone and setup
git clone https://github.com/philo-meerman/agent-monitor.git
cd agent-monitor
./scripts/setup-hooks.sh

# Activate environment
source .venv/bin/activate

# Run tests
pytest tests/ test_app.py -v

# Run dashboard
python app.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full setup instructions.

## Troubleshooting

### Pre-commit Hooks Failing

```bash
# Update hook versions
pre-commit autoupdate

# Run manually to debug
pre-commit run --all-files -v
```

### Dashboard not starting

```bash
# Check if port 5001 is in use
lsof -i :5001

# Check logs
cat ~/.agent-dashboard.log
```

### Langfuse not starting

```bash
# Check Docker is running
docker info

# Check Langfuse logs
docker compose -f docker-compose.v3.yml logs -f
```

### Tests Failing

```bash
# Run with verbose output
pytest tests/ test_app.py -v

# Run specific test
pytest tests/test_upgrade_agent.py::test_name -v
```

For more help, see [CONTRIBUTING.md](CONTRIBUTING.md#troubleshooting).

## License

MIT
