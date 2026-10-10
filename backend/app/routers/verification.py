import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
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

from app.services.packaging_contracts import PackagingAssessment, PackagingCorrections, PackagingHistoryItem
from app.services.packaging_service import (
    analyze_packaging, reanalyze_packaging, get_packaging_check, list_packaging_checks, PackagingWorkflowError,
)


def _packaging_http_error(exc):
    if isinstance(exc, ImageTooLargeError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, ImageValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    status = getattr(exc, 'status_code', 502)
    message = getattr(exc, 'public_message', 'Packaging analysis is temporarily unavailable')
    headers = {'Retry-After': getattr(exc, 'retry_after', None) or '60'} if status == 429 else None
    return HTTPException(status_code=status, detail=message, headers=headers)


@router.post('/analyze', response_model=PackagingAssessment, status_code=201)
async def analyze_package(
    images: list[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),
    trusted_reference: UploadFile | None = File(default=None),
    brand_name: str | None = Form(default=None, max_length=200),
    manufacturer: str | None = Form(default=None, max_length=250),
    registration_number: str | None = Form(default=None, max_length=80),
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
):
    uploads = (images or []) + ([file] if file else [])
    all_uploads = uploads + ([trusted_reference] if trusted_reference else [])
    try:
        if images and file:
            raise ImageValidationError('Use images or the legacy file field, not both')
        if not 1 <= len(uploads) <= 3:
            raise ImageValidationError('Upload one to three photos, with the front of the pack first')
        data = [await image.read(MAX_IMAGE_SIZE + 1) for image in uploads]
        reference_data = await trusted_reference.read(MAX_IMAGE_SIZE + 1) if trusted_reference else None
        fields = {key: value for key, value in {'brand_name': brand_name, 'manufacturer': manufacturer, 'registration_number': registration_number}.items() if value is not None}
        return await run_in_threadpool(analyze_packaging, session, user.patient.id, data, PackagingCorrections(**fields), reference_data)
    except (ImageValidationError, GeminiServiceError, PackagingWorkflowError) as exc:
        raise _packaging_http_error(exc) from exc
    except Exception as exc:
        logger.error('Packaging analysis failed: category=%s', type(exc).__name__)
        raise HTTPException(status_code=502, detail='Packaging analysis is temporarily unavailable') from exc
    finally:
        for image in all_uploads:
            await image.close()


@router.post('/{verification_id:int}/reanalyze', response_model=PackagingAssessment, status_code=201)
def reanalyze_check(verification_id: int, payload: PackagingCorrections, session: Session = Depends(get_session), user: AuthenticatedUser = Depends(get_current_user)):
    try:
        return reanalyze_packaging(session, user.patient.id, verification_id, payload)
    except PackagingWorkflowError as exc:
        raise _packaging_http_error(exc) from exc


@router.get('/{verification_id:int}', response_model=PackagingAssessment)
def get_check(verification_id: int, session: Session = Depends(get_session), user: AuthenticatedUser = Depends(get_current_user)):
    try:
        return get_packaging_check(session, user.patient.id, verification_id)
    except PackagingWorkflowError as exc:
        raise _packaging_http_error(exc) from exc


@router.get('', response_model=list[PackagingHistoryItem])
def list_checks(limit: int = Query(default=10, ge=1, le=50), offset: int = Query(default=0, ge=0, le=10000), session: Session = Depends(get_session), user: AuthenticatedUser = Depends(get_current_user)):
    return list_packaging_checks(session, user.patient.id, limit, offset)


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
