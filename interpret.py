import json

from teams import TEAMS

with open("match.json") as f:
    events = json.load(f)

stats = {
    "home": {"passes": 0, "completed": 0},
    "away": {"passes": 0, "completed": 0},
}

for e in events:
    if e["type"] == "pass":
        team = e["team"]
        stats[team]["passes"] += 1
        if e["completed"]:
            stats[team]["completed"] += 1
total_passes = stats["home"]["passes"] + stats["away"]["passes"]

for team in ("home", "away"):
    passes = stats[team]["passes"]
    completion = stats[team]["completed"] / passes * 100
    possession = passes / total_passes * 100
    print(team, "| completion %:", round(completion, 1), "| possession %:", round(possession, 1))

from collections import defaultdict

WEIGHTS = {"pass": 1, "shot": 3, "xg": 10, "pressure": 2, "tackle": 2}
points = {"home": defaultdict(float), "away": defaultdict(float)}

for e in events:
    team = e["team"]
    minute = e["minute"]
    if e["type"] == "pass" and e["completed"]:
        points[team][minute] += WEIGHTS["pass"]
    elif e["type"] == "tackle" and e["won"]:
        points[team][minute] += WEIGHTS["tackle"]
    elif e["type"] == "shot":
        points[team][minute] += WEIGHTS["shot"] + WEIGHTS["xg"] * e["xg"]
    elif e["type"] == "pressure":
        points[team][minute] += WEIGHTS["pressure"] * e["intensity"]

net = []
for m in range(90):
    net.append(points["home"][m] - points["away"][m])

WINDOW = 5
smooth = []
for m in range(90):
    start = max(0, m - WINDOW + 1)
    chunk = net[start:m + 1]
    smooth.append(sum(chunk) / len(chunk))

# Peaks, ignoring the first minutes where the window isn't full yet
full = smooth[WINDOW - 1:]
print("home peak:", round(max(full), 1), "at minute", full.index(max(full)) + WINDOW - 1)
print("away peak:", round(min(full), 1), "at minute", full.index(min(full)) + WINDOW - 1)

# ---- Key moments ----
moments = []

for e in events:
    if e["type"] == "goal":
        moments.append({"minute": e["minute"], "second": e["second"],
                        "kind": "goal", "team": e["team"], "player_id": e["player_id"]})
    elif e["type"] == "shot" and e["xg"] >= 0.3:
        moments.append({"minute": e["minute"], "second": e["second"],
                        "kind": "big_chance", "team": e["team"], "player_id": e["player_id"],
                        "xg": e["xg"], "on_target": e["on_target"]})

SWING_WINDOW = 5
SWING_THRESHOLD = 4.0
MIN_GAP = 8
last_swing = -MIN_GAP

goal_moments = [(mo["minute"], mo["team"]) for mo in moments if mo["kind"] == "goal"]

for m in range(WINDOW + SWING_WINDOW, 90):
    change = smooth[m - 1] - smooth[m - 1 - SWING_WINDOW]
    team = "home" if change > 0 else "away"
    goal_in_window = any(t == team and m - SWING_WINDOW <= gm < m for gm, t in goal_moments)
    if abs(change) >= SWING_THRESHOLD and m - last_swing >= MIN_GAP and not goal_in_window:
        moments.append({"minute": m, "second": 0, "kind": "swing",
                        "team": team, "change": round(change, 1)})
        last_swing = m

moments.sort(key=lambda mo: (mo["minute"], mo["second"]))

# Remove the duplicate: a big_chance that was also a goal (same minute, second, player)
goal_keys = {(mo["minute"], mo["second"], mo["player_id"]) for mo in moments if mo["kind"] == "goal"}
moments = [mo for mo in moments
           if not (mo["kind"] == "big_chance"
                   and (mo["minute"], mo["second"], mo["player_id"]) in goal_keys)]


def player_name(team, player_id):
    return TEAMS[team]["players"][player_id]["name"]


def score_at(minute, second):
    score = {"home": 0, "away": 0}
    for e in events:
        if e["type"] == "goal" and (e["minute"], e["second"]) <= (minute, second):
            score[e["team"]] += 1
    return score


def window_stats(moment_minute, moment_second, length_seconds=300):
    end = moment_minute * 60 + moment_second
    start = end - length_seconds
    result = {t: {"passes": 0, "completed": 0, "shots": 0, "xg": 0.0,
                  "pressure_events": 0, "tackles_won": 0} for t in ("home", "away")}
    for e in events:
        t = e["minute"] * 60 + e["second"]
        if start <= t < end:
            s = result[e["team"]]
            if e["type"] == "pass":
                s["passes"] += 1
                if e["completed"]:
                    s["completed"] += 1
            elif e["type"] == "shot":
                s["shots"] += 1
                s["xg"] += e["xg"]
            elif e["type"] == "pressure":
                s["pressure_events"] += 1
            elif e["type"] == "tackle" and e["won"]:
                s["tackles_won"] += 1
    for team in result:
        result[team]["xg"] = round(result[team]["xg"], 2)
    return result

for i, mo in enumerate(moments):
    mo["id"] = i
    after = score_at(mo["minute"], mo["second"])
    mo["score_after"] = after
    if mo["kind"] == "goal":
        before = dict(after)
        before[mo["team"]] -= 1
        mo["score_before"] = before
    if "player_id" in mo:
        mo["player"] = player_name(mo["team"], mo["player_id"])
    mo["window"] = window_stats(mo["minute"], mo["second"])

with open("moments.json", "w") as f:
    json.dump(moments, f, indent=2)

print(len(moments), "key moments saved to moments.json")
print(json.dumps(moments[-1], indent=2))