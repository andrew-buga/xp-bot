#!/usr/bin/env python3
"""Git editor to fix commit messages"""
import sys

# Map old hash to new message
NEW_MESSAGES = {
    "0228e7f": "fix: Fix Ukrainian text - remove mixed language strings and correct verb forms",
    "33adb56": "feat: Add department and difficulty filtering in task edit/delete menus",
    "8bb4aad": "fix: Remove f-prefix from f-strings without placeholders (Ruff F541)",
}

if len(sys.argv) < 2:
    sys.exit(0)

msg_file = sys.argv[1]

# Read current message
with open(msg_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Get first line (commit message)
first_line = lines[0] if lines else ""

# Check if we need to replace this message
# Look for any of our target hashes in git environment
import os
git_commit = os.environ.get('GIT_COMMIT', '')

for commit_hash, new_msg in NEW_MESSAGES.items():
    if git_commit.startswith(commit_hash):
        # Replace the message
        lines = [new_msg + '\n'] + lines[1:]
        break

with open(msg_file, 'w', encoding='utf-8') as f:
    f.writelines(lines)
