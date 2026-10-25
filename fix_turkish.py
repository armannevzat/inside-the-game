"""
fix_turkish.py - one-off human correction of personalized.json.

Replaces the English word "five" with Turkish "beş" in the Turkish ("tr") text only,
marks each corrected item's translation source as "ai+edited", and reports any other
English number words left in the Turkish text (it does not change those).

Run once:  python fix_turkish.py
"""

import json
import re

FILE = "personalized.json"
FIVE = re.compile(r"\bfive\b", re.IGNORECASE)
OTHER_ENGLISH = re.compile(r"\b(one|two|three|four|six|seven|eight|nine|ten|minutes?)\b", re.IGNORECASE)


def fix_block(label, item):
    """item is one moment or one player. Fix its "tr" texts in place."""
    changed = False
    for key, text in item["tr"].items():
        new = FIVE.sub(lambda m: "Beş" if m.group(0)[0].isupper() else "beş", text)
        if new != text:
            print(f"{label} [{key}]\n  before: {text}\n  after:  {new}\n")
            item["tr"][key] = new
            changed = True
        leftover = OTHER_ENGLISH.findall(new)
        if leftover:
            print(f"{label} [{key}] still has English words: {leftover}\n  {new}\n")
    if changed:
        item["source"]["translation"] = "ai+edited"
    return changed


with open(FILE, encoding="utf-8") as f:
    data = json.load(f)

count = 0
for mo in data["moments"]:
    count += fix_block(f"Moment {mo['minute']}'", mo)
for pid, p in data["players"].items():
    count += fix_block(f"Player {p['name']}", p)

with open(FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Done: {count} item(s) corrected and marked ai+edited.")
