"""Strict input contracts and allow-listed public/admin output models."""

from datetime import date as calendar_date
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


ShortName = Annotated[StrictStr, Field(min_length=1, max_length=120)]
Seats = Annotated[StrictInt, Field(ge=1, le=50)]
TimeOfDay = Annotated[StrictStr, Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]


class EventData(ApiModel):
    name: Annotated[StrictStr, Field(min_length=1, max_length=80)]
    date: Annotated[StrictStr, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    arrival_time: TimeOfDay
    entrance_time: TimeOfDay
    venue_name: Annotated[StrictStr, Field(min_length=1, max_length=160)]
    venue_address: Annotated[StrictStr, Field(min_length=1, max_length=300)]
    dress_code: Annotated[StrictStr, Field(min_length=1, max_length=100)]

    @field_validator("date")
    @classmethod
    def date_must_exist(cls, value: str) -> str:
        calendar_date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def entrance_cannot_precede_arrival(self) -> Self:
        if self.entrance_time < self.arrival_time:
            raise ValueError("entranceTime cannot precede arrivalTime on the event date.")
        return self


DEFAULT_EVENT = EventData(
    name="Mia",
    date="2026-12-26",
    arrival_time="20:30",
    entrance_time="21:30",
    venue_name="Jardín Secreto",
    venue_address="Teodoro Fels 7423, Trujui",
    dress_code="Elegante sport",
)


class InvitationCreate(ApiModel):
    family_name: ShortName
    seats: Seats


class InvitationPatch(ApiModel):
    family_name: ShortName | None = None
    seats: Seats | None = None
    active: StrictBool | None = None

    @model_validator(mode="after")
    def requires_non_null_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one change is required.")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Changes cannot be null.")
        return self


class RsvpInput(ApiModel):
    attending: StrictBool
    guest_count: Annotated[StrictInt, Field(ge=0, le=50)]

    @model_validator(mode="after")
    def count_must_match_answer(self) -> Self:
        if self.attending and self.guest_count == 0:
            raise ValueError("Attending requires at least one guest.")
        if not self.attending and self.guest_count != 0:
            raise ValueError("A declined invitation must have zero guests.")
        return self


class RsvpData(RsvpInput):
    updated_at: str


class InvitationData(ApiModel):
    id: str
    family_name: str
    seats: int


class InvitationResponse(ApiModel):
    event: EventData
    invitation: InvitationData
    rsvp: RsvpData | None


class AdminInvitation(InvitationData):
    active: bool
    created_at: str
    updated_at: str
    rsvp: RsvpData | None


class CreatedInvitation(AdminInvitation):
    token: str
    invitation_path: str


class RotatedToken(ApiModel):
    id: str
    token: str
    invitation_path: str


class HealthResponse(ApiModel):
    status: str
