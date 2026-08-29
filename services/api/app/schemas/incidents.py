from pydantic import BaseModel, Field

from app.domain.money import MinorUnits


class EntitlementPosition(BaseModel):
    """Current money state for one incident. remaining is derived, never stored as a float."""

    incident_id: str = Field(min_length=1)
    allowed_entitlement_minor: MinorUnits
    settled_entitlement_minor: MinorUnits
    reserved_entitlement_minor: MinorUnits

    def remaining_minor(self) -> int:
        return (
            self.allowed_entitlement_minor
            - self.settled_entitlement_minor
            - self.reserved_entitlement_minor
        )
