from flask import Flask, render_template, jsonify
import os
import json
from datetime import datetime
import re

app = Flask(__name__)

LOG_FILE = os.path.expanduser("~/.brew-maintenance.log")

def parse_agents_from_logs():
    """Parse agent statuses from the log file."""
    agents = {}
    
    if not os.path.exists(LOG_FILE):
        return []
    
    with open(LOG_FILE, 'r') as f:
        content = f.read()
    
    # Parse log entries to extract agent information
    # Looking for patterns like "Agent: <name> - Status: <status>"
    lines = content.split('\n')
    
    for line in lines:
        # Match agent status patterns
        agent_match = re.search(r'Agent:\s*(\S+).*?Status:\s*(\S+)', line)
        time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', line)
        
        if agent_match:
            name = agent_match.group(1)
            status = agent_match.group(2).lower()
            timestamp = time_match.group(1) if time_match else None
            
            agents[name] = {
                'name': name,
                'status': 'success' if status == 'success' else 'failure',
                'last_run': timestamp or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    return list(agents.values())

@app.route('/')
def index():
    """Serve the main dashboard."""
    return render_template('index.html')

@app.route('/logs')
def logs():
    """Serve the log viewer page."""
    return render_template('logs.html')

@app.route('/api/agents')
def get_agents():
    """Return JSON with agent statuses."""
    agents = parse_agents_from_logs()
    
    # If no agents found in logs, provide demo data
    if not agents:
        agents = [
            {'name': 'brew-update', 'status': 'success', 'last_run': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
            {'name': 'brew-upgrade', 'status': 'success', 'last_run': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
            {'name': 'brew-cleanup', 'status': 'failure', 'last_run': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
        ]
    
    return jsonify(agents)

@app.route('/api/logs')
def get_logs():
    """Return parsed log entries from the log file."""
    log_entries = []
    
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Extract timestamp
            time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', line)
            timestamp = time_match.group(1) if time_match else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Determine log level
            level = 'info'
            if 'error' in line.lower() or 'failure' in line.lower():
                level = 'error'
            elif 'success' in line.lower():
                level = 'success'
            elif 'warning' in line.lower():
                level = 'warning'
            
            log_entries.append({
                'timestamp': timestamp,
                'message': line,
                'level': level
            })
    
    # If no logs found, provide demo entries
    if not log_entries:
        log_entries = [
            {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'message': 'Agent: brew-update - Status: Success', 'level': 'success'},
            {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'message': 'Agent: brew-upgrade - Status: Success', 'level': 'success'},
            {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'message': 'Agent: brew-cleanup - Status: Failure - Error: Permission denied', 'level': 'error'},
        ]
    
    return jsonify(log_entries)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
