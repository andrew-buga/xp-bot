"""
Analytics Report Generator - Analyzes events and generates daily reports

Run this script daily to generate analytics reports:
    python analytics_report.py

Creates: analytics/reports/daily_{YYYY-MM-DD}.json

Reports include:
- User metrics (DAU, registrations, role distribution)
- Task metrics (submissions, approvals, completion rate, review latency)
- Idea metrics (submissions, approval rate)
- XP metrics (total awarded, by source)
- Error metrics (frequency, types)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

ANALYTICS_DIR = Path("analytics")
EVENTS_FILE = ANALYTICS_DIR / "events.jsonl"
REPORTS_DIR = ANALYTICS_DIR / "reports"


def ensure_dirs():
    """Create necessary directories."""
    ANALYTICS_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)


def parse_events(date_str: str = None) -> List[Dict[str, Any]]:
    """
    Parse events from events.jsonl for a specific date.
    
    Args:
        date_str: Date in YYYY-MM-DD format. If None, uses today.
        
    Returns:
        List of event dicts that occurred on that date.
    """
    if not EVENTS_FILE.exists():
        return []
    
    if date_str is None:
        date_str = datetime.utcnow().date().isoformat()
    
    # Parse as YYYY-MM-DD
    target_date = datetime.fromisoformat(date_str).date()
    
    events = []
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
                event_timestamp = datetime.fromisoformat(event["timestamp"])
                event_date = event_timestamp.date()
                
                if event_date == target_date:
                    events.append(event)
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
    
    return events


def analyze_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze events and generate metrics.
    
    Returns:
        Dict with comprehensive metrics
    """
    report = {
        "date": datetime.utcnow().date().isoformat(),
        "users": {},
        "tasks": {},
        "ideas": {},
        "xp": {},
        "errors": {},
    }
    
    # Filter events by type
    by_type = defaultdict(list)
    for event in events:
        by_type[event.get("event", "unknown")].append(event)
    
    # === USER METRICS ===
    registrations = by_type.get("user_registered", [])
    active_users = set()
    users_by_role = Counter()
    
    for event in events:
        if "user_id" in event:
            active_users.add(event["user_id"])
    
    report["users"]["active"] = len(active_users)
    report["users"]["registered_today"] = len(registrations)
    
    # === TASK METRICS ===
    submissions = by_type.get("task_submitted", [])
    approvals = by_type.get("task_approved", [])
    rejections = by_type.get("task_rejected", [])
    
    submission_ids = set()
    for s in submissions:
        submission_ids.add(s.get("submission_id", f"{s.get('user_id')}_{events.index(s)}"))
    
    total_submitted = len(submissions)
    total_approved = len(approvals)
    total_rejected = len(rejections)
    
    report["tasks"]["submitted"] = total_submitted
    report["tasks"]["approved"] = total_approved
    report["tasks"]["rejected"] = total_rejected
    report["tasks"]["approval_rate"] = (
        total_approved / total_submitted if total_submitted > 0 else 0
    )
    
    # Calculate review latency (if timestamps exist)
    latencies = []
    approval_by_submission = {a.get("submission_id"): a for a in approvals}
    
    for submission in submissions:
        sub_id = submission.get("submission_id")
        if sub_id and sub_id in approval_by_submission:
            approval = approval_by_submission[sub_id]
            try:
                sub_time = datetime.fromisoformat(submission["timestamp"])
                app_time = datetime.fromisoformat(approval["timestamp"])
                latency_minutes = (app_time - sub_time).total_seconds() / 60
                if latency_minutes >= 0:  # Only count positive latencies
                    latencies.append(latency_minutes)
            except ValueError:
                pass
    
    if latencies:
        report["tasks"]["avg_review_latency_minutes"] = sum(latencies) / len(latencies)
    
    # Task difficulty breakdown
    difficulty_counts = Counter(s.get("difficulty", "unknown") for s in submissions)
    if difficulty_counts:
        report["tasks"]["by_difficulty"] = dict(difficulty_counts)
    
    # === IDEA METRICS ===
    idea_submissions = by_type.get("idea_submitted", [])
    idea_approvals = by_type.get("idea_approved", [])
    
    anonymous_count = sum(1 for i in idea_submissions if i.get("anonymous", False))
    
    report["ideas"]["submitted"] = len(idea_submissions)
    report["ideas"]["approved"] = len(idea_approvals)
    report["ideas"]["anonymous_count"] = anonymous_count
    report["ideas"]["approval_rate"] = (
        len(idea_approvals) / len(idea_submissions) if len(idea_submissions) > 0 else 0
    )
    
    # === XP METRICS ===
    xp_awards = by_type.get("xp_awarded", [])
    xp_spends = by_type.get("xp_spent", [])
    
    total_xp_awarded = 0
    xp_by_source = Counter()
    
    for award in xp_awards:
        amount = award.get("amount", 0)
        total_xp_awarded += amount
        source = award.get("source", "unknown")
        xp_by_source[source] += amount
    
    total_xp_spent = sum(s.get("amount", 0) for s in xp_spends)
    
    report["xp"]["total_awarded"] = total_xp_awarded
    report["xp"]["total_spent"] = total_xp_spent
    report["xp"]["by_source"] = dict(xp_by_source)
    report["xp"]["avg_per_active_user"] = (
        total_xp_awarded / len(active_users) if active_users else 0
    )
    
    # === ERROR METRICS ===
    errors = by_type.get("error", [])
    error_types = Counter(e.get("error_type", "unknown") for e in errors)
    handler_errors = Counter(e.get("handler", "unknown") for e in errors)
    
    report["errors"]["total"] = len(errors)
    if errors:
        report["errors"]["by_type"] = dict(error_types)
        report["errors"]["by_handler"] = dict(handler_errors)
    
    # Error rate
    total_events = len(events)
    report["errors"]["rate"] = len(errors) / total_events if total_events > 0 else 0
    
    return report


def save_report(report: Dict[str, Any], date_str: str = None) -> bool:
    """Save report to JSON file."""
    ensure_dirs()
    
    if date_str is None:
        date_str = report.get("date", datetime.utcnow().date().isoformat())
    
    report_file = REPORTS_DIR / f"daily_{date_str}.json"
    
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Report saved to {report_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        return False


def generate_daily_report(date_str: str = None) -> bool:
    """
    Generate and save daily analytics report.
    
    Args:
        date_str: Date in YYYY-MM-DD format. If None, generates for today.
        
    Returns:
        bool: True if successful
    """
    if date_str is None:
        date_str = datetime.utcnow().date().isoformat()
    
    logger.info(f"📊 Generating report for {date_str}...")
    
    events = parse_events(date_str)
    logger.info(f"   Found {len(events)} events")
    
    if not events:
        logger.warning(f"   No events found for {date_str}")
        return False
    
    report = analyze_events(events)
    report["date"] = date_str
    
    # Print summary
    logger.info(f"   Active users: {report['users']['active']}")
    logger.info(f"   Task submissions: {report['tasks']['submitted']}")
    logger.info(f"   Tasks approved: {report['tasks']['approved']} ({report['tasks']['approval_rate']:.1%})")
    logger.info(f"   Ideas submitted: {report['ideas']['submitted']}")
    logger.info(f"   XP awarded: {report['xp']['total_awarded']}")
    logger.info(f"   Errors: {report['errors']['total']}")
    
    return save_report(report, date_str)


def main():
    """Generate reports for yesterday, today, and check for missing reports."""
    ensure_dirs()
    
    logger.info("🔍 XP-Bot Analytics Report Generator")
    logger.info("=" * 50)
    
    # Generate today's report
    today = datetime.utcnow().date().isoformat()
    generate_daily_report(today)
    
    # Generate yesterday's report (if not already generated)
    yesterday = (datetime.utcnow() - timedelta(days=1)).date().isoformat()
    yesterday_file = REPORTS_DIR / f"daily_{yesterday}.json"
    if not yesterday_file.exists():
        generate_daily_report(yesterday)
    
    logger.info("=" * 50)
    logger.info("✅ Report generation complete!")


if __name__ == "__main__":
    main()
