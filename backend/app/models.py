from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Store UTC in SQLite and restore an explicit UTC offset when reading."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime values must include a timezone")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, _dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Patient(SQLModel, table=True):
    __tablename__ = "patients"

    id: int | None = Field(default=None, primary_key=True)
    demo_name: str = Field(index=True)

    prescriptions: list["Prescription"] = Relationship(back_populates="patient")
    verifications: list["Verification"] = Relationship(back_populates="patient")
    account: "Account" = Relationship(back_populates="patient")


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patients.id", unique=True, index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=utc_now, sa_type=UTCDateTime())

    patient: Patient = Relationship(back_populates="account")


class Prescription(SQLModel, table=True):
    __tablename__ = "prescriptions"

    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patients.id", index=True)
    status: str = Field(default="needs_review", index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=UTCDateTime())

    patient: Patient = Relationship(back_populates="prescriptions")
    items: list["PrescriptionItem"] = Relationship(back_populates="prescription")


class Medicine(SQLModel, table=True):
    __tablename__ = "medicines"

    id: int | None = Field(default=None, primary_key=True)
    brand_name: str = Field(index=True)
    active_ingredient: str = Field(index=True)
    strength: str
    dosage_form: str
    route: str
    release_type: str = "immediate"
    manufacturer: str | None = None
    registration_no: str | None = Field(default=None, index=True)
    data_source: str = "demo_dataset"

    prescription_items: list["PrescriptionItem"] = Relationship(back_populates="medicine")
    verifications: list["Verification"] = Relationship(back_populates="medicine")


class PrescriptionItem(SQLModel, table=True):
    __tablename__ = "prescription_items"

    id: int | None = Field(default=None, primary_key=True)
    prescription_id: int = Field(foreign_key="prescriptions.id", index=True)
    medicine_id: int | None = Field(default=None, foreign_key="medicines.id", index=True)
    medicine_name: str
    strength: str | None = None
    dose: str | None = None
    frequency: str | None = None
    duration_days: int | None = None
    instructions: str | None = None
    needs_review: bool = True

    prescription: Prescription = Relationship(back_populates="items")
    medicine: Medicine | None = Relationship(back_populates="prescription_items")
    schedule_doses: list["ScheduleDose"] = Relationship(back_populates="prescription_item")


class ScheduleDose(SQLModel, table=True):
    __tablename__ = "schedule_doses"
    __table_args__ = (
        UniqueConstraint("prescription_item_id", "scheduled_at", name="uq_schedule_dose_item_time"),
        CheckConstraint("status IN ('pending', 'taken', 'missed')", name="ck_schedule_dose_status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    prescription_item_id: int = Field(foreign_key="prescription_items.id", index=True)
    scheduled_at: datetime = Field(sa_type=UTCDateTime())
    status: str = Field(default="pending", index=True)
    taken_at: datetime | None = Field(default=None, sa_type=UTCDateTime())

    prescription_item: PrescriptionItem = Relationship(back_populates="schedule_doses")


class Verification(SQLModel, table=True):
    __tablename__ = "verifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('record_match', 'inconsistent_information', 'unable_to_verify')",
            name="ck_verification_status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patients.id", index=True)
    medicine_id: int | None = Field(default=None, foreign_key="medicines.id", index=True)
    extracted_details_json: str
    findings_json: str
    status: str = Field(index=True)
    source: str

    patient: Patient = Relationship(back_populates="verifications")
    medicine: Medicine | None = Relationship(back_populates="verifications")
    reports: list["Report"] = Relationship(back_populates="verification")


class Report(SQLModel, table=True):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("status = 'draft_not_submitted'", name="ck_report_draft_status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    verification_id: int = Field(foreign_key="verifications.id", index=True)
    pharmacy_name: str
    purchase_date: date | None = None
    description: str
    status: str = Field(default="draft_not_submitted", index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_type=UTCDateTime())

    verification: Verification = Relationship(back_populates="reports")
