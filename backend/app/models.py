"""Strict input contracts and allow-listed public/admin output models."""

from datetime import date as calendar_date
from typing import Annotated, Self
from uuid import UUID

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
    dress_code="Elegante Sport",
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


class ContactData(ApiModel):
    whatsapp_number: Annotated[StrictStr, Field(pattern=r"^(?:[1-9][0-9]{7,14})?$")]


class BankTransferData(ApiModel):
    holder: Annotated[StrictStr, Field(min_length=1, max_length=120)]
    bank: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    alias: Annotated[StrictStr, Field(max_length=100)] = ""
    account_number: Annotated[StrictStr, Field(pattern=r"^(?:[0-9]{22})?$")] = ""
    illustrative: StrictBool

    @model_validator(mode="after")
    def requires_destination(self) -> Self:
        if not self.alias and not self.account_number:
            raise ValueError("An alias or accountNumber is required.")
        return self


class SectionsData(ApiModel):
    event_utc_offset: Annotated[StrictStr, Field(pattern=r"^-03:00$")]
    contact: ContactData
    bank_transfer: BankTransferData | None


DEFAULT_SECTIONS = SectionsData(
    event_utc_offset="-03:00",
    contact=ContactData(whatsapp_number="5491141675124"),
    bank_transfer=BankTransferData(
        holder="Mia · XV años", bank="Banco ilustrativo", alias="ALIAS A CONFIRMAR",
        account_number="0000000000000000000000", illustrative=True,
    ),
)


class WishInput(ApiModel):
    author: Annotated[StrictStr, Field(min_length=1, max_length=80)]
    message: Annotated[StrictStr, Field(min_length=1, max_length=600)]
    client_request_id: Annotated[StrictStr, Field(min_length=36, max_length=36)]

    @field_validator("author", "message")
    @classmethod
    def disallow_null_character(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Null characters are not allowed.")
        return value

    @field_validator("client_request_id")
    @classmethod
    def canonical_request_id(cls, value: str) -> str:
        return str(UUID(value))


class WishData(ApiModel):
    id: str
    author: str
    message: str
    created_at: str
    updated_at: str


class AdminWish(WishData):
    invitation_id: str
    family_name: str


class AdminSummary(ApiModel):
    total_invitations: int
    active_invitations: int
    confirmed_invitations: int
    declined_invitations: int
    pending_invitations: int
    confirmed_guests: int
    reserved_seats: int
    total_wishes: int


class InvitationResponse(ApiModel):
    event: EventData
    invitation: InvitationData
    rsvp: RsvpData | None
    sections: SectionsData
    wish: WishData | None


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
