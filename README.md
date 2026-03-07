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

### 2. Langfuse (AI Agent Observability)
- Runs on `http://localhost:3000`
- Traces for LLM calls
- Token usage and cost tracking
- Quality evaluation

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
├── requirements.txt            # Python dependencies
├── run-dashboard.sh            # Dashboard runner script
├── setup-langfuse.sh          # Langfuse setup script
├── README.md                   # This file
├── launchd/
│   └── com.user.agent-dashboard.plist  # Auto-start agent
└── templates/
    ├── index.html              # Dashboard UI
    └── logs.html               # Log viewer UI
```

## Troubleshooting

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
cd ../langfuse
docker compose logs -f
```

### Agents not showing

- Ensure your agent scripts write to log files
- Check log file format matches the parser in `app.py`

## License

MIT
