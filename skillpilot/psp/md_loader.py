"""
Markdown PSP Loader

Parses Markdown-formatted Playbook and Skill files into Python data structures.
Simple format: no complex frontmatter, just clear headings and lists.
"""

import os
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from skillpilot.psp.schema import Playbook, Skill, PlaybookDefaults, SkillStep


def parse_markdown_file(filepath: str) -> Dict[str, Any]:
    """
    Parse a Markdown file into structured data.

    Format:
    # Skill Name

    **Inputs:**
    - param1: value
    - param2: value

    **Steps:**
    1. Step Name
       - Action: poke::action_name
       - Args: -arg1 value1, -arg2 value2
       - Timeout: 30s

    Args:
        parse_markdown_file(filepath)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    result = {
        "name": None,
        "inputs_schema": None,
        "steps": [],
        "skills": [],
        "defaults": {},
    }

    # Extract name (first heading)
    name_match = re.search(r"^#\s+(.+?)\s*$", content, re.MULTILINE)
    if name_match:
        result["name"] = name_match.group(1).strip()

    # Extract inputs section
    inputs_section = re.search(
        r"\*\*Inputs:\*\*\s*(.+?)(?=\*\*[A-Z]|\Z)",
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if inputs_section:
        inputs_text = inputs_section.group(1).strip()
        result["inputs_schema"] = parse_inputs_section(inputs_text)

    # Extract steps section
    steps_section = re.search(
        r"\*\*Steps:\*\*\s*(.+?)(?=\*\*[A-Z]|\Z)",
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if steps_section:
        steps_text = steps_section.group(1).strip()
        result["steps"] = parse_steps_section(steps_text)

    # Extract skills section (for playbooks)
    skills_section = re.search(
        r"\*\*Skills:\*\*\s*(.+?)(?=\*\*[A-Z]|\Z)",
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if skills_section:
        skills_text = skills_section.group(1).strip()
        result["skills"] = parse_skills_section(skills_text)

    # Extract defaults section (for playbooks)
    defaults_section = re.search(
        r"\*\*Defaults:\*\*\s*(.+?)(?=\*\*[A-Z]|\Z)",
        content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    if defaults_section:
        defaults_text = defaults_section.group(1).strip()
        result["defaults"] = parse_defaults_section(defaults_text)

    return result


def parse_inputs_section(text: str) -> Dict[str, Any]:
    """
    Parse inputs section text into schema.

    Format:
    - param1: value
    - param2: value
    """
    inputs = {}

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    for line in lines:
        if line.startswith("- "):
            # Format: - param: value or -param value
            line = line[1:].strip()  # Remove leading "- "
            parts = re.split(r"\s*:\s*|\s+", line, maxsplit=1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                # Remove colon if present
                value = value.rstrip(":").strip()
                inputs[key] = value

    return inputs


def parse_steps_section(text: str) -> List[SkillStep]:
    """
    Parse steps section text into SkillStep objects.

    Format:
    1. Step Name
       - Action: poke::action_name
       - Args: -arg1 value1, -arg2 value2
       - Timeout: 30s

    OR:

    Steps:
    1. Step Name: Action poke::action_name Args: -arg1 value
    2. Another Step: Action poke::action2 Args: ...
    """
    steps = []

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if line starts with a number + period (1., 2., etc)
        step_header_match = re.match(r"^(\d+)\.\s+(.+)", line)
        if step_header_match:
            step_num = step_header_match.group(1)
            rest_of_header = step_header_match.group(2).strip()

            # Collect step content until next numbered item
            i += 1
            step_content_lines = []
            while i < len(lines):
                next_line = lines[i].strip()
                # Check if next step starts
                if re.match(r"^\d+\.", next_line) or next_line.startswith("Steps:") or next_line.startswith("**"):
                    break
                step_content_lines.append(next_line)
                i += 1

            step_content = "\n".join(step_content_lines)
            steps.append(parse_step_content(rest_of_header, step_content))
            continue

        # Check if line starts with "Steps:" header
        if line.lower().startswith("steps:"):
            i += 1
            # Collect all non-empty lines until next major section
            step_content_lines = []
            while i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith("#") or next_line.startswith("**"):
                    break
                if next_line and not next_line.startswith("-") and not next_line.startswith("•"):
                    step_content_lines.append(next_line)
                i += 1

            for content_line in step_content_lines:
                # Check for numbered list items
                num_match = re.match(r"^(\d+)\.\s+(.+)", content_line)
                if num_match:
                    content = num_match.group(1).strip()
                    # Parse inline format: "Step Name: Action..."
                    inline_match = re.match(r"(.+?):\s*Action\s+(.+)", content)
                    if inline_match:
                        step_name = inline_match.group(1).strip()
                        action_args = inline_match.group(2).strip()
                        steps.append(parse_step_content(step_name, action_args))
                    else:
                        # Simple numbered item - use entire content
                        steps.append(parse_step_content(content, None))
            continue

        i += 1

    return steps


def parse_step_content(step_name: str, content: Optional[str]) -> SkillStep:
    step = SkillStep(step_name, "", args={}, timeout_s=None)

    if not content:
        return step

    # Extract Action
    action_match = re.search(r"Action:\s*([^\n]+?)(?=\s*$|\n|Timeout:|$)", content, re.IGNORECASE)
    if action_match:
        step.action = action_match.group(1).strip()
        content = content[action_match.end():]
    else:
        # Look for "Action poke::..." pattern
        poke_action_match = re.search(r"Action\s+poke::([^\s\n]+)", content)
        if poke_action_match:
            step.action = f"poke::{poke_action_match.group(1)}"
            content = content[poke_action_match.end():]
        else:
            # Use step name as default action
            step.action = step_name

    # Extract Args
    args_match = re.search(r"Args?:\s*([^\n]+?)(?=\s*$|\n|Timeout:|$)", content, re.IGNORECASE)
    if args_match:
        args_text = args_match.group(1).strip()
        step.args = parse_step_args(args_text)
        content = content[args_match.end():]
    else:
        # Try extracting individual arg lines
        for arg_line in content.split("\n"):
            arg_line = arg_line.strip()
            if arg_line.startswith("- ") or arg_line.startswith("-"):
                key, value = parse_arg_line(arg_line)
                if key and value:
                    step.args[key] = value

    # Extract Timeout
    timeout_match = re.search(r"Timeout:\s*(\d+)s?", content, re.IGNORECASE)
    if timeout_match:
        step.timeout_s = int(timeout_match.group(1))

    return step


def parse_step_args(text: str) -> Dict[str, Any]:
    """
    Parse step arguments from text.

    Format: -arg1 value1, -arg2 value2
    """
    args = {}

    # Split by dash followed by a word character
    parts = re.split(r"-([a-zA-Z_][a-zA-Z0-9_]*)", text)

    i = 1
    while i < len(parts):
        key = parts[i]
        value_part = parts[i + 1] if i + 1 < len(parts) else ""

        tokens = value_part.split()
        if len(tokens) >= 1:
            value = tokens[0].strip('"\'')
            args[key] = value

        i += 2

    return args


def parse_arg_line(line: str) -> tuple:
    """
    Parse a single argument line.

    Format: -arg value or -arg: value
    """
    line = line.strip()

    if not line.startswith("- "):
        return None, None

    line = line[1:].strip()  # Remove leading "- "

    if ":" in line:
        key, value = line.split(":", 1)
        return key.strip(), value.strip()
    else:
        tokens = line.split()
        if len(tokens) >= 2:
            return tokens[0], " ".join(tokens[1:])
        return None, None


def parse_skills_section(text: str) -> List[str]:
    """
    Parse skills section for playbooks.

    Format:
    - skill_name_1
    - skill_name_2
    """
    skills = []

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]

    for line in lines:
        if line.startswith("- ") or line.startswith("-"):
            skill_name = line[1:].strip()
            if skill_name:
                skills.append(skill_name)

    return skills


def parse_defaults_section(text: str) -> PlaybookDefaults:
    """
    Parse defaults section for playbooks.

    Format:
    - timeout_s: 60
    - cancel_policy: ctrl_c
    - fail_fast: true
    - session_mode: shared
    """
    defaults = PlaybookDefaults()

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]

    for line in lines:
        if line.startswith("- ") or line.startswith("-"):
            key_value = parse_arg_line(line)
            if key_value[0] and key_value[1]:
                key = key_value[0]
                value = key_value[1]

                if key == "timeout_s":
                    value = int(value)
                elif key == "fail_fast":
                    value = value.lower() in ["true", "1", "yes"]
                elif key == "session_mode":
                    value = value.strip().lower()

                setattr(defaults, key, value)

    return defaults


class PlaybookLoader:
    """Load Playbook definitions from Markdown files"""

    @staticmethod
    def load(playbook_path: str) -> Playbook:
        """
        Load Playbook from Markdown file.

        Args:
            playbook_path: Path to playbook file

        Returns:
            Playbook object
        """
        if not os.path.exists(playbook_path):
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        data = parse_markdown_file(playbook_path)

        skills_list = data.get("skills", [])
        # Skills in playbooks are strings (references to skill files)
        if isinstance(skills_list, list):
            skills = skills_list
        else:
            # Handle simple comma-separated format
            skills = [s.strip() for s in str(skills_list).split(",") if s.strip()]

        return Playbook(
            name=data.get("name", "unnamed"),
            skills=skills,
            defaults=data["defaults"],
        )


class SkillLoader:
    """Load Skill definitions from Markdown files"""

    @staticmethod
    def load(skill_path: str) -> Skill:
        """
        Load Skill from Markdown file.

        Args:
            skill_path: Path to skill file

        Returns:
            Skill object
        """
        if not os.path.exists(skill_path):
            raise FileNotFoundError(f"Skill not found: {skill_path}")

        data = parse_markdown_file(skill_path)

        return Skill(
            name=data.get("name", "unnamed"),
            inputs_schema=data.get("inputs_schema"),
            steps=data.get("steps", []),
        )

    @staticmethod
    def load_from_directory(skill_dir: str) -> Dict[str, Skill]:
        """
        Load all skills from a directory.

        Args:
            skill_dir: Directory containing skill files

        Returns:
            Dictionary mapping skill names to Skill objects
        """
        skills = {}
        for filename in os.listdir(skill_dir):
            filepath = os.path.join(skill_dir, filename)
            if os.path.isfile(filepath) and filename.endswith(".md"):
                try:
                    skill = SkillLoader.load(filepath)
                    # Use filename (without .md) as key, not skill name from heading
                    skill_key = filename[:-3]
                    skills[skill_key] = skill
                except Exception as e:
                    import sys
                    print(f"Warning: Failed to load skill {filename}: {e}", file=sys.stderr)
        return skills
