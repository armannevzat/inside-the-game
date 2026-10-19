# Project spec (v1: hybrid "Why Engine" + "Two Fans")

**One-liner:** A live match overlay that detects turning points in a synthetic football match, explains *why* each one mattered using the data behind it, and tells that story differently for an analyst and a casual fan, with an optional focus on one favourite player and a second language.

All clubs and players are fictional. No Premier League names or badges.

## What it does (in build order)

1. **Generate** a fake match: a seeded Python script produces a list of events (passes, shots, tackles, pressure, possession changes, goals). Same seed = same match, so demos are repeatable.
2. **Interpret**: plain Python (no AI) turns events into running stats and a **momentum score** per team over time (control vs chaos, pressure, rhythm). It flags **key moments** (goals, big shots, momentum swings).
3. **Explain**: for each key moment, an AI call (Microsoft Foundry) receives the moment plus the surrounding numbers and writes a short "why it mattered" card that cites the evidence.
4. **Personalize**: the same explanation is rewritten for a persona: **Analyst** (numbers, tactical terms) or **Casual** (plain-English story). Extra: **Player Focus** (highlights one chosen player) and one extra language.
5. **Render**: a simple web page with a momentum timeline, moment cards, and a persona/player/language selector.
6. **Recap** (stretch): end-of-match summary from the key moments.

## Roles (the honest "multi-agent" story)
Separate AI roles with separate instructions, passing work along in a fixed order:
- **Explainer**: moment + evidence -> why it mattered
- **Personalizer**: explanation -> persona / player / language version
- **Recap** (stretch)
Fallback: if an AI call fails, show a template-based explanation so the screen is never empty.

## Hosting and judging
- Backend in Python (FastAPI), small frontend, deployed on Azure (Container Apps or similar).
- **Replay mode:** pre-computed match plus cached AI outputs so judges can use it free and instantly. Live AI mode behind a toggle.
- Must stay live and free until 10 Nov.

## Submission checklist
- [ ] Public GitHub repo with README and architecture diagram
- [ ] Working public URL
- [ ] Demo video under 2 min, public link, no copyrighted music or trademarks
- [ ] Pitch: what it does, which Microsoft/Azure tech, what problem it solves
- [ ] Submit by Mon 26 Oct evening (buffer on 27th)

## Cut list (drop in this order if time runs short)
Recap -> second language -> Player Focus -> live AI mode (keep replay) -> extra persona.

## Decisions still open
- Languages besides English: ?
- Streaming method (simple polling is fine to start)
