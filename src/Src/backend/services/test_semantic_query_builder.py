from src.Src.backend.medical_context import MedicalContext
from src.Src.backend.services.semantic_query_builder import (
    SemanticQueryBuilder,
)


context = MedicalContext(
    diagnoses=[
        "coronary artery disease"
    ],
    symptoms=[
        "chest pain"
    ],
    procedures=[
        "CABG"
    ],
    clinical_findings=[
        "reduced ejection fraction"
    ],
    icd10_codes=[
        "I25"
    ],
    canonical_specialties=[
        "Cardiology"
    ],
    primary_specialty="Cardiology",
    extraction_status="success"
)


builder = SemanticQueryBuilder()

query = builder.build(
    context
)

print(query)