from datetime import datetime, time, timedelta, timezone

from app.schemas import MedicineResponse, PrescriptionMedicine, ScheduleDoseResponse


DEMO_TIMEZONE = timezone(timedelta(hours=5), name="Asia/Karachi")

DEMO_PRESCRIPTION_MEDICINES = [
    PrescriptionMedicine(
        name="Demo Medicine A",
        strength="500 mg",
        dose="1 tablet",
        frequency="Twice daily",
        duration_days=5,
        instructions="After food",
        needs_review=True,
        is_demo=True,
    ),
    PrescriptionMedicine(
        name="Demo Medicine C",
        strength="10 mg",
        dose="1 capsule",
        frequency="Once daily",
        duration_days=3,
        instructions=None,
        needs_review=True,
        is_demo=True,
    ),
]

DEMO_CATALOG = [
    MedicineResponse(
        id=1,
        brand_name="Demo Medicine A",
        active_ingredient="Demo Ingredient A",
        strength="500 mg",
        dosage_form="tablet",
        route="oral",
        release_type="immediate",
        manufacturer="Demo Manufacturer A",
        registration_no=None,
        data_source="demo_dataset",
        is_demo=True,
    ),
    MedicineResponse(
        id=2,
        brand_name="Demo Medicine B",
        active_ingredient="Demo Ingredient A",
        strength="500 mg",
        dosage_form="tablet",
        route="oral",
        release_type="immediate",
        manufacturer="Demo Manufacturer B",
        registration_no=None,
        data_source="demo_dataset",
        is_demo=True,
    ),
    MedicineResponse(
        id=3,
        brand_name="Demo Medicine C",
        active_ingredient="Demo Ingredient C",
        strength="10 mg",
        dosage_form="capsule",
        route="oral",
        release_type="immediate",
        manufacturer="Demo Manufacturer C",
        registration_no=None,
        data_source="demo_dataset",
        is_demo=True,
    ),
]


def demo_today_schedule(now: datetime | None = None) -> list[ScheduleDoseResponse]:
    local_now = (now or datetime.now(timezone.utc)).astimezone(DEMO_TIMEZONE)
    local_date = local_now.date()

    def utc_at(local_time: time) -> datetime:
        return datetime.combine(local_date, local_time, DEMO_TIMEZONE).astimezone(timezone.utc)

    return [
        ScheduleDoseResponse(
            id=301,
            prescription_item_id=201,
            medicine_name="Demo Medicine A",
            scheduled_at=utc_at(time(9)),
            local_time="09:00",
            status="taken",
            taken_at=utc_at(time(9, 5)),
            is_demo=True,
        ),
        ScheduleDoseResponse(
            id=302,
            prescription_item_id=202,
            medicine_name="Demo Medicine C",
            scheduled_at=utc_at(time(14)),
            local_time="14:00",
            status="missed",
            taken_at=None,
            is_demo=True,
        ),
        ScheduleDoseResponse(
            id=303,
            prescription_item_id=201,
            medicine_name="Demo Medicine A",
            scheduled_at=utc_at(time(21)),
            local_time="21:00",
            status="pending",
            taken_at=None,
            is_demo=True,
        ),
    ]
