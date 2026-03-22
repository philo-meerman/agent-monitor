"""Run the upgrade agent."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upgrade_agent.agent import run_upgrade_agent_sync
from upgrade_agent.config import validate_config


def main():
    """Main entry point."""
    print("=" * 50)
    print("Upgrade Agent - Starting")
    print("=" * 50)
    
    # Validate config
    missing = validate_config()
    if missing:
        print(f"ERROR: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease copy .env.example to .env and fill in the values.")
        sys.exit(1)
    
    # Run agent
    print("\nRunning upgrade agent...\n")
    result = run_upgrade_agent_sync()
    
    print("\n" + "=" * 50)
    print("Upgrade Agent - Complete")
    print("=" * 50)
    print(f"Result: {result}")
    
    return result


if __name__ == "__main__":
    main()
