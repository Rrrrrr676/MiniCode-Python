"""Compatibility facade for minicode.integrations.skills."""

import sys as _sys
from minicode.integrations import skills as _implementation

_implementation.__all__ = ["LoadedSkill","SkillSummary","discover_skills","extract_description","install_skill","load_skill","remove_managed_skill"]
_sys.modules[__name__] = _implementation

from minicode.integrations.skills import (
    LoadedSkill,
    SkillSummary,
    discover_skills,
    extract_description,
    install_skill,
    load_skill,
    remove_managed_skill,
)

__all__ = [
    "LoadedSkill",
    "SkillSummary",
    "discover_skills",
    "extract_description",
    "install_skill",
    "load_skill",
    "remove_managed_skill",
]
