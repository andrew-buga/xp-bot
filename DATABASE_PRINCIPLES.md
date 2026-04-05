# Database Integrity Principles & Architecture

**Last Updated**: After critical department loss investigation  
**Status**: Active Defense System  
**Priority**: 🔴 CRITICAL

---

## 1. Core Principle: Users Can NEVER Lose Data

### Golden Rule
> **НИКОГДА НЕ ВГАДУВАЙ** — Data operations MUST verify → ensure → test → deploy

Every data change that affects users must follow this workflow:
1. **Verify** current state in logs/DB
2. **Ensure** safety checks exist in code
3. **Test** with real scenarios
4. **Only then Deploy**

### Why This Matters
Users depend on:
- Department assignments (affects which tasks they see)
- XP accumulation (affects rewards)
- Submission history (proof of work)
- Role permissions (affects access)

Losing any of this breaks the bot for users and forces re-registration.

---

## 2. The Lost Departments Problem (FIXED)

### What Happened
```
User 5266708533: Had depts=[4,5] at 19:39 → lost all deps by 21:12
User 498249299:  Had depts=[5] at 16:39 → lost all deps by 17:05
```

### Root Causes Found & Fixed

#### 1️⃣ **Handler Chain Issue** ✅ FIXED
**Problem**: `handle_department_selection()` returned `None` instead of `True`
- Allowed subsequent handlers to also process the same callback
- Could cause state corruption if multiple handlers ran

**Fix**: All callback handlers now return `True` to stop the chain:
```python
return True  # 🔒 Stop handler chain to prevent double-processing
```

#### 2️⃣ **Non-Atomic Database Operations** ✅ FIXED
**Problem**: Department updates were 3 separate DB operations:
```python
current_depts = get_user_departments()  # Read from DB
for dept_id in current_depts:
    if dept_id not in selected:
        remove_user_department()  # Write to DB ← Connection could fail here
for dept_id in selected:
    if dept_id not in current_depts:
        add_user_department()     # Write to DB ← Or here
```

If connection failed between operations, user could end up with partial updates.

**Fix**: New atomic function `atomic_update_user_departments(user_id, new_dept_ids)`:
```python
# All operations in single transaction
- Validates: Non-empty department list required
- Compares: Current vs new departments
- Deletes: Old departments (if removed)
- Inserts: New departments (if added)
- Commits: Everything at once or nothing
- Verifies: Reads back from DB to confirm
```

Usage in bot.py:
```python
try:
    atomic_update_user_departments(user_id, selected)
except ValueError:  # 0 depts
    # Show error to user
except Exception:   # DB error
    # Retry or show sync error
```

#### 3️⃣ **Context Corruption Risk** ✅ MITIGATED
**Problem**: `ctx.user_data["selected_depts"]` could become out-of-sync with DB
- User navigates between settings/change depts menus
- Context might not reflect actual DB state

**Mitigation**:
- `show_department_selection()` fetches current depts from DB
- `on_button()` refreshes context for each menu entry
- `handle_department_selection()` checks if context exists before reuse
- Always reread from DB between major operations

---

## 3. Database Architecture Rules

### Rule #1: Single Source of Truth
The database is always the authoritative source. Context (`ctx.user_data`) is only a temporary session state.

**Good** ✅:
```python
# Fetch fresh data from DB before critical operation
current_depts = get_user_departments(user_id)  # Hit DB
atomic_update_user_departments(user_id, new_depts)  # Atomic update
```

**Bad** ❌:
```python
# Assuming context hasn't changed (could be stale!)
selected = ctx.user_data.get("selected_depts", [])
# User might have changed departments in another session
remove_user_department(user_id, selected[0])
```

### Rule #2: Atomic Operations for Multi-Step Changes
Any operation that involves multiple DB writes must use transactions.

**Good** ✅:
```python
def atomic_update_user_departments(user_id, new_dept_ids):
    """Atomic: delete old, add new, verify all at once"""
```

**Bad** ❌:
```python
remove_user_department(user_id, 1)  # If bot crashes here...
add_user_department(user_id, 2)     # ...user loses dept 1 and never gets dept 2!
```

### Rule #3: Validate Before Modifying
Every data change must have pre-flight checks.

**Good** ✅:
```python
if not new_dept_ids:
    raise ValueError("User cannot have 0 departments")
atomic_update_user_departments(user_id, new_dept_ids)
```

**Bad** ❌:
```python
# What if selected_depts was somehow empty?
atomic_update_user_departments(user_id, selected_depts)  # User loses all depts!
```

### Rule #4: Log Everything
Every data modification must be logged with context.

**Good** ✅:
```python
logger.info(f"📝 Department selection for {user_id}:")
logger.info(f"   Current: {current_depts}")
logger.info(f"   New: {selected}")
logger.info(f"✅ UPDATE COMPLETE: {final_depts}")
```

**Bad** ❌:
```python
# Silent update - how will we debug if it goes wrong?
atomic_update_user_departments(user_id, depts)
```

### Rule #5: Handler Chain Discipline
Callback handlers must return `True` to stop handler chain.

**Good** ✅:
```python
async def handle_department_selection():
    # Process
    return True  # Stop other handlers from also processing
```

**Bad** ❌:
```python
async def handle_department_selection():
    # Process
    return  # Allows other handlers to also process this callback!
```

---

## 4. User-Impacting Operations Checklist

Before deploying any code that modifies user data:

### ✓ Pre-Deployment Checklist

- [ ] **Data Flow Documented**: Every place user data changes is documented
- [ ] **Atomic Operation Used**: Multi-step changes use transactions
- [ ] **Validation in Place**: Edge cases (0 depts, empty values) handled
- [ ] **Logging Added**: Every data change has debug logs with context
- [ ] **Error Handling**: Failures don't leave users in bad state
- [ ] **Tested Locally**: Scenario tested with test user first
- [ ] **Production Plan**: How to recover if deployed wrong
- [ ] **Rollback Ready**: Can revert if issues found

### Example: Adding a new feature that changes departments

```python
# ❌ BAD - No safety checks
def change_dept(user_id, new_dept):
    remove_user_department(user_id, 1)
    add_user_department(user_id, 2)

# ✅ GOOD - Production-ready
def change_dept(user_id, old_dept, new_dept):
    """Safely change user department"""
    # Validate
    if old_dept not in get_user_departments(user_id):
        logger.warning(f"User {user_id} doesn't have dept {old_dept}")
        return False
    
    # Log before
    logger.info(f"📝 Changing dept for {user_id}: {old_dept} → {new_dept}")
    
    # Operate atomically
    result = atomic_update_user_departments(user_id, list(set(
        [d for d in get_user_departments(user_id) if d != old_dept] + [new_dept]
    )))
    
    # Verify
    final_depts = get_user_departments(user_id)
    if new_dept in final_depts:
        logger.info(f"✅ Department change successful: {final_depts}")
        return True
    else:
        logger.error(f"❌ Department change FAILED for {user_id}")
        return False
```

---

## 5. Database Recovery Procedures

If users lose data:

### Step 1: Find the Problem
```bash
# Check journalctl for the exact time
journalctl -u xp-bot --no-pager | grep -E "depts=|Department"

# Sample DB to see current state
sqlite3 bot_data.db ".mode column" "SELECT user_id, count(*) as dept_count FROM users_departments GROUP BY user_id;"
```

### Step 2: Verify Against Logs
```bash
# Find the last moment user had correct data
journalctl -u xp-bot --no-pager | grep "User 123456"
```

### Step 3: Restore
**NEVER guess when**. Always:
1. Find exact time in logs when dept was assigned
2. Check if it matches logs from other users
3. Run restore script with `--verify` first
4. Only deploy if verified

---

## 6. Code Patterns to Avoid

### ❌ Anti-Pattern #1: Silent Failures
```python
# BAD: No error handling
for dept_id in depts:
    remove_user_department(user_id, dept_id)  # What if this fails?
```

**Better**:
```python
try:
    atomic_update_user_departments(user_id, new_depts)
    logger.info(f"✅ Updated: {new_depts}")
except Exception as e:
    logger.error(f"❌ Failed: {e}")
    # Tell user to try again
```

### ❌ Anti-Pattern #2: Assuming Context is Fresh
```python
# BAD: Multiple callbacks might modify context
selected = ctx.user_data["selected_depts"]  # Could be stale!
atomic_update_user_departments(user_id, selected)
```

**Better**:
```python
# Refetch if critical
current = get_user_departments(user_id)  # Fresh from DB
selected = ctx.user_data.get("selected_depts", current)  # Use context if available
atomic_update_user_departments(user_id, selected)
```

### ❌ Anti-Pattern #3: Partial Ownership
```python
# BAD: Two functions modifying same data
def remove_depts():
    remove_user_department(uid, 1)

def add_depts():
    add_user_department(uid, 2)  # Called after remove_depts()

# If something fails between them, user is inconsistent
```

**Better**:
```python
def update_depts(uid, old_depts, new_depts):
    """Single function owns the entire operation"""
    atomic_update_user_departments(uid, new_depts)
```

---

## 7. Monitoring & Early Warning

### Important Logs to Watch
```bash
# Watch for department losses in real-time
journalctl -u xp-bot -f | grep -E "ATOMIC UPDATE|🗑️|❌"

# Check for failed updates
journalctl -u xp-bot | grep "❌ ATOMIC UPDATE FAILED"

# Find users with 0 departments (should almost never happen)
sqlite3 bot_data.db "SELECT u.user_id, u.username FROM users u WHERE u.user_id NOT IN (SELECT DISTINCT user_id FROM users_departments);"
```

### Alert Triggers
- ✅ Any user with 0 departments (except brand new users)
- ✅ Any "❌ ATOMIC UPDATE FAILED" in logs
- ✅ Any manual remove_user_department following add_user_department for same user/dept

---

## 8. Context: Why This Happened

### The Incident
1. User auto-registration feature was added (ensure_user_exists)
2. It created incomplete user records (no departments)
3. Users had to re-register
4. Department loss occurred during re-registration flow
5. Suspected race condition in handler chain

### What We Learned
- Always validate input data before operations
- Handler chain can cause issues if not properly terminated
- Single threaded async code can still have race conditions
- Users expect dept assignments to persist forever
- Logging is the only way to debug async issues

---

## 9. Future Improvements

### Planned
- [ ] Implement proper database connection pooling
- [ ] Add database migration system
- [ ] Create audit log table for all user data changes
- [ ] Implement database backup before major operations
- [ ] Add data integrity checks on startup

### Considered
- Using proper ORM (SQLAlchemy) instead of raw SQL
- Implementing database triggers for validation
- Adding user notification for data changes

---

## 10. Quick Reference: Safe Department Updates

```python
# CORRECT WAY to update user departments
from database import atomic_update_user_departments

async def safe_update_depts(user_id, new_dept_ids):
    """Example: Safe department update"""
    try:
        # Validate
        if not new_dept_ids:
            logger.error(f"Cannot remove all depts for {user_id}")
            return False
        
        # Log intent
        logger.info(f"Updating {user_id} depts to {new_dept_ids}")
        
        # Operate
        atomic_update_user_departments(user_id, new_dept_ids)
        
        # Verify
        return get_user_departments(user_id) == sorted(new_dept_ids)
        
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return False
```

---

**Remember**: User data is sacred. When in doubt, verify from logs first.
