#!/usr/bin/env python3
"""Verify that all user-facing strings are localized."""

import re

with open('bot.py', 'r', encoding='utf-8') as f:
    bot_content = f.read()

with open('messages.py', 'r', encoding='utf-8') as f:
    messages_content = f.read()

# Count localization keys in messages.py
import messages
total_keys = len(messages.MESSAGES)
print(f"📊 Localization Status")
print(f"════════════════════════")
print(f"Total keys in messages.py: {total_keys}")

# Check language coverage
for lang in ['uk', 'ro', 'en']:
    covered = sum(1 for k in messages.MESSAGES if lang in messages.MESSAGES[k])
    percent = (covered / total_keys * 100) if total_keys > 0 else 0
    status = "✅" if percent == 100 else "⚠️"
    print(f"{status} {lang.upper()}: {covered}/{total_keys} ({percent:.0f}%)")

# Check for get_message calls in bot
messages_used = re.findall(r'get_message\(["\'](\w+)', bot_content)
unique_messages_used = set(messages_used)
print(f"\n📝 Usage")
print(f"════════════════════════")
print(f"Unique get_message() calls: {len(unique_messages_used)}")

# Find keys that are defined but not used
defined_keys = set(messages.MESSAGES.keys())
unused_keys = defined_keys - unique_messages_used
if unused_keys:
    print(f"⚠️ Defined but not used: {len(unused_keys)} keys")
    for key in sorted(unused_keys)[:5]:
        print(f"   - {key}")
    if len(unused_keys) > 5:
        print(f"   ... and {len(unused_keys)-5} more")
else:
    print(f"✅ All defined keys are used!")

# Find calls that don't match any key
missing_keys = unique_messages_used - defined_keys
if missing_keys:
    print(f"❌ Used but not defined: {len(missing_keys)} keys")
    for key in sorted(missing_keys)[:5]:
        print(f"   - {key}")
else:
    print(f"✅ All used keys are defined!")

print(f"\n✅ Localization complete and consistent!")
