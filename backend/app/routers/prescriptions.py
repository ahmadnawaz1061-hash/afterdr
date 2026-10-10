import logging

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_session
from app.schemas import (
    PrescriptionCreateRequest,
    PrescriptionCreateResponse,
    PrescriptionDetailResponse,
    PrescriptionExtractionResponse,
    PrescriptionItemResponse,
)
from app.services.gemini_service import GeminiServiceError
from app.services.auth_service import AuthenticatedUser, get_current_user
from app.services.image_validation import (
    MAX_IMAGE_SIZE,
    ImageTooLargeError,
    ImageValidationError,
)
from app.services.prescription_service import (
    PatientNotFoundError,
    PrescriptionNotFoundError,
    PrescriptionSaveError,
    extract_prescription_draft,
    get_prescription_with_items,
    save_confirmed_prescription,
)


router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])
logger = logging.getLogger(__name__)


@router.post("/extract", response_model=PrescriptionExtractionResponse)
async def extract_prescription(
    file: UploadFile = File(...),
    _user: AuthenticatedUser = Depends(get_current_user),
) -> PrescriptionExtractionResponse:
    image_bytes = await file.read(MAX_IMAGE_SIZE + 1)
    await file.close()
    try:
        extraction, simulated = await run_in_threadpool(
            extract_prescription_draft,
            image_bytes,
        )
    except ImageTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GeminiServiceError as exc:
        logger.warning(
            "Prescription extraction failed: category=%s message=%s",
            type(exc).__name__,
            exc.public_message,
        )
        headers = {}
        if exc.status_code == 429 and getattr(exc, "retry_after", None):
            headers["Retry-After"] = exc.retry_after
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.public_message,
            headers=headers or None,
        ) from exc
    except Exception as exc:
        logger.error(
            "Unexpected prescription extraction failure: category=%s "
            "message=Prescription extraction is temporarily unavailable",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Prescription extraction is temporarily unavailable",
        ) from exc

    return PrescriptionExtractionResponse(
        patient_name=extraction.patient_name,
        doctor_name=extraction.doctor_name,
        medicines=[
            {**medicine.model_dump(), "is_demo": simulated}
            for medicine in extraction.medicines
        ],
        is_demo=simulated,
        simulated=simulated,
    )


@router.post("", response_model=PrescriptionCreateResponse, status_code=201)
def create_prescription(
    payload: PrescriptionCreateRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> PrescriptionCreateResponse:
    try:
        prescription = save_confirmed_prescription(
            session,
            payload.model_copy(update={"patient_id": user.patient.id}),
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PrescriptionSaveError as exc:
        raise HTTPException(
            status_code=500,
            detail="The confirmed prescription could not be saved",
        ) from exc

    return PrescriptionCreateResponse(
        prescription_id=prescription.id,
        status="confirmed",
        medicine_count=len(payload.medicines),
    )


@router.get("/{prescription_id:int}", response_model=PrescriptionDetailResponse)
def get_prescription(
    prescription_id: int = Path(ge=1),
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> PrescriptionDetailResponse:
    try:
        prescription, items = get_prescription_with_items(session, prescription_id)
    except PrescriptionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if prescription.patient_id != user.patient.id:
        raise HTTPException(status_code=404, detail="Prescription not found")

    medicines = [
        PrescriptionItemResponse(
            prescription_item_id=item.id,
            medicine_id=item.medicine_id,
            name=item.medicine_name,
            strength=item.strength,
            dose=item.dose,
            frequency=item.frequency,
            duration_days=item.duration_days,
            instructions=item.instructions,
            needs_review=item.needs_review,
            is_demo=False,
        )
        for item in items
    ]
    return PrescriptionDetailResponse(
        prescription_id=prescription.id,
        patient_id=prescription.patient_id,
        status="confirmed",
        created_at=prescription.created_at,
        medicines=medicines,
        is_demo=False,
    )
