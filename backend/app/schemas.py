from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DoseStatus = Literal["pending", "taken", "missed"]
VerificationStatus = Literal["record_match", "inconsistent_information", "unable_to_verify"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"


class RegisterRequest(ContractModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("name", "email")
    @classmethod
    def normalize_account_text(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("This field must not be blank")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email_shape(cls, value: str) -> str:
        normalized = value.casefold()
        local, separator, domain = normalized.partition("@")
        if not separator or not local or "." not in domain or domain.startswith("."):
            raise ValueError("Enter a valid email address")
        return normalized


class LoginRequest(ContractModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AuthUserResponse(ContractModel):
    id: int
    patient_id: int
    name: str
    email: str


class PrescriptionMedicine(ContractModel):
    name: str = Field(min_length=1)
    strength: str | None = None
    dose: str | None = None
    frequency: str | None = None
    duration_days: int | None = Field(default=None, ge=1)
    instructions: str | None = None
    needs_review: bool = True
    is_demo: bool = True

    @field_validator("name")
    @classmethod
    def medicine_name_must_not_be_blank(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Medicine name must not be blank")
        return name


class ExtractedPrescriptionMedicine(ContractModel):
    name: str | None = None
    strength: str | None = None
    dose: str | None = None
    frequency: str | None = None
    duration_days: int | None = Field(default=None, ge=1)
    instructions: str | None = None
    needs_review: bool = True
    is_demo: bool = False


class PrescriptionExtractionResponse(ContractModel):
    status: Literal["needs_review"] = "needs_review"
    patient_name: str | None = None
    doctor_name: str | None = None
    is_demo: bool = False
    medicines: list[ExtractedPrescriptionMedicine]
    simulated: bool = False


class PrescriptionCreateRequest(ContractModel):
    patient_id: int = Field(default=1, ge=1)
    patient_name: str | None = None
    doctor_name: str | None = None
    status: Literal["confirmed"] = "confirmed"
    auto_schedule: bool = True
    medicines: list[PrescriptionMedicine] = Field(min_length=1)


class PrescriptionSchedulingItem(ContractModel):
    prescription_item_id: int
    medicine_name: str
    status: Literal["scheduled", "needs_times"]
    times: list[str]
    doses_created: int = Field(ge=0)
    reason: str | None = None


class PrescriptionSchedulingResponse(ContractModel):
    items: list[PrescriptionSchedulingItem]
    error: str | None = None


class PrescriptionCreateResponse(ContractModel):
    prescription_id: int
    status: Literal["confirmed"] = "confirmed"
    medicine_count: int = Field(ge=1)
    scheduling: PrescriptionSchedulingResponse | None = None


class PrescriptionItemResponse(PrescriptionMedicine):
    prescription_item_id: int = Field(ge=1)
    medicine_id: int | None = Field(default=None, ge=1)


class PrescriptionDetailResponse(ContractModel):
    prescription_id: int
    patient_id: int
    status: Literal["confirmed"] = "confirmed"
    created_at: datetime
    medicines: list[PrescriptionItemResponse]
    is_demo: bool = False


class ScheduleCreateRequest(ContractModel):
    prescription_item_id: int = Field(ge=1)
    start_date: date
    duration_days: int = Field(default=5, ge=1, le=365)
    reminder_times: list[time] = Field(min_length=1)
    timezone: str = "Asia/Karachi"

    @field_validator("reminder_times")
    @classmethod
    def reminder_times_must_be_local(cls, values: list[time]) -> list[time]:
        if any(value.tzinfo is not None for value in values):
            raise ValueError("Reminder times must not include a UTC offset")
        return values

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_valid(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        name = value.strip()
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA timezone") from exc
        return name


class ScheduleCreateResponse(ContractModel):
    schedule_id: int
    doses_created: int = Field(ge=0)
    status: Literal["scheduled"] = "scheduled"


class ScheduleDoseResponse(ContractModel):
    id: int
    prescription_item_id: int
    medicine_name: str
    dose: str | None = None
    scheduled_at: datetime
    local_time: str
    status: DoseStatus
    taken_at: datetime | None = None
    is_demo: bool = False


class ScheduleUpdateRequest(ContractModel):
    status: DoseStatus
    taken_at: datetime | None = None


class ScheduleRegenerateRequest(ContractModel):
    reminder_times: list[time] = Field(min_length=1)
    timezone: str = "Asia/Karachi"

    @field_validator("reminder_times")
    @classmethod
    def times_must_be_local(cls, values: list[time]) -> list[time]:
        if any(value.tzinfo is not None for value in values):
            raise ValueError("Reminder times must not include a UTC offset")
        return values

    @field_validator("timezone")
    @classmethod
    def regenerate_timezone_must_be_valid(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(value.strip())
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA timezone") from exc
        return value.strip()


class ScheduleDayResponse(ContractModel):
    date: date
    doses: list[ScheduleDoseResponse]


class ScheduleItemResponse(ContractModel):
    prescription_item_id: int
    medicine_name: str
    dose: str | None = None
    frequency: str | None = None
    duration_days: int | None = None
    status: Literal["scheduled", "needs_times"]
    reason: str | None = None
    times: list[str]
    suggested_times: list[str]
    course_start: date | None = None
    course_end: date | None = None
    days: list[ScheduleDayResponse]


class ConfirmedPrescriptionOption(ContractModel):
    prescription_id: int
    created_at: datetime


class PrescriptionScheduleResponse(ContractModel):
    prescription_id: int | None = None
    timezone: str
    prescriptions: list[ConfirmedPrescriptionOption]
    items: list[ScheduleItemResponse]


class MedicineResponse(ContractModel):
    id: int
    brand_name: str
    active_ingredient: str
    strength: str
    dosage_form: str
    route: str
    release_type: str = "immediate"
    manufacturer: str | None = None
    registration_no: str | None = None
    data_source: str = "demo_dataset"
    is_demo: bool = True


class AlternativeMedicineResponse(MedicineResponse):
    is_alternative: Literal[True] = True
    match_reasons: list[str]
    notice: Literal["Confirm with your pharmacist or prescriber before substituting."] = (
        "Confirm with your pharmacist or prescriber before substituting."
    )


class PackageExtractionResponse(ContractModel):
    brand_name: str | None = None
    manufacturer: str | None = None
    registration_number: str | None = None
    batch_number: str | None = None
    expiry_date_text: str | None = None
    strength: str | None = None
    dosage_form: str | None = None
    needs_review: bool = True
    is_demo: bool = False
    simulated: bool = False


class VerificationCreateRequest(ContractModel):
    patient_id: int = Field(default=1, ge=1)
    medicine_id: int | None = Field(default=None, ge=1)
    brand_name: str | None = "Demo Medicine A"
    manufacturer: str | None = "Demo Manufacturer B"
    registration_number: str | None = None
    batch_number: str | None = None
    expiry_date_text: str | None = None
    strength: str | None = "500 mg"
    dosage_form: str | None = "tablet"


class VerificationFinding(ContractModel):
    field: str
    result: Literal["match", "mismatch", "not_available"]
    message: str


class VerificationResponse(ContractModel):
    verification_id: int = Field(ge=1)
    status: VerificationStatus
    findings: list[VerificationFinding]
    counterfeit_confirmed: Literal[False] = False
    source: str = "demo_dataset"
    limitations: str
    is_demo: bool = True


class ReportCreateRequest(ContractModel):
    verification_id: int = Field(ge=1)
    pharmacy_name: str
    purchase_date: date | None = None
    description: str

    @field_validator("pharmacy_name", "description")
    @classmethod
    def required_report_text_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field must not be blank")
        return cleaned


class ReportCreateResponse(ContractModel):
    report_id: int
    status: Literal["draft_not_submitted"] = "draft_not_submitted"


class ReportDownloadResponse(ContractModel):
    """OpenAPI metadata for the binary report download endpoint."""

    report_id: int
    media_type: Literal["application/pdf"] = "application/pdf"
    status: Literal["draft_not_submitted"] = "draft_not_submitted"


class DashboardPatient(ContractModel):
    id: int
    name: str


class DashboardToday(ContractModel):
    total_doses: int
    taken: int
    remaining: int


class DashboardNextDose(ContractModel):
    medicine: str
    time: str


class DashboardResponse(ContractModel):
    patient: DashboardPatient
    active_prescriptions: int
    today: DashboardToday
    next_dose: DashboardNextDose | None
    recent_verifications: int
