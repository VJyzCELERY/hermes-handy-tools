"""Skills package for OpenCode Python CLI."""

import os
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).parent


def get_skill_names() -> list:
    """Get all available skill names."""
    skills = []
    for item in SKILLS_DIR.iterdir():
        if item.is_file() and item.suffix == ".md":
            skills.append(item.stem)
    return sorted(skills)


def get_skill_content(name: str) -> Optional[str]:
    """Get skill content by name."""
    skill_file = SKILLS_DIR / f"{name}.md"
    if skill_file.exists():
        return skill_file.read_text()
    return None
