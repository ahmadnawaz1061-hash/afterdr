"""Prescription extraction and persistence workflows."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import Patient, Prescription, PrescriptionItem
from app.repositories.medicine_repository import MedicineRepository
from app.schemas import PrescriptionCreateRequest
from app.services import gemini_service
from app.services.gemini_service import PrescriptionExtraction
from app.services.image_validation import validate_image


class PrescriptionServiceError(RuntimeError):
    """Base error for prescription persistence failures."""


class PatientNotFoundError(PrescriptionServiceError):
    """Raised when the requested prescription owner does not exist."""


class PrescriptionNotFoundError(PrescriptionServiceError):
    """Raised when a prescription cannot be found."""


class PrescriptionSaveError(PrescriptionServiceError):
    """Raised after a failed transaction has been rolled back."""


def extract_prescription_draft(
    image_bytes: bytes,
) -> tuple[PrescriptionExtraction, bool]:
    """Validate and transcribe an image without writing to the database."""
    mime_type = validate_image(image_bytes)
    extraction = gemini_service.extract_prescription(image_bytes, mime_type)
    return extraction, gemini_service.using_mock_ai()


def _catalog_medicine_id(
    repository: MedicineRepository,
    medicine_name: str,
) -> int | None:
    normalized_name = medicine_name.casefold()
    for medicine in repository.search_by_name(medicine_name):
        if medicine.brand_name.casefold() == normalized_name:
            return medicine.id
    return None


def save_confirmed_prescription(
    session: Session,
    payload: PrescriptionCreateRequest,
) -> Prescription:
    """Save a confirmed prescription and all items in one transaction."""
    try:
        if session.get(Patient, payload.patient_id) is None:
            raise PatientNotFoundError(
                f"Patient {payload.patient_id} does not exist"
            )

        repository = MedicineRepository(session)
        catalog_ids = [
            _catalog_medicine_id(repository, medicine.name)
            for medicine in payload.medicines
        ]

        prescription = Prescription(
            patient_id=payload.patient_id,
            status="confirmed",
        )
        session.add(prescription)
        session.flush()

        items = [
            PrescriptionItem(
                prescription_id=prescription.id,
                medicine_id=medicine_id,
                medicine_name=medicine.name,
                strength=medicine.strength,
                dose=medicine.dose,
                frequency=medicine.frequency,
                duration_days=medicine.duration_days,
                instructions=medicine.instructions,
                needs_review=medicine.needs_review,
            )
            for medicine, medicine_id in zip(payload.medicines, catalog_ids)
        ]
        session.add_all(items)
        session.commit()
        session.refresh(prescription)
        return prescription
    except PatientNotFoundError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        raise PrescriptionSaveError(
            "The confirmed prescription could not be saved"
        ) from exc


def get_prescription_with_items(
    session: Session,
    prescription_id: int,
) -> tuple[Prescription, list[PrescriptionItem]]:
    prescription = session.get(Prescription, prescription_id)
    if prescription is None:
        raise PrescriptionNotFoundError(
            f"Prescription {prescription_id} was not found"
        )

    items = list(session.exec(
        select(PrescriptionItem)
        .where(PrescriptionItem.prescription_id == prescription_id)
        .order_by(PrescriptionItem.id)
    ).all())
    return prescription, items
