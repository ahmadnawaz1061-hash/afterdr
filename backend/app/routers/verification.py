import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_session
from app.schemas import (
    PackageExtractionResponse,
    VerificationCreateRequest,
    VerificationResponse,
)
from app.services.gemini_service import GeminiServiceError
from app.services.auth_service import AuthenticatedUser, get_current_user
from app.services.image_validation import (
    MAX_IMAGE_SIZE,
    ImageTooLargeError,
    ImageValidationError,
)
from app.services.verification_service import (
    LIMITATIONS,
    VerificationMedicineNotFoundError,
    VerificationPatientNotFoundError,
    VerificationSaveError,
    extract_package_draft,
    verify_package,
)


router = APIRouter(prefix="/api/verifications", tags=["verification"])
logger = logging.getLogger(__name__)


@router.post("/extract", response_model=PackageExtractionResponse)
async def extract_package(
    file: UploadFile = File(...),
    _user: AuthenticatedUser = Depends(get_current_user),
) -> PackageExtractionResponse:
    image_bytes = await file.read(MAX_IMAGE_SIZE + 1)
    await file.close()
    try:
        extraction, simulated = await run_in_threadpool(
            extract_package_draft,
            image_bytes,
        )
    except ImageTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GeminiServiceError as exc:
        logger.warning(
            "Package extraction failed: category=%s message=%s",
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
            "Unexpected package extraction failure: category=%s "
            "message=Package extraction is temporarily unavailable",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Package extraction is temporarily unavailable",
        ) from exc

    valid_fields = set(PackageExtractionResponse.model_fields.keys())
    data = {k: v for k, v in extraction.model_dump().items() if k in valid_fields}
    return PackageExtractionResponse(
        **data,
        is_demo=simulated,
        simulated=simulated,
    )


from app.schemas import (
    EvidenceResponse,
    PackageExtractionResponse,
    SourceLinkResponse,
    VerificationCreateRequest,
    VerificationResponse,
)


@router.post("", response_model=VerificationResponse, status_code=201)
def create_verification(
    payload: VerificationCreateRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> VerificationResponse:
    try:
        result = verify_package(
            session,
            payload.model_copy(update={"patient_id": user.patient.id}),
        )
    except (VerificationPatientNotFoundError, VerificationMedicineNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VerificationSaveError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    assessment = result.assessment
    return VerificationResponse(
        verification_id=result.verification.id,
        status=result.verification.status,
        findings=list(result.findings),
        counterfeit_confirmed=False,
        source=result.source,
        limitations=LIMITATIONS,
        is_demo=result.source == "demo_dataset",
        outcome=assessment.outcome if assessment else "registered_unconfirmed",
        outcome_label=assessment.outcome_label if assessment else "Registered product found",
        summary_message=assessment.summary_message if assessment else "",
        discrepancies=list(assessment.discrepancies) if assessment else [],
        evidence=[
            EvidenceResponse(
                category=e.category,
                source=e.source,
                detail=e.detail,
                is_critical=e.is_critical,
                source_url=e.source_url,
            )
            for e in (assessment.evidence if assessment else [])
        ],
        recommended_next_steps=list(assessment.recommended_next_steps) if assessment else [],
        source_links=[
            SourceLinkResponse(title=s["title"], url=s["url"])
            for s in (assessment.source_links if assessment else [])
        ],
        assessed_at=assessment.assessed_at if assessment else "",
    )
