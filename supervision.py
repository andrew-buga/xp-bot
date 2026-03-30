"""
Supervision Module - Health monitoring and system state snapshots for XP-Bot

Tracks bot health metrics and creates periodic snapshots of system state.
Used to detect issues and monitor overall bot behavior.

Outputs:
- analytics/supervision.log - Health snapshots (appended on bot start + periodic)
- analytics/supervision_summary.json - Current system state (updated regularly)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

ANALYTICS_DIR = Path("analytics")
SUPERVISION_LOG = ANALYTICS_DIR / "supervision.log"
SUPERVISION_SUMMARY = ANALYTICS_DIR / "supervision_summary.json"


def ensure_analytics_dir():
    """Create analytics directory if it doesn't exist."""
    ANALYTICS_DIR.mkdir(exist_ok=True)


def log_supervision_event(event_type: str, data: Dict[str, Any]) -> bool:
    """
    Log a supervision event to the supervision log.
    
    Args:
        event_type: Type of supervision event (e.g., 'BOT_START', 'PERIODIC', 'HEALTH')
        data: Event data
        
    Returns:
        bool: True if logged successfully
    """
    ensure_analytics_dir()
    
    try:
        timestamp = datetime.utcnow().isoformat()
        event_str = f"[{timestamp}] {event_type}: "
        
        # Format data as readable key=value pairs
        data_str = ", ".join(f"{k}={v}" for k, v in data.items())
        
        with open(SUPERVISION_LOG, "a", encoding="utf-8") as f:
            f.write(event_str + data_str + "\n")
        
        return True
    except Exception as e:
        logger.error(f"Failed to log supervision event: {e}")
        return False


def update_supervision_summary(snapshot: Dict[str, Any]) -> bool:
    """
    Update the current supervision summary (snapshot of current state).
    
    Args:
        snapshot: Dict with keys 'users', 'system', 'today' containing metrics
        
    Returns:
        bool: True if updated successfully
        
    Example snapshot:
    {
        "timestamp": "2026-03-31T12:00:00",
        "users": {
            "total": 10,
            "verified": 8,
            "in_departments": 10,
            "by_role": {"admin": 1, "user": 9}
        },
        "system": {
            "pending_submissions": 2,
            "unreviewed_ideas": 1,
            "banned_users": 0,
            "open_tasks": 15
        },
        "today": {
            "new_registrations": 2,
            "tasks_submitted": 5,
            "tasks_approved": 3,
            "xp_awarded": 250,
            "errors": 0
        }
    }
    """
    ensure_analytics_dir()
    
    try:
        # Add timestamp if not present
        if "timestamp" not in snapshot:
            snapshot["timestamp"] = datetime.utcnow().isoformat()
        
        with open(SUPERVISION_SUMMARY, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        logger.error(f"Failed to update supervision summary: {e}")
        return False


def log_bot_startup(
    users_total: int,
    departments: int,
    pending_submissions: int,
    errors_count: int = 0,
) -> bool:
    """Log bot startup event."""
    data = {
        "users": users_total,
        "depts": departments,
        "pending_submissions": pending_submissions,
        "errors_today": errors_count,
    }
    return log_supervision_event("BOT_START", data)


def log_periodic_check(
    users_online: int,
    tasks_open: int,
    idea_backlog: int,
    pending_submissions: int,
) -> bool:
    """Log periodic health check event."""
    data = {
        "users_online": users_online,
        "tasks_open": tasks_open,
        "idea_backlog": idea_backlog,
        "pending_submissions": pending_submissions,
    }
    return log_supervision_event("PERIODIC", data)


def log_daily_health(
    xp_awarded_today: int,
    admin_actions: int,
    error_count: int,
    error_rate: float = 0.0,
) -> bool:
    """Log daily health metrics."""
    data = {
        "xp_awarded_today": xp_awarded_today,
        "admin_actions_today": admin_actions,
        "error_rate": f"{error_rate:.1%}",
        "total_errors": error_count,
    }
    return log_supervision_event("HEALTH", data)


def get_supervision_summary() -> Optional[Dict[str, Any]]:
    """Get current supervision summary."""
    try:
        if SUPERVISION_SUMMARY.exists():
            with open(SUPERVISION_SUMMARY, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    except Exception as e:
        logger.error(f"Failed to read supervision summary: {e}")
        return None


def get_supervision_log(lines_limit: int = 50) -> list:
    """Get recent supervision log entries."""
    try:
        if not SUPERVISION_LOG.exists():
            return []
        
        with open(SUPERVISION_LOG, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        # Return last N lines
        return all_lines[-lines_limit:]
    except Exception as e:
        logger.error(f"Failed to read supervision log: {e}")
        return []


# Initialize on import
ensure_analytics_dir()
