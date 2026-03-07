from flask import Flask, render_template, jsonify, request
import os
import json
from datetime import datetime, timedelta
import re

app = Flask(__name__)

LOG_FILE = os.path.expanduser("~/.brew-maintenance.log")

def detect_log_level(line):
    """
    Detect the log level (error, warning, success, info) from a log line.
    
    Args:
        line (str): The log line to analyze
        
    Returns:
        str: One of 'error', 'warning', 'success', or 'info'
    """
    line_lower = line.lower()
    
    # Error patterns: error, failed, failure, command not found, exception, fatal, abort, etc.
    error_patterns = ['error', 'failed', 'failure', 'command not found', 'exception', 
                      'fatal', 'abort', 'panic', 'segmentation fault', 'traceback',
                      'error:', 'err:', 'errno', 'crashed', 'could not', 'cannot']
    if any(pattern in line_lower for pattern in error_patterns):
        return 'error'
    
    # Warning patterns: warning, warn, deprecated, retry, timeout, deprecated, etc.
    warning_patterns = ['warning', 'warn', 'deprecated', 'retry', 'timeout', 'skip',
                       'warn:', 'warning:', 'ignored', 'unknown', 'suspicious']
    if any(pattern in line_lower for pattern in warning_patterns):
        return 'warning'
    
    # Success patterns: completed, finished, success, succeeded, done, ✓, etc.
    success_patterns = ['completed', 'finished', 'succeeded', 'success', 'done',
                       '✓', 'successful', 'complete', 'deployed', 'installed',
                       'deployed successfully', 'updated successfully']
    if any(pattern in line_lower for pattern in success_patterns):
        return 'success'
    
    # Default to info
    return 'info'

def generate_demo_logs():
    """
    Generate realistic demo log entries with variety of levels.
    
    Returns:
        list: List of demo log entries
    """
    now = datetime.now()
    demo_entries = []
    
    # Success entries
    success_messages = [
        'Agent: brew-update - Status: Success',
        '[brew-update] brew update completed successfully',
        'Deployment finished with 0 errors',
        'Database migration succeeded',
        'Cache cleared successfully',
        'Backup completed successfully',
        'Health check passed',
        'All tests passed successfully',
    ]
    
    # Error entries
    error_messages = [
        'Agent: backup-job - Status: Failed - Error: disk space low',
        'ERROR: Connection refused to database server',
        'Fatal error: Authentication failed for API endpoint',
        'Exception in agent processor: Null pointer exception',
        'Critical: Network timeout after 30 seconds',
        'Error: File not found or permission denied',
    ]
    
    # Warning entries
    warning_messages = [
        'WARNING: Response time exceeded 5 seconds',
        'Deprecated API endpoint used - please update client',
        'Retry attempt 2 of 3 for agent connection',
        'Warning: Memory usage at 85% threshold',
        'Timeout warning: Request took longer than expected',
    ]
    
    # Info entries
    info_messages = [
        'Starting agent monitoring cycle',
        'Fetching logs from all agents',
        'Processing 150 log entries',
        'Connected to agent broker',
        'Loading configuration from file',
        'Initializing database connection',
    ]
    
    # Create entries with timestamps spread over the last 2 days
    all_messages = [
        ('success', success_messages),
        ('error', error_messages),
        ('warning', warning_messages),
        ('info', info_messages),
    ]
    
    entry_index = 0
    for level, messages in all_messages:
        for i, message in enumerate(messages):
            # Spread timestamps over the last 2 days
            time_offset = (entry_index * 2) % 48  # 48-hour spread
            timestamp = now - timedelta(hours=time_offset)
            
            demo_entries.append({
                'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'message': message,
                'level': level,
                'is_demo': True
            })
            entry_index += 1
    
    # Sort by timestamp (newest first)
    demo_entries.sort(key=lambda x: x['timestamp'], reverse=True)
    return demo_entries

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
    
    # Add static agents
    static_agents = [
        {
            'name': 'Brew Maintenance',
            'status': 'success',
            'last_run': get_last_brew_run(),
            'icon': '🍺',
            'type': 'system',
            'link': '/logs?agent=brew'
        },
        {
            'name': 'Langfuse',
            'status': 'running',
            'last_run': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'icon': '🤖',
            'type': 'ai',
            'link': 'http://localhost:3000/project/cmmgpb4m100063hfu9fs66va4'
        }
    ]
    
    return jsonify(static_agents)

def get_last_brew_run():
    """Get the last run time from brew maintenance log."""
    if not os.path.exists(LOG_FILE):
        return None
    with open(LOG_FILE, 'r') as f:
        lines = f.readlines()
    for line in reversed(lines):
        if 'finished' in line.lower():
            match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', line)
            if match:
                return match.group(1)
    return None

@app.route('/api/logs')
def get_logs():
    """
    Return parsed log entries from the log file.
    Supports ?demo=true to force demo mode.
    """
    log_entries = []
    
    # Check if demo mode is requested
    demo_mode = request.args.get('demo', 'false').lower() == 'true'
    
    # Parse real logs if they exist
    if os.path.exists(LOG_FILE) and not demo_mode:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Extract timestamp
            time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', line)
            timestamp = time_match.group(1) if time_match else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Use smart log level detection
            level = detect_log_level(line)
            
            log_entries.append({
                'timestamp': timestamp,
                'message': line,
                'level': level
            })
    
    # If no real logs found or demo mode is on, add demo data
    if not log_entries or demo_mode:
        demo_entries = generate_demo_logs()
        
        # If we have real logs, append demo data; otherwise use only demo
        if log_entries and not demo_mode:
            log_entries.extend(demo_entries)
        else:
            log_entries = demo_entries
    
    # Sort by timestamp (newest first)
    log_entries.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify(log_entries)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
