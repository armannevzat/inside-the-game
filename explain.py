import json
import time

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from teams import TEAMS

ENDPOINT = "https://inside-the-game-resource1.services.ai.azure.com/api/projects/inside-the-game"
MODEL = "gpt-5-mini"

INSTRUCTIONS = """You are the Explainer, one agent in a football broadcast analysis system.
You receive one key moment from a match as JSON, with statistics from the five minutes leading up to it.
Explain WHY the moment mattered, not just what happened.

Kinds of moment:
- goal: a goal was scored.
- big_chance: a high-quality shot (high xg means a very good chance).
- swing: control of the match shifted towards the named team; momentum_change is how far.

Rules:
- Use only facts in the JSON. Never invent players, tactics, injuries or events.
- Start with what the moment changed: the score, the lead, or the balance of the match.
- For a goal or big_chance, name the player (use the "player" field) in the headline or the explanation.
- Only say the balance of the match shifted when the kind is swing. For a goal or big_chance, describe the build-up without claiming a shift.
- The statistics cover the five minutes BEFORE the moment. Use them only to explain the build-up. Never use the moment itself as evidence for itself.
- Quote one to three numbers, and only where the two sides clearly differ. If the sides were level, say the build-up was even instead of quoting numbers.
- Compare like with like (completed passes against completed passes).
- pressure_events counts how often a side pressed the opponent while it did not have the ball. It is not attacking threat. Never say pressure was "converted" into a goal.
- Do not say a goal was "decisive", a "winner" or "crucial", and do not predict what happens next.
- momentum_change is an internal score. Do not quote it; say that momentum shifted towards the named team.
- Use the club and player names given. Never say "home" or "away".
- Write in British English.
- The explanation must be two sentences and under 45 words in total.
- Reply with JSON only, exactly in this form: {"headline": "<at most 8 words>", "explanation": "<two sentences>"}
"""

project = AIProjectClient(endpoint=ENDPOINT, credential=DefaultAzureCredential())
client = project.get_openai_client()


def build_payload(mo):
    club = {t: TEAMS[t]["name"] for t in ("home", "away")}
    payload = {
        "kind": mo["kind"],
        "minute": mo["minute"],
        "team": club[mo["team"]],
        "player": mo.get("player"),
        "score_after": {club[t]: mo["score_after"][t] for t in club},
        "xg": mo.get("xg"),
        "momentum_change": mo.get("change"),
        "last_five_minutes": {club[t]: mo["window"][t] for t in club},
    }
    if "score_before" in mo:
        payload["score_before"] = {club[t]: mo["score_before"][t] for t in club}
    return payload


def fallback(mo):
    club = TEAMS[mo["team"]]["name"]
    if mo["kind"] == "goal":
        return {"headline": f"Goal for {club}",
                "explanation": f"{mo.get('player')} scored for {club} in minute {mo['minute']}.",
                "source": "fallback"}
    if mo["kind"] == "big_chance":
        return {"headline": f"Big chance for {club}",
                "explanation": f"{mo.get('player')} had a high-quality chance in minute {mo['minute']}.",
                "source": "fallback"}
    return {"headline": f"{club} take control",
            "explanation": f"Momentum shifted towards {club} around minute {mo['minute']}.",
            "source": "fallback"}


def explain(mo):
    payload = build_payload(mo)
    for attempt in range(2):
        try:
            response = client.responses.create(
                model=MODEL,
                instructions=INSTRUCTIONS,
                input=json.dumps(payload),
            )
            text = response.output_text
            data = json.loads(text[text.index("{"): text.rindex("}") + 1])
            return {"headline": data["headline"],
                    "explanation": data["explanation"],
                    "source": "ai"}
        except Exception as err:
            print("  attempt", attempt + 1, "failed for moment", mo["id"], "-", err)
            time.sleep(2)
    return fallback(mo)


with open("moments.json") as f:
    moments = json.load(f)

results = []
for mo in moments:
    result = explain(mo)
    result["moment_id"] = mo["id"]
    result["minute"] = mo["minute"]
    result["kind"] = mo["kind"]
    results.append(result)
    print(f"[{mo['minute']}'] {result['headline']} ({result['source']})")
    print("   ", result["explanation"])

with open("explanations.json", "w") as f:
    json.dump(results, f, indent=2)
print("Saved", len(results), "explanations to explanations.json")