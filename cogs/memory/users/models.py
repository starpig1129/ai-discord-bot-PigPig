"""UserInfo model for user data."""
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, Optional


@dataclass
class UserInfo:
    """User info dataclass."""
    user_id: str
    display_name: str = ""
    user_data: Optional[str] = None
    last_active: Optional[datetime] = None
    profile_data: Optional[Dict] = None
    preferences: Optional[Dict] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, serializing datetimes."""
        data = asdict(self)
        if self.last_active:
            data["last_active"] = self.last_active.isoformat()
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserInfo":
        """Instantiate from dict, parsing datetimes."""
        if data.get("last_active"):
            try:
                data["last_active"] = datetime.fromisoformat(data["last_active"])
            except (ValueError, TypeError):
                data["last_active"] = None

        if data.get("created_at"):
            try:
                data["created_at"] = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                data["created_at"] = None

        return cls(**data)