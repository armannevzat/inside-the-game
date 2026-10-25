"""
personalize.py - Stage 4 of the pipeline.

Three jobs in one file:
  Agent 2  "Personalizer": rewrites each moment for an Analyst and a Casual fan,
                           and writes a one-line "watch" note per focus player.
  Agent 3  "Translator":   translates those texts into one extra language.
  Checker  (plain Python): rejects any AI text with numbers or names that are not
                           in the evidence, banned words, or the wrong length.
                           Rejected -> retry once -> template fallback.

Reads:  moments.json, explanations.json, match.json, teams.py
Writes: personalized.json

Run:
  python personalize.py --stats   player stat strips only. No AI calls, free.
  python personalize.py           full run. Refuses to overwrite an existing personalized.json.
  python personalize.py --force   full run, replaces personalized.json.
"""

import json
import os
import re
import sys
import time

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from teams import TEAMS

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

ENDPOINT = "https://inside-the-game-resource1.services.ai.azure.com/api/projects/inside-the-game"
MODEL = "gpt-5-mini"

LANG = "tr"                            # extra language code
LANG_NAME = "Turkish"                  # extra language name (used in the Translator's instructions)
FOCUS_PLAYERS = ["H9", "H3", "A9"]     # Taherzadeh, Eren Nevzat, Simitci
PAUSE = 3                              # seconds between AI calls (student quota is small)
OUT = "personalized.json"

CLUB = {side: TEAMS[side]["name"] for side in ("home", "away")}

# Names the Translator must keep: every player's surname + both club names.
NAMES = [p["name"].split()[-1] for side in ("home", "away") for p in TEAMS[side]["players"].values()]
NAMES += list(CLUB.values())

CLIENT = None  # the Foundry client, created in main() only when AI calls are needed


# ---------------------------------------------------------------------------
# Agent instructions
# ---------------------------------------------------------------------------

PERSONA_INSTRUCTIONS = """You rewrite one key moment of a football match for two audiences. You receive the moment's evidence and an approved explanation written by another agent.

Rules:
- Use only facts in the JSON. Never invent players, tactics, injuries or events.
- Do not contradict the approved explanation.
- The statistics cover the five minutes BEFORE the moment. Use them only to explain the build-up. Never use the moment itself as evidence for itself.
- Only quote numbers that appear in the JSON. Do not calculate new numbers (no differences, totals or percentages).
- Compare like with like (completed passes against completed passes).
- pressure_events counts how often a side pressed the opponent while it did not have the ball. It is not attacking threat. Never say pressure was "converted" into a goal.
- Do not say a goal was "decisive", a "winner" or "crucial", and do not predict what happens next.
- For a goal or big_chance, name the player (use the "player" field) in BOTH versions.
- Only say the balance of the match shifted when the kind is swing.
- Use the club and player names given. Never say "home" or "away".
- Write in British English.

analyst: for a tactically literate viewer. Precise vocabulary (build-up, xG, pressing, completed passes). Quote two or three numbers from the evidence. At most 60 words.
casual: for a casual fan. A plain-English storyline with no jargon: never write "xG"; say "good chances" or "chance quality" instead. At most one number. At most 30 words.

Reply with JSON only, exactly in this form: {"analyst": "<text>", "casual": "<text>"}"""

PLAYER_INSTRUCTIONS = """You write a one-sentence "player to watch" note about one footballer, from their full-match statistics and the key moments they appeared in.

Rules:
- Use only facts in the JSON. Never invent players, tactics, injuries or events.
- Only quote numbers that appear in the JSON. Do not calculate new numbers. Quote at most two.
- pressures counts how often the player pressed an opponent while their team did not have the ball. It is not attacking threat.
- Do not say "decisive", "winner" or "crucial", and do not predict anything.
- Use the player's and club's names. Never say "home" or "away".
- Write in British English. One sentence, at most 25 words.

Reply with JSON only, exactly in this form: {"watch": "<one sentence>"}"""

TRANSLATOR_INSTRUCTIONS = f"""You translate short football texts from English into {LANG_NAME} for a match-overlay app.

Rules:
- Translate the meaning faithfully. Do not add or remove any fact.
- Keep every number exactly as written, with the same digits and a decimal point (0.15, never 0,15).
- Keep player and club names exactly as written. Suffixes after an apostrophe are fine (for example Taherzadeh'in).
- Use natural, modern {LANG_NAME} football language.
- Reply with JSON only, using exactly the same keys you were given."""


# ---------------------------------------------------------------------------
# Loading data
# ---------------------------------------------------------------------------

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def as_list(data, key):
    """Accept either a plain list or a dict that holds the list under `key`."""
    return data[key] if isinstance(data, dict) else data


def event_type(ev):
    return ev.get("type") or ev.get("event_type")


def with_club_names(obj):
    """Replace every "home"/"away" key or value with the club's name, all the way down."""
    if isinstance(obj, dict):
        return {CLUB.get(k, k): with_club_names(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [with_club_names(v) for v in obj]
    if isinstance(obj, str):
        return CLUB.get(obj, obj)
    return obj


# ---------------------------------------------------------------------------
# Player stat strip (pure Python, from match.json)
# ---------------------------------------------------------------------------

def player_stats(events, pid):
    s = {"passes": 0, "completed": 0, "shots": 0, "on_target": 0,
         "xg": 0.0, "goals": 0, "tackles_won": 0, "pressures": 0}
    for ev in events:
        if ev.get("player_id") != pid:
            continue
        t = event_type(ev)
        if t == "pass":
            s["passes"] += 1
            if ev.get("completed"):
                s["completed"] += 1
        elif t == "shot":
            s["shots"] += 1
            if ev.get("on_target"):
                s["on_target"] += 1
            s["xg"] += ev.get("xg") or 0
        elif t == "goal":
            s["goals"] += 1
        elif t == "tackle" and ev.get("won"):
            s["tackles_won"] += 1
        elif t == "pressure":
            s["pressures"] += 1
    s["xg"] = round(s["xg"], 2)
    s["pass_completion_pct"] = round(100 * s["completed"] / s["passes"]) if s["passes"] else 0
    return s


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------

NUM = re.compile(r"\d+(?:[.,]\d+)?")
BANNED = re.compile(r"\b(decisive|winner|winning goal|crucial|converted|home|away)\b", re.IGNORECASE)


def numbers_in(text):
    return [float(n.replace(",", ".")) for n in NUM.findall(text)]


def numbers_from(obj):
    """Every number inside a data structure, including numbers inside strings like "2-1"."""
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        return numbers_in(obj)
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in numbers_from(v)]
    if isinstance(obj, list):
        return [n for v in obj for n in numbers_from(v)]
    return []


def unsupported_numbers(text, allowed):
    # 0.011 tolerance lets 0.1523 in the data appear as 0.15 in the text.
    return [n for n in numbers_in(text) if not any(abs(n - a) <= 0.011 for a in allowed)]


def check_text(key, text, limit, allowed, must_name=None):
    if not isinstance(text, str) or not text.strip():
        return [f"{key}: missing"]
    problems = []
    words = len(text.split())
    if words > limit:
        problems.append(f"{key}: {words} words (limit {limit})")
    bad = unsupported_numbers(text, allowed)
    if bad:
        problems.append(f"{key}: numbers not in evidence {bad}")
    banned = BANNED.search(text)
    if banned:
        problems.append(f"{key}: banned word '{banned.group(0)}'")
    if must_name and must_name not in text:
        problems.append(f"{key}: does not name {must_name}")
    return problems


def check_personas(result, mo, allowed):
    surname = None
    if mo["kind"] in ("goal", "big_chance") and mo.get("player"):
        surname = mo["player"].split()[-1]
    problems = check_text("analyst", result.get("analyst"), 60, allowed, surname)
    problems += check_text("casual", result.get("casual"), 30, allowed, surname)
    if "xg" in str(result.get("casual", "")).lower():
        problems.append("casual: uses jargon 'xG'")
    return problems


def check_watch(result, player_name, allowed):
    return check_text("watch", result.get("watch"), 30, allowed, player_name.split()[-1])


def check_translation(source, result):
    problems = []
    for key, text in source.items():
        tr = result.get(key)
        if not isinstance(tr, str) or not tr.strip():
            problems.append(f"{key}: missing")
            continue
        if set(numbers_in(tr)) != set(numbers_in(text)):
            problems.append(f"{key}: numbers changed {numbers_in(text)} -> {numbers_in(tr)}")
        for name in NAMES:
            if name in text and name not in tr:
                problems.append(f"{key}: lost name {name}")
    return problems


# ---------------------------------------------------------------------------
# Calling the model: ask once, then generate = ask + check + retry
# ---------------------------------------------------------------------------

def ask(instructions, payload):
    response = CLIENT.responses.create(
        model=MODEL,
        instructions=instructions,
        input=json.dumps(payload, ensure_ascii=False),
    )
    time.sleep(PAUSE)
    text = response.output_text
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def generate(label, instructions, payload, check):
    """Two attempts. Returns the model's dict if it passes the Checker, else None."""
    for attempt in (1, 2):
        try:
            result = ask(instructions, payload)
            problems = check(result)
        except Exception as e:
            problems = [f"call or parse failed: {e}"]
        if not problems:
            print(f"  {label}: ai (attempt {attempt})")
            return result
        print(f"  {label}: attempt {attempt} rejected -> {problems}")
        time.sleep(PAUSE)
    print(f"  {label}: FALLBACK")
    return None


# ---------------------------------------------------------------------------
# Template fallbacks (used only when the AI fails twice)
# ---------------------------------------------------------------------------

def persona_fallback(card):
    first_sentence = card["explanation"].split(". ")[0].rstrip(".") + "."
    return {"analyst": card["explanation"], "casual": first_sentence}


def player_fallback(p):
    s = p["stats"]
    return (f"{p['name']} ({p['club']}): {s['completed']} of {s['passes']} passes completed, "
            f"{s['shots']} shots, {s['goals']} goals.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global CLIENT

    events = as_list(load("match.json"), "events")
    moments = as_list(load("moments.json"), "moments")
    cards = {c["moment_id"]: c for c in as_list(load("explanations.json"), "explanations")}

    players = {}
    for pid in FOCUS_PLAYERS:
        side = "home" if pid.startswith("H") else "away"
        info = TEAMS[side]["players"][pid]
        players[pid] = {"name": info["name"], "club": CLUB[side], "position": info["position"],
                        "stats": player_stats(events, pid)}

    if "--stats" in sys.argv:
        print("Event types in match.json:", sorted({str(event_type(e)) for e in events}))
        for pid, p in players.items():
            print(pid, p["name"], "|", p["club"], "|", p["stats"])
        return

    if os.path.exists(OUT) and "--force" not in sys.argv:
        print(f"{OUT} already exists (locked snapshot). Run with --force to replace it.")
        return

    project = AIProjectClient(endpoint=ENDPOINT, credential=DefaultAzureCredential())
    CLIENT = project.get_openai_client()

    # --- Moments: Personalizer then Translator --------------------------------
    out_moments = []
    for mo in moments:
        card = cards[mo["id"]]
        print(f"Moment {mo['minute']}' {mo['kind']}")

        evidence = {k: v for k, v in mo.items() if k not in ("change", "id")}
        payload = {"moment": with_club_names(evidence),
                   "approved_explanation": {"headline": card["headline"],
                                            "explanation": card["explanation"]}}
        allowed = numbers_from(evidence) + [5.0]  # 5 = "five minutes" written as a digit

        result = generate("personas", PERSONA_INSTRUCTIONS, payload,
                          lambda r: check_personas(r, mo, allowed))
        texts = result if result else persona_fallback(card)
        en = {"headline": card["headline"], "analyst": texts["analyst"], "casual": texts["casual"]}

        tr = generate("translation", TRANSLATOR_INSTRUCTIONS, en,
                      lambda r: check_translation(en, r))

        out_moments.append({
            "moment_id": mo["id"],
            "minute": mo["minute"],
            "second": mo.get("second", 0),
            "kind": mo["kind"],
            "team": CLUB.get(mo.get("team"), mo.get("team")),
            "player_id": mo.get("player_id"),
            "en": en,
            LANG: tr if tr else en,
            "source": {"personas": "ai" if result else "fallback",
                       "translation": "ai" if tr else "fallback"},
        })

    # --- Focus players: watch note then Translator ---------------------------
    for pid, p in players.items():
        print(f"Player {p['name']}")
        involved = [m for m in out_moments if m["player_id"] == pid]
        p["moment_ids"] = [m["moment_id"] for m in involved]

        payload = {"player": p["name"], "club": p["club"], "position": p["position"],
                   "stats": p["stats"],
                   "key_moments": [{"minute": m["minute"], "kind": m["kind"],
                                    "headline": m["en"]["headline"]} for m in involved]}
        allowed = numbers_from(payload)

        result = generate("watch note", PLAYER_INSTRUCTIONS, payload,
                          lambda r: check_watch(r, p["name"], allowed))
        en = {"watch": result["watch"] if result else player_fallback(p)}

        tr = generate("translation", TRANSLATOR_INSTRUCTIONS, en,
                      lambda r: check_translation(en, r))

        p["en"] = en
        p[LANG] = tr if tr else en
        p["source"] = {"watch": "ai" if result else "fallback",
                       "translation": "ai" if tr else "fallback"}

    # --- Save -----------------------------------------------------------------
    output = {"languages": {"en": "English", LANG: LANG_NAME},
              "focus_players": FOCUS_PLAYERS,
              "moments": out_moments,
              "players": players}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    sources = [v for m in out_moments for v in m["source"].values()]
    sources += [v for p in players.values() for v in p["source"].values()]
    print(f"\nSaved {OUT}: {sources.count('ai')} ai, {sources.count('fallback')} fallback")


if __name__ == "__main__":
    main()
