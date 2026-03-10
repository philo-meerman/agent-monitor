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

def parse_timestamp(timestamp_str):
    """Convert timestamp string to ISO format datetime object."""
    try:
        return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
    except:
        return datetime.now()

def extract_stage_summary(stage_name, raw_output):
    """
    Extract KPI summary from brew stage output.
    Returns summary string with key metrics.
    """
    output_lower = raw_output.lower()
    summaries = []
    
    if stage_name.lower() == 'update':
        # Look for "Updated X tap(s)"
        tap_match = re.search(r'updated\s+(\d+)\s+tap', output_lower)
        if tap_match:
            count = tap_match.group(1)
            summaries.append(f"{count} tap{'s' if count != '1' else ''} updated")
        
        # Look for outdated formulae
        outdated_match = re.search(r'(\d+)\s+outdated\s+formula', output_lower)
        if outdated_match:
            count = outdated_match.group(1)
            summaries.append(f"{count} formula{'s' if count != '1' else ''} outdated")
    
    elif stage_name.lower() == 'upgrade':
        # Look for "Upgrading X outdated packages"
        upgrade_match = re.search(r'upgrading\s+(\d+)\s+outdated', output_lower)
        if upgrade_match:
            count = upgrade_match.group(1)
            summaries.append(f"{count} package{'s' if count != '1' else ''} upgraded")
        
        # Look for specific package upgrades: "package 1.0 -> 2.0"
        pkg_matches = re.findall(r'(\S+)\s+\d+\.\d+.*?->\s*\d+\.\d+', output_lower)
        if pkg_matches and not upgrade_match:
            summaries.append(f"{len(pkg_matches)} package{'s' if len(pkg_matches) != 1 else ''} upgraded")
    
    elif stage_name.lower() == 'cleanup':
        # Look for "Removing X file(s)"
        cleanup_match = re.search(r'removing\s+(\d+)\s+file', output_lower)
        if cleanup_match:
            count = cleanup_match.group(1)
            summaries.append(f"{count} file{'s' if count != '1' else ''} removed")
        
        # Look for freed space
        space_match = re.search(r'freed\s+(\S+)', output_lower)
        if space_match:
            space = space_match.group(1)
            summaries.append(f"Freed {space}")
    
    if not summaries:
        summaries.append("No changes")
    
    return ", ".join(summaries)

def group_logs_by_pattern(lines):
    """
    Group log lines into events using pattern matching.
    Looks for "Starting brew maintenance" and "Brew maintenance finished" patterns.
    Returns list of event log groups.
    """
    events = []
    current_event = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Start of a new event
        if 'starting brew maintenance' in line.lower():
            # Save previous event if exists
            if current_event:
                events.append(current_event)
            current_event = [line]
        else:
            current_event.append(line)
            # End of event
            if 'brew maintenance finished' in line.lower():
                events.append(current_event)
                current_event = []
    
    # Add any remaining lines
    if current_event:
        events.append(current_event)
    
    return events

def parse_brew_events(log_lines=None):
    """
    Parse brew maintenance events from log lines.
    Supports both new format with [EVENT] markers and old format with pattern matching.
    
    Args:
        log_lines (list): List of log line strings. If None, reads from LOG_FILE.
    
    Returns:
        list: List of event dictionaries
    """
    if log_lines is None:
        if not os.path.exists(LOG_FILE):
            return []
        with open(LOG_FILE, 'r') as f:
            log_lines = f.readlines()
    
    events = []
    current_event = None
    current_stages = {}
    event_start_time = None
    log_buffer = []
    
    for line in log_lines:
        line = line.strip()
        if not line:
            continue
        
        log_buffer.append(line)
        
        # Check for new event markers
        if '[EVENT] START:' in line:
            # Save previous event
            if current_event:
                # Finalize previous event
                if current_stages:
                    current_event['stages'] = list(current_stages.values())
                    current_event['status'] = 'failed' if any(s['status'] == 'failed' for s in current_event['stages']) else \
                                              'warning' if any(s['status'] == 'warning' for s in current_event['stages']) else 'success'
                events.append(current_event)
            
            # Start new event
            time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', line)
            timestamp_str = time_match.group(1) if time_match else None
            
            # If no timestamp in event line, look backwards in log buffer
            if not timestamp_str:
                for prev_line in reversed(log_buffer[:-1]):
                    time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', prev_line)
                    if time_match:
                        timestamp_str = time_match.group(1)
                        break
            
            # Final fallback to current time
            if not timestamp_str:
                timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            event_start_time = parse_timestamp(timestamp_str)
            
            current_event = {
                'id': f"evt_{timestamp_str.replace(' ', '_').replace(':', '').replace('-', '')}",
                'name': 'Brew Maintenance',
                'trigger': 'Lid Wake',
                'timestamp': event_start_time.isoformat(),
                'timestamp_start': event_start_time,
                'status': 'success',
                'stages': [],
                'raw_logs': []
            }
            current_stages = {}
            log_buffer = [line]
        
        # Check for stage markers
        elif '[EVENT] STAGE:' in line and current_event:
            stage_match = re.search(r'STAGE:(\w+):(started|success|failed|warning)', line)
            if stage_match:
                stage_name = stage_match.group(1).capitalize()
                stage_status = stage_match.group(2)
                
                if stage_status == 'started':
                    time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', line)
                    timestamp_str = time_match.group(1) if time_match else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    current_stages[stage_name] = {
                        'name': stage_name,
                        'status': 'running',
                        'timestamp_start': parse_timestamp(timestamp_str).isoformat(),
                        'summary': '',
                        'duration_seconds': 0,
                        'raw_output': ''
                    }
                else:
                    if stage_name in current_stages:
                        current_stages[stage_name]['status'] = stage_status
        
        # Collect lines into current active stage's raw_output (only for non-EVENT lines)
        elif current_event and current_stages and '[EVENT]' not in line:
            active_stage = None
            for stage_name, stage_data in current_stages.items():
                if stage_data.get('status') in ('running', 'started'):
                    active_stage = stage_name
                    break
            if active_stage:
                current_stages[active_stage]['raw_output'] += line + '\n'
        
        # Check for event end marker
        elif '[EVENT] END:' in line and current_event:
            end_match = re.search(r'END:(\w+):(success|failed|warning)', line)
            if end_match:
                end_status = end_match.group(2)
                current_event['status'] = end_status
                
                # Calculate durations - look backwards for timestamp if not in END line
                time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', line)
                timestamp_str = time_match.group(1) if time_match else None
                
                if not timestamp_str:
                    for prev_line in reversed(log_buffer):
                        time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', prev_line)
                        if time_match:
                            timestamp_str = time_match.group(1)
                            break
                
                if not timestamp_str:
                    timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                event_end_time = parse_timestamp(timestamp_str)
                
                current_event['timestamp_end'] = event_end_time.isoformat()
                duration = (event_end_time - event_start_time).total_seconds()
                current_event['duration_seconds'] = int(duration)
                
                # Finalize stages and extract summaries
                for stage_name, stage_data in current_stages.items():
                    # Extract summary from raw output
                    stage_data['summary'] = extract_stage_summary(stage_name, stage_data['raw_output'])
                
                current_event['stages'] = list(current_stages.values())
                current_event['raw_logs'] = log_buffer
                
                # Create overall summary
                upgrades = sum(1 for s in current_event['stages'] if s['name'].lower() == 'upgrade')
                if upgrades > 0:
                    for stage in current_event['stages']:
                        if stage['name'].lower() == 'upgrade':
                            current_event['overall_summary'] = stage['summary']
                            break
                else:
                    current_event['overall_summary'] = 'No changes'
                
                events.append(current_event)
                current_event = None
                current_stages = {}
                log_buffer = []
    
    # If we're still tracking an event (incomplete new-format logs)
    if current_event and current_stages:
        current_event['stages'] = list(current_stages.values())
        events.append(current_event)
    
    # Fallback: If no events were found, try pattern matching for old-format logs
    if not events:
        event_groups = group_logs_by_pattern(log_lines)
        
        for group in event_groups:
            # Extract timestamp from first line
            first_line = group[0]
            time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', first_line)
            timestamp_str = time_match.group(1) if time_match else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            event_start_time = parse_timestamp(timestamp_str)
            
            # Extract timestamp from last line for duration
            last_line = group[-1]
            time_match = re.search(r'\[([\d\-]+\s+[\d:]+)\]', last_line)
            end_timestamp_str = time_match.group(1) if time_match else timestamp_str
            event_end_time = parse_timestamp(end_timestamp_str)
            
            # Determine overall status from log content
            full_content = '\n'.join(group)
            status = 'success'
            if any(pattern in full_content.lower() for pattern in ['error', 'failed', 'command not found']):
                status = 'failed'
            elif any(pattern in full_content.lower() for pattern in ['warning', 'deprecated']):
                status = 'warning'
            
            # Extract stages
            stages = []
            stage_names = ['update', 'upgrade', 'cleanup']
            for stage_name in stage_names:
                stage_lines = [l for l in group if stage_name in l.lower()]
                stage_raw = '\n'.join(stage_lines)
                
                # Determine stage status
                stage_status = 'success'
                if any(pattern in stage_raw.lower() for pattern in ['error', 'failed']):
                    stage_status = 'failed'
                elif any(pattern in stage_raw.lower() for pattern in ['warning']):
                    stage_status = 'warning'
                
                stage_summary = extract_stage_summary(stage_name, stage_raw)
                
                stages.append({
                    'name': stage_name.capitalize(),
                    'status': stage_status,
                    'summary': stage_summary,
                    'duration_seconds': 0,
                    'raw_output': stage_raw
                })
            
            event = {
                'id': f"evt_{timestamp_str.replace(' ', '_').replace(':', '').replace('-', '')}",
                'name': 'Brew Maintenance',
                'trigger': 'Lid Wake',
                'timestamp': event_start_time.isoformat(),
                'status': status,
                'duration_seconds': int((event_end_time - event_start_time).total_seconds()),
                'stages': stages,
                'overall_summary': stages[1]['summary'] if len(stages) > 1 else 'No changes',
                'raw_logs': group
            }
            events.append(event)
    
    # Sort by timestamp (newest first)
    events.sort(key=lambda x: x['timestamp'], reverse=True)
    return events

def generate_demo_events():
    """
    Generate realistic demo brew maintenance events with variety of statuses.
    
    Returns:
        list: List of demo event dictionaries
    """
    now = datetime.now()
    demo_events = []
    
    # Event 1: Success - 2 packages upgraded
    demo_events.append({
        'id': f"evt_{(now - timedelta(hours=4)).strftime('%Y%m%d_%H%M%S')}",
        'name': 'Brew Maintenance',
        'trigger': 'Lid Wake',
        'timestamp': (now - timedelta(hours=4)).isoformat(),
        'status': 'success',
        'duration_seconds': 135,
        'stages': [
            {
                'name': 'Update',
                'status': 'success',
                'summary': '2 taps updated',
                'duration_seconds': 25,
                'raw_output': '==> Updating Homebrew...\nUpdated 2 taps (anomalyco/tap, homebrew/core).'
            },
            {
                'name': 'Upgrade',
                'status': 'success',
                'summary': '2 packages upgraded',
                'duration_seconds': 85,
                'raw_output': '==> Upgrading 2 outdated packages:\nlibiconv 1.18 -> 1.19\nopencode 1.2.20 -> 1.2.21'
            },
            {
                'name': 'Cleanup',
                'status': 'success',
                'summary': '12 files removed, Freed 248.3MB',
                'duration_seconds': 25,
                'raw_output': '==> Removing old versions\nRemoving 12 files. Freed 248.3MB.'
            }
        ],
        'overall_summary': '2 packages upgraded',
        'raw_logs': ['Demo event 1']
    })
    
    # Event 2: Success - 0 packages
    demo_events.append({
        'id': f"evt_{(now - timedelta(hours=24)).strftime('%Y%m%d_%H%M%S')}",
        'name': 'Brew Maintenance',
        'trigger': 'Lid Wake',
        'timestamp': (now - timedelta(hours=24)).isoformat(),
        'status': 'success',
        'duration_seconds': 47,
        'stages': [
            {
                'name': 'Update',
                'status': 'success',
                'summary': '1 tap updated',
                'duration_seconds': 12,
                'raw_output': '==> Updating Homebrew...\nUpdated 1 tap (homebrew/core).'
            },
            {
                'name': 'Upgrade',
                'status': 'success',
                'summary': 'No changes',
                'duration_seconds': 20,
                'raw_output': 'Your system is up-to-date. No upgrades available.'
            },
            {
                'name': 'Cleanup',
                'status': 'success',
                'summary': '3 files removed, Freed 45.2MB',
                'duration_seconds': 15,
                'raw_output': '==> Removing old versions\nRemoving 3 files. Freed 45.2MB.'
            }
        ],
        'overall_summary': 'No changes',
        'raw_logs': ['Demo event 2']
    })
    
    # Event 3: Warning - deprecated packages
    demo_events.append({
        'id': f"evt_{(now - timedelta(hours=48)).strftime('%Y%m%d_%H%M%S')}",
        'name': 'Brew Maintenance',
        'trigger': 'Lid Wake',
        'timestamp': (now - timedelta(hours=48)).isoformat(),
        'status': 'warning',
        'duration_seconds': 156,
        'stages': [
            {
                'name': 'Update',
                'status': 'success',
                'summary': '2 taps updated',
                'duration_seconds': 30,
                'raw_output': '==> Updating Homebrew...\nUpdated 2 taps (anomalyco/tap, homebrew/core).'
            },
            {
                'name': 'Upgrade',
                'status': 'warning',
                'summary': '3 packages upgraded',
                'duration_seconds': 95,
                'raw_output': '==> Upgrading 3 outdated packages:\nnode 18.5 -> 18.12\npython 3.10.5 -> 3.10.9\ngo 1.18 -> 1.19\nWarning: Deprecated formula. Please migrate to node@18.'
            },
            {
                'name': 'Cleanup',
                'status': 'success',
                'summary': '28 files removed, Freed 512.7MB',
                'duration_seconds': 31,
                'raw_output': '==> Removing old versions\nRemoving 28 files. Freed 512.7MB.'
            }
        ],
        'overall_summary': '3 packages upgraded',
        'raw_logs': ['Demo event 3']
    })
    
    # Event 4: Failed - network timeout
    demo_events.append({
        'id': f"evt_{(now - timedelta(hours=72)).strftime('%Y%m%d_%H%M%S')}",
        'name': 'Brew Maintenance',
        'trigger': 'Lid Wake',
        'timestamp': (now - timedelta(hours=72)).isoformat(),
        'status': 'failed',
        'duration_seconds': 35,
        'stages': [
            {
                'name': 'Update',
                'status': 'success',
                'summary': '1 tap updated',
                'duration_seconds': 12,
                'raw_output': '==> Updating Homebrew...\nUpdated 1 tap (homebrew/core).'
            },
            {
                'name': 'Upgrade',
                'status': 'failed',
                'summary': 'Network error',
                'duration_seconds': 23,
                'raw_output': 'Error: Network timeout after 30 seconds. Failed to download bottles. Please try again later.'
            },
            {
                'name': 'Cleanup',
                'status': 'success',
                'summary': 'No changes',
                'duration_seconds': 0,
                'raw_output': 'Skipped due to upgrade failure.'
            }
        ],
        'overall_summary': 'Network error',
        'raw_logs': ['Demo event 4']
    })
    
    # Event 5: Success - large upgrade
    demo_events.append({
        'id': f"evt_{(now - timedelta(hours=96)).strftime('%Y%m%d_%H%M%S')}",
        'name': 'Brew Maintenance',
        'trigger': 'Lid Wake',
        'timestamp': (now - timedelta(hours=96)).isoformat(),
        'status': 'success',
        'duration_seconds': 287,
        'stages': [
            {
                'name': 'Update',
                'status': 'success',
                'summary': '3 taps updated',
                'duration_seconds': 35,
                'raw_output': '==> Updating Homebrew...\nUpdated 3 taps (anomalyco/tap, homebrew/core, homebrew/cask).'
            },
            {
                'name': 'Upgrade',
                'status': 'success',
                'summary': '5 packages upgraded',
                'duration_seconds': 215,
                'raw_output': '==> Upgrading 5 outdated packages:\nchrome 110.0 -> 111.0\nffmpeg 5.1.2 -> 6.0\nrust 1.67 -> 1.68\nnode 18.10 -> 18.12\npython 3.10.8 -> 3.10.9'
            },
            {
                'name': 'Cleanup',
                'status': 'success',
                'summary': '42 files removed, Freed 1.2GB',
                'duration_seconds': 37,
                'raw_output': '==> Removing old versions\nRemoving 42 files. Freed 1.2GB.'
            }
        ],
        'overall_summary': '5 packages upgraded',
        'raw_logs': ['Demo event 5']
    })
    
    return demo_events

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
    
    # Check Langfuse Docker status
    langfuse_status = check_langfuse_status()
    
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
            'status': langfuse_status,
            'last_run': None,  # Not applicable for AI services
            'icon': 'langfuse',
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

def check_langfuse_status():
    """Check if Langfuse Docker containers are running."""
    import subprocess
    import socket
    
    # Method 1: Check Docker containers
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', 'name=langfuse', '--format', '{{.Names}}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        containers = result.stdout.strip().split('\n') if result.stdout.strip() else []
        if containers and containers[0]:
            return 'running'
    except Exception as e:
        print(f"[DEBUG] Docker check failed: {e}")
    
    # Method 2: Fallback - check if port 3000 is listening
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('localhost', 3000))
        sock.close()
        if result == 0:
            return 'running'
    except Exception as e:
        print(f"[DEBUG] Port check failed: {e}")
    
    return 'stopped'

@app.route('/api/logs')
def get_logs():
    """
    Return parsed logs or events from the log file.
    Supports:
    - ?view=events (default) or ?view=logs for log lines
    - ?status=all|success|failed|warning (for events)
    - ?demo=true to force demo mode
    """
    view = request.args.get('view', 'events').lower()
    status_filter = request.args.get('status', 'all').lower()
    demo_mode = request.args.get('demo', 'false').lower() == 'true'
    
    # VIEW: EVENTS (new format)
    if view == 'events':
        events = []
        
        # Parse real events if they exist
        if os.path.exists(LOG_FILE) and not demo_mode:
            with open(LOG_FILE, 'r') as f:
                lines = f.readlines()
            events = parse_brew_events(lines)
        
        # If no real events found or demo mode is on, add demo data
        if not events or demo_mode:
            demo_events = generate_demo_events()
            
            # If we have real events, append demo data; otherwise use only demo
            if events and not demo_mode:
                events.extend(demo_events)
            else:
                events = demo_events
        
        # Apply status filter
        if status_filter != 'all':
            events = [e for e in events if e['status'] == status_filter]
        
        # Calculate summary
        all_events = parse_brew_events() if os.path.exists(LOG_FILE) else generate_demo_events()
        summary = {
            'success': len([e for e in all_events if e['status'] == 'success']),
            'failed': len([e for e in all_events if e['status'] == 'failed']),
            'warning': len([e for e in all_events if e['status'] == 'warning']),
        }
        
        response = {
            'view': 'events',
            'status_filter': status_filter,
            'events': events,
            'total_events': len(all_events),
            'summary': summary
        }
        
        return jsonify(response)
    
    # VIEW: LOGS (old format - for backward compatibility)
    else:
        log_entries = []
        
        # Parse real logs if they exist
        if os.path.exists(LOG_FILE) and not demo_mode:
            with open(LOG_FILE, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                if not line or '[EVENT]' in line:  # Skip empty lines and event markers
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
