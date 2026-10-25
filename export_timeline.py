"""
export_timeline.py - writes timeline.json for the momentum graph on the web page.

Uses the same momentum rules as interpret.py:
  completed pass = 1, shot = 3 + 10 x xG, pressure = 2 x intensity, tackle won = 2
  net = home - away per minute, smooth = 5-minute rolling average

Then CHECKS itself: the swing size it computes at each swing minute must match
the "change" value interpret.py saved in moments.json.

Run:  python export_timeline.py
"""

import json

from teams import TEAMS


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


data = load("match.json")
events = data["events"] if isinstance(data, dict) else data
moments_data = load("moments.json")
moments = moments_data["moments"] if isinstance(moments_data, dict) else moments_data

# Points per team per minute
first = min(ev["minute"] for ev in events)
last = max(ev["minute"] for ev in events)
points = {m: {"home": 0.0, "away": 0.0} for m in range(first, last + 1)}

for ev in events:
    t = ev.get("type") or ev.get("event_type")
    side = ev["team"]
    m = ev["minute"]
    if t == "pass" and ev.get("completed"):
        points[m][side] += 1
    elif t == "shot":
        points[m][side] += 3 + 10 * (ev.get("xg") or 0)
    elif t == "pressure":
        points[m][side] += 2 * (ev.get("intensity") or 0)
    elif t == "tackle" and ev.get("won"):
        points[m][side] += 2

minutes = list(points)
net = {m: points[m]["home"] - points[m]["away"] for m in minutes}

# 5-minute rolling average: this minute and the four before it
smooth = {}
for m in minutes:
    window = [net[k] for k in range(max(first, m - 4), m + 1)]
    smooth[m] = sum(window) / len(window)

# Self-check against interpret.py's swing values
print("Swing check (should match moments.json):")
for mo in moments:
    if mo["kind"] == "swing":
        m = mo["minute"]
        mine = smooth[m - 1] - smooth[m - 1 - 5]
        print(f"  {m}': moments.json change = {mo.get('change')}, recomputed = {round(mine, 2)}")

out = {
    "home": TEAMS["home"]["name"],
    "away": TEAMS["away"]["name"],
    "minutes": minutes,
    "net": [round(net[m], 2) for m in minutes],
    "smooth": [round(smooth[m], 2) for m in minutes],
}
with open("timeline.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(f"Saved timeline.json: minutes {first}-{last}")
