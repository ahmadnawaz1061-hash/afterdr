"""Additive packaging-analysis contracts; legacy verification schemas stay intact."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal['name_brand', 'manufacturer', 'label_print', 'packaging_design', 'registration', 'image_quality', 'ingredient_strength']
Severity = Literal['positive', 'neutral', 'low', 'medium', 'high']
Origin = Literal['vision_observation', 'reference_catalog', 'user_correction', 'local_image_quality', 'simulated_demo', 'legacy_record']
RegistrationState = Literal['matched_reference', 'mismatch', 'not_visible', 'not_in_reference', 'simulated_mismatch']
AnalysisStatus = Literal['likely_consistent', 'suspicious', 'unable_to_assess']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PackagingFields(StrictModel):
    brand_name: str | None = Field(default=None, max_length=200)
    active_ingredient: str | None = Field(default=None, max_length=300)
    strength: str | None = Field(default=None, max_length=120)
    dosage_form: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=250)
    registration_number: str | None = Field(default=None, max_length=80)
    pack_type: str | None = Field(default=None, max_length=120)

    @field_validator('*', mode='before')
    @classmethod
    def clean_optional_text(cls, value):
        if isinstance(value, str):
            value = ' '.join(value.split())
            return value or None
        return value


class PackagingCorrections(PackagingFields):
    """Only explicitly set fields replace extracted text; null clears a field."""


class VisualSignal(StrictModel):
    category: Category
    severity: Severity
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=600)
    evidence: str = Field(min_length=1, max_length=400)
    image_index: int | None = Field(default=None, ge=1, le=4)


class PackagingVision(StrictModel):
    extracted: PackagingFields = Field(default_factory=PackagingFields)
    image_quality: Literal['good', 'fair', 'poor', 'unreadable'] = 'unreadable'
    quality_issues: list[str] = Field(default_factory=list, max_length=12)
    signals: list[VisualSignal] = Field(default_factory=list, max_length=24)
    observations: list[str] = Field(default_factory=list, max_length=12)
    human_review: bool = True


class PackagingSignal(StrictModel):
    category: Category
    severity: Severity
    title: str
    detail: str
    origin: Origin
    evidence: str | None = None
    image_index: int | None = None
    reference_url: str | None = None
    registration_state: RegistrationState | None = None
    simulated: bool = False


class MatchedReference(StrictModel):
    brand_name: str
    active_ingredient: str | None = None
    strength: str | None = None
    dosage_form: str | None = None
    manufacturer: str | None = None
    registration_no: str | None = None
    data_source: str
    source_url: str | None = None
    last_verified_at: str | None = None
    match_kind: Literal['exact', 'alias', 'lookalike']
    similarity: float
    comparison_status: str
    notes: str


class ImageQuality(StrictModel):
    image_index: int
    role: str
    width: int
    height: int
    brightness: float
    contrast: float
    edge_variance: float
    issues: list[str]
    unusable: bool


class OnlineSource(StrictModel):
    title: str = Field(max_length=300)
    url: str = Field(max_length=2048)


class OnlineLookup(StrictModel):
    status: Literal['matched', 'not_found', 'unavailable', 'not_searched', 'simulated'] = 'not_searched'
    query: str | None = None
    summary: str = 'Internet lookup has not been performed.'
    sources: list[OnlineSource] = Field(default_factory=list, max_length=6)
    product: PackagingFields | None = None
    searched_at: str | None = None
    source: str = 'Live DRAP public product index'


class PackagingAssessment(StrictModel):
    verification_id: int = Field(default=0, ge=0)
    status: AnalysisStatus
    status_label: str
    risk_level: Literal['low', 'medium', 'high', 'unknown']
    risk_score: int | None = Field(default=None, ge=0, le=100)
    summary: str
    extracted: PackagingFields
    signals: list[PackagingSignal]
    next_steps: list[str]
    matched_reference: MatchedReference | None = None
    registration_state: RegistrationState
    counterfeit_confirmed: Literal[False] = False
    source: str
    limitations: list[str]
    simulated: bool = False
    image_quality: list[ImageQuality] = Field(default_factory=list)
    assessed_at: str
    reanalysis_of: int | None = None
    cached: bool = False
    online_lookup: OnlineLookup = Field(default_factory=OnlineLookup)


class PackagingHistoryItem(StrictModel):
    verification_id: int
    brand_name: str | None
    status: AnalysisStatus
    status_label: str
    risk_level: str
    risk_score: int | None
    simulated: bool
    assessed_at: str | None
