# XP & User Data Management Architecture

**Status**: Design Phase  
**Priority**: 🔴 CRITICAL  
**Goal**: Database as Single Source of Truth for All User Data

---

## 1. Current Database Schema Review

### ✅ What We Have

```
users table:
  - user_id (PK)
  - username
  - first_name  
  - xp (current/active XP)
  - total_xp (cumulative XP ever awarded)
  - spendable_xp (XP available for shop)
  - joined_at
  - is_banned
  - language
  - is_verified
  - role
  - ... more fields

submissions table:
  - id (PK)
  - user_id (FK)
  - task_id (FK)
  - status ('pending', 'approved', 'rejected')
  - proof_text, proof_file_id
  - submitted_at, reviewed_at, reviewer_id

tasks table:
  - id (PK)
  - title, description
  - xp_reward
  - difficulty_level
  - department_id

users_departments table:
  - user_id (FK)
  - department_id (FK)
  - dept_role ('member', 'admin')
```

### ⚠️ What's Missing or Weak

1. **No XP Breakdown by Category**
   - Current: Only total_xp
   - Missing: xp_by_category = {dept_id: xp_amount}

2. **No XP History/Audit Log**
   - Current: No history of XP changes
   - Missing: xp_history table = when, how much, source

3. **No User Profile Completeness Tracking**
   - Current: Hard to know what data is missing
   - Missing: profile_fields table tracking what user filled out

4. **Limited Department Context in Users**
   - Current: Need to join users_departments
   - Missing: dept_count, primary_dept in users for quick access

5. **No Transaction History**
   - Current: Only submissions
   - Missing: Full activity log

---

## 2. Enhanced Database Architecture Design

### Phase 1: Add XP Category Tracking (Must Have)

```sql
-- ALTER users table to add:
xp_by_category JSON DEFAULT '{}' -- e.g. {1: 50, 2: 75, 3: 120}

-- Example format:
{
  "1": 20,    -- SMM dept: 20 XP
  "2": 15,    -- Finance dept: 15 XP  
  "3": 30,    -- PM dept: 30 XP
  "4": 0,     -- Comm dept: 0 XP
  "5": 10     -- IT dept: 10 XP
}

Total XP = SUM of all = 75 XP
```

### Phase 2: Add XP History Table

```sql
CREATE TABLE xp_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER FK,
  amount INTEGER,
  source TEXT ('task_approval', 'shop_purchase', 'admin_grant', 'admin_subtract'),
  source_id INTEGER,  -- task_id or submission_id
  category_id INTEGER,  -- department_id or NULL
  balance_before INTEGER,
  balance_after INTEGER,
  timestamp TEXT,
  FOREIGN KEY(user_id) REFERENCES users(user_id)
)
```

### Phase 3: Add User Activity Log Table

```sql
CREATE TABLE user_activity_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER FK,
  event_type TEXT ('submission', 'purchase', 'dept_join', 'dept_leave'),
  event_data JSON,  -- context specific data
  timestamp TEXT,
  FOREIGN KEY(user_id) REFERENCES users(user_id)
)
```

### Phase 4: Add Data Completeness Tracking

```sql
CREATE TABLE user_profile_fields (
  user_id INTEGER FK PRIMARY KEY,
  has_username INTEGER DEFAULT 0,
  has_first_name INTEGER DEFAULT 0,
  has_departments INTEGER DEFAULT 0,
  has_verified_subscription INTEGER DEFAULT 0,
  profile_complete_pct INTEGER DEFAULT 0,  -- 0-100%
  last_updated TEXT,
  FOREIGN KEY(user_id) REFERENCES users(user_id)
)
```

---

## 3. XP Award Safeguard System

### Current Flow (UNSAFE)
```
User submits task
  ↓
Admin approves
  ↓
Call add_xp(user_id, reward) 
  ↓
Update 3 columns (xp, total_xp, spendable_xp)
  ↓
❌ If connection fails mid-operation, data is inconsistent
```

### New Flow (SAFE)

```python
def atomic_award_xp(user_id, amount, task_id, dept_id):
    """
    🔒 ATOMIC: Award XP with full audit trail
    
    Operations:
    1. Create xp_history entry (for audit)
    2. Update users (xp, total_xp, spendable_xp, xp_by_category)
    3. Update activity log
    4. Verify balance matches
    """
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Step 1: Get current balance
        c.execute("SELECT xp, total_xp, spendable_xp, xp_by_category FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        old_xp = user['xp']
        old_category = json.loads(user['xp_by_category'] or '{}')
        
        # Step 2: Calculate new balance
        new_xp = old_xp + amount
        new_category = old_category.copy()
        new_category[str(dept_id)] = new_category.get(str(dept_id), 0) + amount
        
        # Step 3: Update user (atomic)
        c.execute("""
            UPDATE users SET
              xp = ?,
              total_xp = total_xp + ?,
              spendable_xp = spendable_xp + ?,
              xp_by_category = ?
            WHERE user_id = ?
        """, (new_xp, amount, amount, json.dumps(new_category), user_id))
        
        # Step 4: Create history entry
        c.execute("""
            INSERT INTO xp_history (user_id, amount, source, source_id, category_id, balance_before, balance_after, timestamp)
            VALUES (?, ?, 'task_approval', ?, ?, ?, ?, ?)
        """, (user_id, amount, task_id, dept_id, old_xp, new_xp, datetime.now().isoformat()))
        
        # Step 5: Create activity log
        c.execute("""
            INSERT INTO user_activity_log (user_id, event_type, event_data, timestamp)
            VALUES (?, 'submission_approved', ?, ?)
        """, (user_id, json.dumps({'task_id': task_id, 'xp': amount}), datetime.now().isoformat()))
        
        # Step 6: COMMIT (all or nothing)
        conn.commit()
        
        # Step 7: VERIFY
        c.execute("SELECT xp, total_xp FROM users WHERE user_id=?", (user_id,))
        user_after = c.fetchone()
        
        if user_after['total_xp'] != user['total_xp'] + amount:
            logger.error(f"❌ XP AWARD VERIFICATION FAILED for user {user_id}")
            raise Exception("XP verification failed")
        
        logger.info(f"✅ XP awarded: User {user_id} +{amount} XP (balance: {user_after['xp']})")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ XP AWARD FAILED: {e}")
        return False
```

---

## 4. Verification & Recovery Procedures

### Daily Consistency Check

```python
def verify_xp_consistency():
    """Run daily to ensure DB integrity"""
    issues = []
    
    # Check 1: Approved submissions have corresponding XP
    c.execute("""
        SELECT s.id, s.user_id, t.xp_reward, u.total_xp
        FROM submissions s
        JOIN tasks t ON s.task_id = t.id
        JOIN users u ON s.user_id = u.user_id
        WHERE s.status = 'approved'
    """)
    
    total_should = 0
    for submission in c.fetchall():
        total_should += submission['xp_reward']
    
    c.execute("SELECT COALESCE(SUM(total_xp), 0) as total FROM users")
    total_actual = c.fetchone()['total']
    
    if total_should != total_actual:
        issues.append({
            'severity': 'CRITICAL',
            'type': 'xp_mismatch',
            'expected': total_should,
            'actual': total_actual,
            'diff': total_actual - total_should
        })
    
    # Check 2: XP History entries match actual changes
    c.execute("""
        SELECT COALESCE(SUM(amount), 0) as total FROM xp_history
        WHERE source = 'task_approval'
    """)
    history_total = c.fetchone()['total']
    
    # Check 3: Category XP sums match total XP
    # ... similar validation
    
    return issues
```

### Recovery Procedure

If XP inconsistency found:

```bash
# 1. STOP the bot
systemctl stop xp-bot

# 2. BACKUP database
cp bot_data.db bot_data.db.backup.$(date +%s)

# 3. RUN verification
python verify_xp_consistency.py

# 4. IDENTIFY affected users
python find_xp_issues.py

# 5. MANUAL FIX (if needed)
# Never auto-fix - always verify first!
sqlite3 bot_data.db
UPDATE users SET xp=X, total_xp=Y WHERE user_id=Z;
.g fix_submission_id=M;

# 6. RE-VERIFY
python verify_xp_consistency.py

# 7. RESTART
systemctl start xp-bot

# 8. MONITOR
journalctl -u xp-bot -f | grep XP
```

---

## 5. Data Loss Prevention Checklist

### Before Every Production Change

- [ ] Database backup exists
- [ ] Verify current state logged (journalctl)
- [ ] Test change in development
- [ ] Run consistency check before deploy
- [ ] All XP operations use atomic functions
- [ ] Have rollback plan ready
- [ ] Monitor logs for 1 hour after deploy

### In Code

✅ **Must Do**:
- Atomic transactions for multi-step changes
- Comprehensive logging of state before/after
- Validation at every step
- Fallback/rejection if validation fails
- History/audit trail of all changes

❌ **Never**:
- Assume context is current without re-reading DB
- Do partial updates without transactions
- Fail silently - always log errors
- Skip validation "for performance"
- Delete user data without backup

---

## 6. Current Data Integrity Report

### ✅ Status

```
Total users: 4
Approved submissions: 2
Total XP in system: 20 (2 users × 10 XP)
XP awarded vs DB: MATCH ✅
User departments: ALL ASSIGNED ✅
```

### Users with Data

```
User 5266708533 (andriybuga)
  - Depts: [4, 5] ✅
  - XP: 10 total ✅
  - Submissions: 1 approved, 1 rejected

User 1058602390 (viskasmeowww)
  - Depts: [1, 2] ✅
  - XP: 10 total ✅
  - Submissions: 1 approved
```

---

## 7. Implementation Timeline

### Phase 1 (Immediate - This Sprint)
- ✅ Verify current XP consistency
- ✅ Add comprehensive logging to XP operations
- ✅ Create atomic_award_xp() function in database.py
- Update bot.py to use atomic function

### Phase 2 (Next Sprint)
- Add xp_by_category JSON tracking
- Create xp_history table
- Implement daily consistency check job

### Phase 3 (Following Sprint)
- Add user_activity_log table
- Add user_profile_fields tracking
- Create recovery procedures

---

## 8. Code Changes Needed

### database.py

```python
# NEW FUNCTION
def atomic_award_xp(user_id, amount, task_id, dept_id):
    """Award XP with full audit trail and verification"""
    # ... implementation above

# ENHANCED FUNCTION
def add_xp(user_id, amount, source=None, source_id=None, dept_id=None):
    """Wrapper for backward compatibility"""
    if source == 'task_approval':
        return atomic_award_xp(user_id, amount, source_id, dept_id)
    else:
        # Fallback for manual XP grants (admin)
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE users SET
              xp = xp + ?,
              total_xp = total_xp + ?,
              spendable_xp = spendable_xp + ?
            WHERE user_id = ?
        """, (amount, amount, amount, user_id))
        conn.commit()
        conn.close()

# NEW FUNCTION  
def verify_xp_consistency():
    """Check XP integrity and return issues"""
    # ... implementation above
```

### bot.py

```python
# When approving submission (in admin handler)
if action == "approve":
    success = atomic_award_xp(  # ← Use atomic function!
        user_id=sub["user_id"],
        amount=task["xp_reward"],
        task_id=sub["task_id"],
        dept_id=task.get("department_id")
    )
    if success:
        # Continue with approval
    else:
        # Show error, don't mark as approved
```

---

**Key Principle**: Database is authoritative. Context, logs, and frontend are derived from database state. Never guess or assume.
