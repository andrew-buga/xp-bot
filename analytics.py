"""
Analytics Module - Centralized event logging for XP-Bot

Events are logged to analytics/events.jsonl (one JSON object per line).
This creates an immutable audit trail for analysis, debugging, and supervision.

Usage:
    from analytics import log_event
    log_event('task_submitted', user_id=123, data={'task_id': 42, 'difficulty': 'medium'})
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ANALYTICS_DIR = Path("analytics")
EVENTS_FILE = ANALYTICS_DIR / "events.jsonl"


def ensure_analytics_dir():
    """Create analytics directory if it doesn't exist."""
    ANALYTICS_DIR.mkdir(exist_ok=True)
    
    # Create subdirectories
    (ANALYTICS_DIR / "reports").mkdir(exist_ok=True)


def log_event(
    event_type: str,
    user_id: Optional[int] = None,
    data: Optional[Dict[str, Any]] = None,
    admin_id: Optional[int] = None,
) -> bool:
    """
    Log an event to the analytics stream.
    
    Args:
        event_type: Type of event (e.g., 'user_registered', 'task_submitted', 'error')
        user_id: User ID involved in the event (can be None for system events)
        data: Additional event data (dict with any structure)
        admin_id: Admin user ID if this was an admin action
        
    Returns:
        bool: True if logged successfully, False if error occurred
        
    Event Types:
        - user_registered: User joined via /start
        - task_submitted: User submitted task proof
        - task_approved: Admin approved task submission
        - task_rejected: Admin rejected task submission
        - xp_awarded: XP given to user (task, admin bonus, shop)
        - xp_spent: User spent XP in shop
        - idea_submitted: User submitted feedback/idea
        - idea_approved: Admin approved idea
        - admin_action: Admin performed action (ban, role change, etc)
        - error: Exception occurred in handler
        - performance: Performance metric (latency, DB query time)
        - bot_startup: Bot initialization
        - bot_shutdown: Bot shutdown
    """
    ensure_analytics_dir()
    
    try:
        event = {
            "event": event_type,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Add optional fields
        if user_id is not None:
            event["user_id"] = user_id
        if admin_id is not None:
            event["admin_id"] = admin_id
        if data:
            event.update(data)
        
        # Append to events.jsonl (one event per line)
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to log event {event_type}: {e}")
        return False


def log_user_action(
    event_type: str,
    user_id: int,
    action_data: Dict[str, Any],
) -> bool:
    """Convenience function for user-triggered events."""
    return log_event(event_type, user_id=user_id, data=action_data)


def log_admin_action(
    event_type: str,
    admin_id: int,
    target_user_id: Optional[int] = None,
    action_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """Convenience function for admin actions."""
    data = action_data or {}
    if target_user_id is not None:
        data["target_user_id"] = target_user_id
    return log_event(event_type, admin_id=admin_id, data=data)


def log_error(
    error_type: str,
    user_id: Optional[int] = None,
    handler: Optional[str] = None,
    error_msg: Optional[str] = None,
    traceback_str: Optional[str] = None,
) -> bool:
    """Log an error event with context."""
    data = {"error_type": error_type}
    if handler:
        data["handler"] = handler
    if error_msg:
        data["error_message"] = str(error_msg)[:500]  # Limit to 500 chars
    if traceback_str:
        data["traceback"] = traceback_str[:1000]  # Limit to 1000 chars
    
    return log_event("error", user_id=user_id, data=data)


def get_events_count() -> int:
    """Get total number of events logged so far."""
    try:
        if EVENTS_FILE.exists():
            with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        return 0
    except Exception as e:
        logger.error(f"Failed to count events: {e}")
        return 0


def get_recent_events(limit: int = 100) -> list:
    """Get the most recent N events."""
    try:
        if not EVENTS_FILE.exists():
            return []
        
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        
        return events
    except Exception as e:
        logger.error(f"Failed to read recent events: {e}")
        return []


def get_events_by_type(event_type: str) -> list:
    """Get all events of a specific type."""
    try:
        if not EVENTS_FILE.exists():
            return []
        
        events = []
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    if event.get("event") == event_type:
                        events.append(event)
                except json.JSONDecodeError:
                    continue
        
        return events
    except Exception as e:
        logger.error(f"Failed to read events by type {event_type}: {e}")
        return []


# Initialize on import
ensure_analytics_dir()
