"""
PSP (Playbook/Skill/Poke) schema definitions
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class SkillStep:
    """Single step in a skill"""
    name: str
    action: str
    args: Dict[str, Any] = field(default_factory=dict)
    timeout_s: Optional[int] = None


@dataclass
class Skill:
    """Skill definition - contains steps that call poke actions"""
    name: str
    inputs_schema: Optional[Dict[str, Any]] = None
    steps: List[SkillStep] = field(default_factory=list)


@dataclass
class PlaybookDefaults:
    """Default values for playbook"""
    timeout_s: Optional[int] = None
    cancel_policy: str = "ctrl_c"
    fail_fast: bool = True
    session_mode: str = "shared"


@dataclass
class Playbook:
    """Playbook definition - orchestrates skills"""
    name: str
    skills: List[str]  # Skill names or references
    defaults: PlaybookDefaults = field(default_factory=PlaybookDefaults)
