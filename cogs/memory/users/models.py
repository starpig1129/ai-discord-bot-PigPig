"""UserInfo model for user data."""
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, Optional, List
 
 
@dataclass
class UserInfo:
    """Dataclass matching the new `users` schema.
 
    Fields:
      - discord_id: primary identifier (TEXT)
      - discord_name: current display name
      - display_names: historical display names (stored as JSON array)
      - procedural_memory: free-form procedural memory (string)
      - user_background: free-form background info (string)
      - created_at: creation timestamp
    """
    discord_id: str
    discord_name: str = ""
    display_names: List[str] = field(default_factory=list)
    procedural_memory: Optional[str] = None
    user_background: Optional[str] = None
    created_at: Optional[datetime] = None
 
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization; datetimes become ISO strings."""
        data = asdict(self)
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        return data
 
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserInfo":
        """Instantiate from dict, handling created_at and display_names formats."""
        # Normalize display_names to a list
        dn = data.get("display_names")
        if isinstance(dn, str):
            try:
                # might be JSON string
                import json
                dn_parsed = json.loads(dn)
                if isinstance(dn_parsed, list):
                    data["display_names"] = dn_parsed
                else:
                    data["display_names"] = [str(dn_parsed)]
            except Exception:
                # fallback to single-element list
                data["display_names"] = [dn]
        elif dn is None:
            data["display_names"] = []
 
        if data.get("created_at"):
            try:
                data["created_at"] = datetime.fromisoformat(data["created_at"])
            except Exception:
                try:
                    data["created_at"] = datetime.fromtimestamp(float(data["created_at"]))
                except Exception:
                    data["created_at"] = None
 
        return cls(**data)