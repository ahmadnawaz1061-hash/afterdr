from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlmodel import Session

from app.database import get_session
from app.schemas import ReportCreateRequest, ReportCreateResponse
from app.services.report_service import (
    ReportNotFoundError,
    ReportSaveError,
    ReportVerificationNotFoundError,
    create_report_draft,
    generate_report_pdf,
)
from app.models import Report, Verification
from app.services.auth_service import AuthenticatedUser, get_current_user


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("", response_model=ReportCreateResponse, status_code=201)
def create_report(
    payload: ReportCreateRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ReportCreateResponse:
    verification = session.get(Verification, payload.verification_id)
    if verification is None or verification.patient_id != user.patient.id:
        raise HTTPException(status_code=404, detail="Verification not found")
    try:
        report = create_report_draft(session, payload)
    except ReportVerificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReportSaveError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ReportCreateResponse(
        report_id=report.id,
        status=report.status,
    )


@router.get(
    "/{report_id:int}/download",
    response_class=Response,
    responses={
        200: {
            "description": "PDF complaint draft",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def download_report(
    report_id: int = Path(ge=1),
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    report_record = session.get(Report, report_id)
    verification = (
        session.get(Verification, report_record.verification_id)
        if report_record is not None else None
    )
    if verification is None or verification.patient_id != user.patient.id:
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        pdf_bytes = generate_report_pdf(session, report_id)
    except (ReportNotFoundError, ReportVerificationNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="medcare-report-{report_id}-draft.pdf"'},
    )
