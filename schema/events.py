"""Event schema for the synthetic match stream (draft v0).
 
All clubs/players are fictional. Coordinates are on a 105 x 68 m pitch,
x along the length (0 = own goal line of the home team), y across.
"""
from enum import Enum
from typing import Literal, Optional, Union
 
from pydantic import BaseModel, Field
 
 
class Team(str, Enum):
    HOME = "home"
    AWAY = "away"
 
 
class EventType(str, Enum):
    PASS = "pass"
    SHOT = "shot"
    TACKLE = "tackle"
    POSSESSION_CHANGE = "possession_change"
    PRESSURE = "pressure"
    FOUL = "foul"
    GOAL = "goal"
    SUBSTITUTION = "substitution"
    PERIOD = "period"  # kickoff, half-time, full-time
 
 
class Location(BaseModel):
    x: float = Field(ge=0, le=105)
    y: float = Field(ge=0, le=68)
 
 
class BaseEvent(BaseModel):
    match_id: str
    seq: int  # monotonically increasing per match
    minute: int
    second: int = Field(ge=0, lt=60)
    period: Literal[1, 2]
    team: Team
    player_id: Optional[str] = None
    location: Optional[Location] = None
 
 
class PassEvent(BaseEvent):
    type: Literal[EventType.PASS] = EventType.PASS
    recipient_id: Optional[str] = None
    end_location: Location
    distance_m: float
    completed: bool
    difficulty: float = Field(ge=0, le=1)  # 0 easy, 1 very hard
    ball_speed_kmh: Optional[float] = None
 
 
class ShotEvent(BaseEvent):
    type: Literal[EventType.SHOT] = EventType.SHOT
    on_target: bool
    shot_speed_kmh: float
    xg: float = Field(ge=0, le=1)
 
 
class TackleEvent(BaseEvent):
    type: Literal[EventType.TACKLE] = EventType.TACKLE
    won: bool
 
 
class PossessionChangeEvent(BaseEvent):
    type: Literal[EventType.POSSESSION_CHANGE] = EventType.POSSESSION_CHANGE
    reason: Literal["interception", "tackle", "out_of_play", "foul", "turnover"]
 
 
class PressureEvent(BaseEvent):
    type: Literal[EventType.PRESSURE] = EventType.PRESSURE
    intensity: float = Field(ge=0, le=1)
 
 
class GoalEvent(BaseEvent):
    type: Literal[EventType.GOAL] = EventType.GOAL
    assist_player_id: Optional[str] = None
 
 
class PeriodEvent(BaseEvent):
    type: Literal[EventType.PERIOD] = EventType.PERIOD
    phase: Literal["kickoff", "half_time", "second_half_start", "full_time"]
 
 
MatchEvent = Union[
    PassEvent, ShotEvent, TackleEvent, PossessionChangeEvent,
    PressureEvent, GoalEvent, PeriodEvent,
]
 
 
class MatchMeta(BaseModel):
    match_id: str
    home_club: str  # fictional
    away_club: str  # fictional
    seed: int
    players: dict[str, dict]  # player_id -> {name, team, position, shirt}
 
