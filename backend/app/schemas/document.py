import uuid
from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadResponse(BaseModel):
    """
    Structured response model returned after successful document upload.
    Contains essential metadata of the created document record.
    """

    document_id: uuid.UUID = Field(
        ...,
        description="Unique UUID identifier generated for the uploaded document",
        examples=["a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"],
    )
    filename: str = Field(
        ...,
        description="Sanitized original filename of the uploaded document",
        examples=["HR-TRV-001_Travel_Reimbursement_v1.0.pdf"],
    )
    file_type: str = Field(
        ...,
        description="Normalized file format type ('pdf', 'docx', 'txt')",
        examples=["pdf"],
    )
    status: str = Field(
        ...,
        description="Initial processing status of the document record (set to 'uploaded')",
        examples=["uploaded"],
    )

    model_config = ConfigDict(from_attributes=True)
