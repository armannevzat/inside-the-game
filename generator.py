TEAMS = {
    "home": {
        "name": "Kazafani United",
        "players": {
            "H1":  {"name": "Arman Nevzat",       "position": "GK"},
            "H2":  {"name": "Aydan Nevzat",     "position": "DEF"},
            "H3":  {"name": "Eren Nevzat",    "position": "DEF"},
            "H4":  {"name": "Irfan Nevzat",     "position": "DEF"},
            "H5":  {"name": "Ada Binatlioglu",    "position": "DEF"},
            "H6":  {"name": "Daniel Marhoom",   "position": "MID"},
            "H7":  {"name": "Berk Kalfaoglu",      "position": "MID"},
            "H8":  {"name": "Olgun Jack Karabulut",      "position": "MID"},
            "H9":  {"name": "Farid Taherzadeh",      "position": "FWD"},
            "H10": {"name": "Emir Ergun",    "position": "FWD"},
            "H11": {"name": "Adil Erguler",       "position": "FWD"},
        },
    },
    "away": {
        "name": "Magusa Athletic",
        "players": {
            "A1":  {"name": "Kemal Tavukcu",        "position": "GK"},
            "A2":  {"name": "Cemil Kabakulak",      "position": "DEF"},
            "A3":  {"name": "Orhan Patlican",       "position": "DEF"},
            "A4":  {"name": "Necati Karpuz",        "position": "DEF"},
            "A5":  {"name": "Huseyin Zeytinoglu",   "position": "DEF"},
            "A6":  {"name": "Sedat Tulumbaci",      "position": "MID"},
            "A7":  {"name": "Bekir Halloumoglu",    "position": "MID"},
            "A8":  {"name": "Tuncay Kaymakoglu",    "position": "MID"},
            "A9":  {"name": "Zeki Simitci",         "position": "FWD"},
            "A10": {"name": "Rustem Pirpirim",      "position": "FWD"},
            "A11": {"name": "Mahmut Cokertme",      "position": "FWD"},
        },
    }
}


import random
from schema.events import PassEvent, ShotEvent, GoalEvent, TackleEvent, PressureEvent, PossessionChangeEvent, Team, Location

random.seed(3)


def make_pass(seq, minute, second, team_key, period):
    player_ids = list(TEAMS[team_key]["players"])
    passer, receiver = random.sample(player_ids, 2)

    start = Location(x=random.uniform(0, 105), y=random.uniform(0, 68))
    end = Location(
        x=min(105, max(0, start.x + random.uniform(-30, 30))),
        y=min(68, max(0, start.y + random.uniform(-20, 20))),
    )
    distance = ((end.x - start.x) ** 2 + (end.y - start.y) ** 2) ** 0.5

    return PassEvent(
        match_id="match-001",
        seq=seq,
        minute=minute,
        second=second,
        period=period,
        team=Team(team_key),
        player_id=passer,
        location=start,
        recipient_id=receiver,
        end_location=end,
        distance_m=round(distance, 1),
        completed=(distance <= 50) and (random.random() <0.85),
        difficulty=round(min(distance / 60, 1), 2),
    )


def make_shot(seq, minute, second, team_key, period):
    shooter = random.choice(list(TEAMS[team_key]["players"]))
    goal_x = 105 if team_key == "home" else 0
    if team_key == "home":
        x = goal_x - random.uniform(3, 25)
    else:
        x = goal_x + random.uniform(3, 25)
    y = random.uniform(20, 48)
    dist = ((goal_x - x) ** 2 + (34 - y) ** 2) ** 0.5
    xg = round(max(0.02, 0.5 - dist / 50), 2)

    return ShotEvent(
        match_id="match-001",
        seq=seq,
        minute=minute,
        second=second,
        period=period,
        team=Team(team_key),
        player_id=shooter,
        location=Location(x=x, y=y),
        on_target=random.random() < 0.4,
        shot_speed_kmh=round(random.uniform(60, 120), 1),
        xg=xg,
    )

import json


def generate_match():
    events = []
    seq = 1
    possession = "home"
    remaining = random.randint(5,15)
    for period in (1, 2):
        for m in range(45):
            minute = m if period == 1 else 45 + m
            seconds = sorted(random.randint(0, 59) for _ in range(8))
            for second in seconds:
                events.append(make_pass(seq, minute, second, possession, period))
                seq += 1
                if random.random() < 0.08:
                    defender = "away" if possession == "home" else "home"
                    events.append(PressureEvent(
                        match_id="match-001", seq=seq, minute=minute,
                        second=second, period=period, team=Team(defender),
                        player_id=random.choice(list(TEAMS[defender]["players"])),
                        intensity=round(random.uniform(0.2, 1.0), 2),
                    ))
                    seq += 1
                remaining -= 1
                if remaining == 0:
                    if random.random() < 0.3:
                        shot = make_shot(seq, minute, second, possession, period)
                        events.append(shot)
                        seq += 1
                        if shot.on_target and random.random() < shot.xg * 2:
                            events.append(GoalEvent(
                                match_id="match-001", seq=seq, minute=minute,
                                second=second, period=period,
                                team=Team(possession), player_id=shot.player_id,
                            ))
                            seq += 1

                    new_team = "away" if possession == "home" else "home"
                    reason = random.choice(["tackle", "interception", "out_of_play", "foul", "turnover"])
                    if reason == "tackle":
                        events.append(TackleEvent(
                            match_id="match-001", seq=seq, minute=minute,
                            second=second, period=period, team=Team(new_team),
                            player_id=random.choice(list(TEAMS[new_team]["players"])),
                            won=True,
                        ))
                        seq += 1
                    events.append(PossessionChangeEvent(
                        match_id="match-001", seq=seq, minute=minute,
                        second=second, period=period, team=Team(new_team),
                        reason=reason,
                    ))
                    seq += 1
                    possession = new_team
                    remaining = random.randint(5, 15)
    return events


events = generate_match()
with open("match.json", "w") as f:
    json.dump([e.model_dump(mode="json") for e in events], f, indent=2)
print(len(events), "events written to match.json")

print("home shots:", sum(1 for e in events if isinstance(e, ShotEvent) and e.team == Team.HOME))
print("away shots:", sum(1 for e in events if isinstance(e, ShotEvent) and e.team == Team.AWAY))
print("goals:", sum(1 for e in events if isinstance(e, GoalEvent)))

print("home goals:", sum(1 for e in events if isinstance(e, GoalEvent) and e.team == Team.HOME))
print("away goals:", sum(1 for e in events if isinstance(e, GoalEvent) and e.team == Team.AWAY))

from collections import Counter
print(Counter(e.type.value for e in events))