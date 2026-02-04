"""
Contracts module for contract validation and output verification
"""

import glob
from pathlib import Path
from typing import Tuple, List, Dict, Any
from skillpilot.protocol.contract import Contract


class ContractValidator:
    """Validator for subskill contracts and outputs"""

    @staticmethod
    def validate_contract(contract: Contract) -> Tuple[bool, str]:
        """
        Validate contract
        
        Returns:
            (is_valid, error_message)
        """
        return contract.validate()

    @staticmethod
    def validate_outputs(contract: Contract, reports_dir: Path) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Validate outputs against contract
        
        Args:
            contract: Subskill contract
            reports_dir: Path to reports directory
            
        Returns:
            (is_valid, error_type, validation_results)
        """
        results = []
        required_outputs = contract.get_required_outputs()
        
        for output in required_outputs:
            pattern = output["path"]
            non_empty = output.get("non_empty", True)
            
            # Remove "reports/" prefix if present (pattern is relative to reports_dir)
            if pattern.startswith("reports/"):
                pattern = pattern[8:]  # len("reports/") = 8
            
            # Resolve glob pattern
            pattern_path = reports_dir / pattern
            matched_files = list(glob.glob(str(pattern_path)))
            
            if not matched_files:
                results.append({
                    "path": pattern,
                    "status": "MISSING",
                    "error": "No files matched pattern",
                })
                continue
            
            # Check non_empty
            if non_empty:
                all_non_empty = True
                all_sizes = []
                for file_path in matched_files:
                    try:
                        size = Path(file_path).stat().st_size
                        all_sizes.append((file_path, size))
                        if size == 0:
                            all_non_empty = False
                    except OSError:
                        all_sizes.append((file_path, 0))
                        all_non_empty = False
                
                if not all_non_empty:
                    results.append({
                        "path": pattern,
                        "status": "EMPTY",
                        "error": f"Some matched files are empty: {all_sizes}",
                    })
                    continue
                
                results.append({
                    "path": pattern,
                    "status": "OK",
                    "files": matched_files,
                })
            else:
                results.append({
                    "path": pattern,
                    "status": "OK",
                    "files": matched_files,
                })
        
        # Check if any validation failed
        for result in results:
            if result["status"] == "MISSING":
                return False, "OUTPUT_MISSING", results
            if result["status"] == "EMPTY":
                return False, "OUTPUT_EMPTY", results
        
        return True, "OK", results
