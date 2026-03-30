# XP-Bot Analytics & Supervision Documentation

## Overview

The analytics system provides:
- **Event logging**: Immutable audit trail of all bot actions
- **Health monitoring**: Real-time bot state snapshots
- **Data analysis**: Daily/weekly reports with metrics
- **Debugging support**: Historical data for troubleshooting

This enables you to understand how the bot is used, detect issues early, and make data-driven decisions for future updates.

---

## File Structure

```
analytics/
├── events.jsonl              # Raw event log (one JSON event per line, append-only)
├── supervision.log           # Health snapshots and bot status
├── supervision_summary.json  # Current system state (JSON, frequently updated)
└── reports/
    ├── daily_2026-03-30.json
    ├── daily_2026-03-31.json
    └── ...
```

---

## 1. Event Logging (events.jsonl)

### What It Is
- **Append-only log** of all bot events
- **One JSON object per line** (JSON Lines format)
- **Immutable** - once written, never modified
- **Used for**: Debugging, auditing, analysis

### Event Fields

```json
{
  "event": "task_submitted",
  "timestamp": "2026-03-31T14:30:45.123456",
  "user_id": 5266708533,
  "task_id": 42,
  "difficulty": "medium"
}
```

**Standard fields**:
- `event` (string): Event type (required)
- `timestamp` (string): ISO 8601 timestamp in UTC
- `user_id` (int): User ID (optional, None for system events)
- `admin_id` (int): Admin performing action (optional, for admin events)
- Additional fields depend on event type (see below)

### Event Types

#### **User Events**

```jsonl
{"event":"user_registered","timestamp":"...","user_id":123,"language":"uk","depts":[1,5]}
{"event":"task_submitted","timestamp":"...","user_id":123,"task_id":42,"difficulty":"medium"}
{"event":"task_approved","timestamp":"...","user_id":123,"admin_id":498249299,"xp_awarded":50,"submission_id":101}
{"event":"task_rejected","timestamp":"...","user_id":123,"admin_id":498249299,"submission_id":101}
{"event":"xp_awarded","timestamp":"...","user_id":123,"amount":50,"source":"task_approval"}
{"event":"xp_spent","timestamp":"...","user_id":123,"amount":30,"product_id":5}
{"event":"idea_submitted","timestamp":"...","user_id":123,"anonymous":false}
{"event":"idea_approved","timestamp":"...","user_id":123,"admin_id":498249299,"idea_id":15}
```

#### **Admin Events**

```jsonl
{"event":"admin_action","timestamp":"...","admin_id":498249299,"action":"ban_user","target_user_id":123}
{"event":"admin_action","timestamp":"...","admin_id":498249299,"action":"set_role","target_user_id":123,"role":"supervisor"}
{"event":"admin_action","timestamp":"...","admin_id":498249299,"action":"adjust_xp","target_user_id":123,"amount":50}
```

#### **System Events**

```jsonl
{"event":"bot_startup","timestamp":"...","users":3,"depts":5,"pending":2}
{"event":"error","timestamp":"...","user_id":123,"handler":"cmd_tasks","error_type":"KeyError","error_message":"..."}
{"event":"performance","timestamp":"...","handler":"get_user_departments","latency_ms":15}
```

---

## 2. Supervision Monitoring

### supervision.log

Health snapshots appended on bot startup and periodic checks.

```
[2026-03-31T20:49:33] BOT_START: users=3, depts=5, pending_submissions=0, errors_today=0
[2026-03-31T21:00:00] PERIODIC: users_online=2, tasks_open=15, idea_backlog=2, pending_submissions=0
[2026-03-31T21:30:00] HEALTH: xp_awarded_today=150, admin_actions_today=3, error_rate=0.1%, total_errors=0
```

### supervision_summary.json

Current system state snapshot (frequently updated).

```json
{
  "timestamp": "2026-03-31T22:30:00",
  "users": {
    "total": 3,
    "verified": 2,
    "in_departments": 3,
    "by_role": {
      "admin": 1,
      "user": 2
    }
  },
  "system": {
    "pending_submissions": 0,
    "unreviewed_ideas": 2,
    "banned_users": 0,
    "open_tasks": 15
  },
  "today": {
    "new_registrations": 1,
    "tasks_submitted": 4,
    "tasks_approved": 3,
    "xp_awarded": 150,
    "errors": 0
  }
}
```

---

## 3. Analytics Reports

### Daily Reports (daily_YYYY-MM-DD.json)

Generated daily by running `python analytics_report.py`.

Example report:

```json
{
  "date": "2026-03-31",
  "users": {
    "active": 3,
    "registered_today": 1
  },
  "tasks": {
    "submitted": 4,
    "approved": 3,
    "rejected": 1,
    "approval_rate": 0.75,
    "avg_review_latency_minutes": 13.5,
    "by_difficulty": {
      "easy": 2,
      "medium": 2
    }
  },
  "ideas": {
    "submitted": 2,
    "approved": 0,
    "anonymous_count": 1,
    "approval_rate": 0.0
  },
  "xp": {
    "total_awarded": 150,
    "total_spent": 50,
    "by_source": {
      "task_approval": 150
    },
    "avg_per_active_user": 50.0
  },
  "errors": {
    "total": 0,
    "rate": 0.0
  }
}
```

---

## How to Use

### 1. View Recent Events

**See last 20 events**:
```bash
tail -20 analytics/events.jsonl | python -m json.tool
```

**See all events for a user**:
```bash
grep '"user_id":123' analytics/events.jsonl | python -m json.tool
```

**See all errors**:
```bash
grep '"event":"error"' analytics/events.jsonl | python -m json.tool
```

### 2. Check Current System State

```bash
# View current snapshot
python -c "import json; print(json.dumps(json.load(open('analytics/supervision_summary.json')), indent=2))"

# View recent health log
tail -10 analytics/supervision.log
```

### 3. Generate Reports

```bash
# Generate today's report (and yesterday if missing)
python analytics_report.py

# View today's report
python -c "import json; r=json.load(open('analytics/reports/daily_2026-03-31.json')); print(f'Active: {r[\"users\"][\"active\"]}, Submissions: {r[\"tasks\"][\"submitted\"]}, Approval: {r[\"tasks\"][\"approval_rate\"]:.1%}')"
```

### 4. Analyze Patterns

**Which tasks are most submitted?**
```bash
grep '"event":"task_submitted"' analytics/events.jsonl | python -c "
import sys, json
from collections import Counter
tasks = Counter()
for line in sys.stdin:
    event = json.loads(line)
    task_id = event.get('task_id')
    if task_id:
        tasks[task_id] += 1
for task_id, count in tasks.most_common(10):
    print(f'Task {task_id}: {count} submissions')
"
```

**How long does it take to review tasks?**
```python
# Already calculated in daily reports: "avg_review_latency_minutes"
```

**Which users are most active?**
```bash
grep '"event":"task_submitted"' analytics/events.jsonl | python -c "
import sys, json
from collections import Counter
users = Counter()
for line in sys.stdin:
    event = json.loads(line)
    user_id = event.get('user_id')
    if user_id:
        users[user_id] += 1
for user_id, count in users.most_common(10):
    print(f'User {user_id}: {count} submissions')
"
```

---

## Integration with Code

### Adding Event Logging

In `bot.py`, import and use the logging functions:

```python
from analytics import log_event, log_admin_action, log_error

# Log user action
@app.message_handler(commands=['tasks'])
async def cmd_tasks(update, ctx):
    user = update.effective_user
    # ... do something ...
    log_event('task_submitted', user_id=user.id, data={'task_id': 42, 'difficulty': 'medium'})

# Log admin action
await log_admin_action('admin_action', admin_id=admin.id, target_user_id=user.id, 
                       action_data={'action': 'ban_user'})

# Log error
try:
    # something that might fail
except Exception as e:
    log_error('Exception', user_id=user.id, handler='cmd_tasks', error_msg=str(e))
```

### Available Functions

**Analytics module**:
- `log_event(event_type, user_id, data, admin_id)` - General event logging
- `log_user_action(event_type, user_id, action_data)` - Shorthand for user events
- `log_admin_action(event_type, admin_id, target_user_id, action_data)` - Shorthand for admin events
- `log_error(error_type, user_id, handler, error_msg, traceback_str)` - Error logging
- `get_events_count()` - Total events logged
- `get_recent_events(limit)` - Most recent N events
- `get_events_by_type(event_type)` - All events of a type

**Supervision module**:
- `log_bot_startup(users_total, departments, pending_submissions, errors_count)` - Log bot start
- `update_supervision_summary(snapshot)` - Update current state
- `get_supervision_summary()` - Get current state
- `get_supervision_log(lines_limit)` - Get recent supervision log entries

---

## Maintenance

### Daily Tasks

```bash
# Around midnight UTC, run:
python analytics_report.py

# Optionally, backup events file (every 7 days):
cp analytics/events.jsonl analytics/backups/events_$(date +%Y-%m-%d).jsonl.gz
```

### Archiving Old Data

Keep events.jsonl compact by backing up old events:

```bash
# Archive events older than 30 days
python -c "
import json
from pathlib import Path
from datetime import datetime, timedelta

events_file = Path('analytics/events.jsonl')
archive_file = Path('analytics/archive/events_2026_Q1.jsonl')
cutoff = (datetime.utcnow() - timedelta(days=30)).date().isoformat()

recent_events = []
with open(events_file) as f:
    for line in f:
        event = json.loads(line)
        if event['timestamp'][:10] >= cutoff:
            recent_events.append(event)

# Write recent events back
with open(events_file, 'w') as f:
    for event in recent_events:
        f.write(json.dumps(event, ensure_ascii=False) + '\\n')
"
```

---

## FAQ

**Q: Why JSON Lines instead of a database?**  
A: JSON Lines is human-readable, easily appendable, and requires no schema migration. Perfect for an audit trail. You can always migrate to a database later if needed.

**Q: Is there performance overhead?**  
A: Each event logs in ~1-2ms (file write is fast). Even 1000 events/day adds <2 seconds to bot runtime.

**Q: Can I delete old events?**  
A: Yes, but be careful. We recommend archiving instead (copy to separate file, then delete old lines from events.jsonl).

**Q: How do I use this for future updates?**  
A: Before making a breaking change, query analytics to understand current behavior:
- "How many users submit tasks daily?" → Baseline
- Make change → Monitor metrics for 1 week
- Compare: "Are submissions up/down?" → Measure impact

---

## Examples: Using Analytics for Development

### Example 1: "Should we add a new task difficulty?"

**Before deciding:**
```bash
# Check distribution of current tasks
grep '"event":"task_submitted"' analytics/events.jsonl | python -c "
import sys, json
from collections import Counter
diffs = Counter()
for line in sys.stdin:
    event = json.loads(line)
    diffs[event.get('difficulty', 'unknown')] += 1
print('Current difficulty distribution:')
for d, c in diffs.most_common():
    print(f'  {d}: {c}')
"
# Output: easy: 45%, medium: 40%, hard: 15%
# Insight: "Hard tasks are underused, maybe they're too hard. A new 'very_hard' won't help."
```

### Example 2: "Why are some tasks not being submitted?"

**Analyze:**
```python
import json
from collections import Counter

# Count submissions by task
task_submissions = Counter()
with open('analytics/events.jsonl') as f:
    for line in f:
        event = json.loads(line)
        if event['event'] == 'task_submitted':
            task_submissions[event['task_id']] += 1

# Compare with database
from database import get_all_tasks
all_tasks = get_all_tasks()
for task in all_tasks:
    if task['id'] not in task_submissions:
        print(f"Task {task['id']} ({task['title']}) has 0 submissions!")
    elif task_submissions[task['id']] < 2:
        print(f"Task {task['id']} ({task['title']}) only has {task_submissions[task['id']]} submissions")
```

### Example 3: "Admin review latency is high - should we hire more admins?"

**Check reports:**
```bash
python -c "
import json
reports = [
    json.load(open('analytics/reports/daily_2026-03-28.json')),
    json.load(open('analytics/reports/daily_2026-03-29.json')),
    json.load(open('analytics/reports/daily_2026-03-30.json')),
]
for r in reports:
    latency = r['tasks'].get('avg_review_latency_minutes', 0)
    approved = r['tasks']['approved']
    print(f\"{r['date']}: {approved} approved, {latency:.1f} min avg latency\")
"
# Output:
# 2026-03-28: 5 approved, 45.2 min avg latency
# 2026-03-29: 3 approved, 120.5 min avg latency  <- spike!
# 2026-03-30: 8 approved, 15.3 min avg latency  <- back to normal
# Insight: "Latency spikes when fewer admins are available, but recovers quickly"
```

---

## Next Steps

1. **Monitor daily reports** - Check metrics weekly to spot trends
2. **Set up cron job** for `python analytics_report.py` (runs daily)
3. **Define alerts** - E.g., "error rate > 5%" → send notification
4. **Share reports** with team - Use as discussion point for improvements

