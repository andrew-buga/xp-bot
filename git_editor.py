#!/usr/bin/env python3
"""Git sequence editor to mark commits for reword"""
import sys

if len(sys.argv) < 2:
    sys.exit(0)

todo_file = sys.argv[1]

# Commit hashes to change
commits_to_reword = {
    "0228e7f",
    "33adb56", 
    "8bb4aad",
}

with open(todo_file, 'r') as f:
    lines = f.readlines()

# Mark specified commits for reword
new_lines = []
for line in lines:
    for commit in commits_to_reword:
        if line.startswith(f'pick {commit}'):
            line = line.replace('pick', 'reword', 1)
            break
    new_lines.append(line)

with open(todo_file, 'w') as f:
    f.writelines(new_lines)
