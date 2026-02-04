"""
Locator module for finding design DBs
"""

from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime


class LocatorResult:
    """Result from locator"""

    def __init__(
        self,
        enc_path: Optional[Path] = None,
        enc_dat_path: Optional[Path] = None,
        candidates: Optional[List[dict]] = None,
        selection_reason: str = "",
    ):
        self.enc_path = enc_path
        self.enc_dat_path = enc_dat_path
        self.candidates = candidates
        self.selection_reason = selection_reason

    def is_success(self) -> bool:
        """Check if locator found a unique DB"""
        return self.enc_path is not None and self.enc_dat_path is not None

    def needs_selection(self) -> bool:
        """Check if user needs to select from candidates"""
        return bool(self.candidates and len(self.candidates) > 1)


class Locator:
    """Design DB locator"""

    def __init__(self, cwd: Path, scan_depth: int = 3):
        self.cwd = cwd
        self.scan_depth = scan_depth

    def locate(self, query: str) -> LocatorResult:
        """
        Locate design DB based on query
        
        Args:
            query: Design name or explicit path
            
        Returns:
            LocatorResult with either selected DB or candidates
        """
        # Check if explicit path
        if self._is_explicit_path(query):
            return self._locate_explicit(query)
        
        # Otherwise scan cwd
        return self._locate_scan(query)

    def _is_explicit_path(self, query: str) -> bool:
        """Check if query is an explicit path"""
        return (
            "/" in query or
            "\\" in query or
            query.endswith(".enc") or
            query.startswith("./") or
            query.startswith(".\\")
        )

    def _locate_explicit(self, query: str) -> LocatorResult:
        """Locate using explicit path"""
        query_path = Path(query)
        
        # Resolve to absolute path
        enc_path = (self.cwd / query_path).resolve() if not query_path.is_absolute() else query_path.resolve()
        
        # Check if enc exists
        if not enc_path.exists():
            return LocatorResult(
                selection_reason="explicit_path_not_found",
            )
        
        # Find enc.dat
        enc_dat_path = self._find_enc_dat(enc_path)
        if not enc_dat_path or not enc_dat_path.exists():
            return LocatorResult(
                selection_reason="enc_dat_missing",
            )
        
        return LocatorResult(
            enc_path=enc_path,
            enc_dat_path=enc_dat_path,
            selection_reason="direct_match",
        )

    def _locate_scan(self, query: str) -> LocatorResult:
        """Scan cwd for matching enc files"""
        candidates = []
        
        # Scan for *.enc files
        for enc_path in self.cwd.rglob("*.enc"):
            # Check depth
            try:
                rel_path = enc_path.relative_to(self.cwd)
                depth = len(rel_path.parts) - 1
                if depth > self.scan_depth:
                    continue
            except ValueError:
                continue
            
            # Check if name matches query
            if enc_path.stem == query or query == "":
                # Find enc.dat
                enc_dat_path = self._find_enc_dat(enc_path)
                if enc_dat_path and enc_dat_path.exists():
                    stat = enc_path.stat()
                    candidates.append({
                        "path": str(enc_path),
                        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "size": stat.st_size,
                    })
        
        if len(candidates) == 0:
            return LocatorResult(
                selection_reason="no_candidates",
            )
        elif len(candidates) == 1:
            enc_path = Path(candidates[0]["path"])
            enc_dat_path = self._find_enc_dat(enc_path)
            return LocatorResult(
                enc_path=enc_path,
                enc_dat_path=enc_dat_path,
                candidates=candidates,
                selection_reason="unique_scan_result",
            )
        else:
            return LocatorResult(
                candidates=candidates,
                selection_reason="multiple_candidates",
            )

    def _find_enc_dat(self, enc_path: Path) -> Optional[Path]:
        """Find enc.dat file"""
        # Standard naming: <enc_path>.dat
        enc_dat_path = Path(str(enc_path) + ".dat")
        if enc_dat_path.exists():
            return enc_dat_path
        
        # Alternative: <name>.enc.dat
        enc_dat_path = enc_path.parent / f"{enc_path.stem}.enc.dat"
        if enc_dat_path.exists():
            return enc_dat_path
        
        return None
