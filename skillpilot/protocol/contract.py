"""
Contract protocol implementation
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
from .schema import SCHEMA_VERSION


class Contract:
    """Subskill contract - defines inputs, outputs, and validation rules"""

    def __init__(
        self,
        name: str,
        version: str,
        tool: str = "innovus",
        description: str = "",
    ):
        self.schema_version = SCHEMA_VERSION
        self.name = name
        self.version = version
        self.tool = tool
        self.description = description
        self.scripts: List[Dict[str, str]] = []
        self.outputs: Dict[str, Any] = {"required": []}
        self.debug_hints: List[str] = []

    def add_script(self, name: str, entry: str) -> None:
        """Add script definition"""
        self.scripts.append({"name": name, "entry": entry})

    def add_required_output(self, path: str, non_empty: bool = True, description: str = "") -> None:
        """Add required output"""
        output = {"path": path, "non_empty": non_empty}
        if description:
            output["description"] = description
        self.outputs["required"].append(output)

    def add_debug_hint(self, hint: str) -> None:
        """Add debug hint"""
        self.debug_hints.append(hint)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "version": self.version,
            "tool": self.tool,
            "description": self.description,
            "scripts": self.scripts,
            "outputs": self.outputs,
            "debug_hints": self.debug_hints,
        }

    @staticmethod
    def load(path: Path) -> "Contract":
        """Load contract from YAML file"""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        
        contract = Contract(
            name=data["name"],
            version=data["version"],
            tool=data.get("tool", "innovus"),
            description=data.get("description", ""),
        )
        
        for script in data.get("scripts", []):
            contract.add_script(script["name"], script["entry"])
        
        for output in data.get("outputs", {}).get("required", []):
            contract.add_required_output(
                path=output["path"],
                non_empty=output.get("non_empty", True),
                description=output.get("description", ""),
            )
        
        contract.debug_hints = data.get("debug_hints", [])
        
        return contract

    def validate(self) -> tuple[bool, str]:
        """Validate contract"""
        if not self.outputs["required"]:
            return False, "No required outputs specified"
        
        for output in self.outputs["required"]:
            path = output["path"]
            
            # Check if path starts with reports/
            if not path.startswith("reports/"):
                return False, f"Output path must start with 'reports/': {path}"
            
            # Check for path traversal
            if ".." in path:
                return False, f"Output path must not contain '..': {path}"
            
            # Check if path is absolute
            if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
                return False, f"Output path must be relative: {path}"
        
        if len(self.debug_hints) < 2:
            return False, "At least 2 debug hints required"
        
        return True, ""

    def get_required_outputs(self) -> List[Dict[str, Any]]:
        """Get required outputs"""
        return self.outputs["required"]
