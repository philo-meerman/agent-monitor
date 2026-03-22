#!/bin/bash

# Upgrade Agent Launcher
# Runs the upgrade agent

cd /Users/Philo/GitHub/agent-monitor

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the agent
python3 run-upgrade-agent.py

# Log result
echo "Upgrade agent completed at $(date)" >> ~/.upgrade-agent.log
