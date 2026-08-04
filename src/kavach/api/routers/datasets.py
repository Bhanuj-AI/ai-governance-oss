from __future__ import annotations

from typing import Annotated

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from kavach.api.dependencies import get_dataset_registry_service
from kavach.api.models import DatasetResponse, ErrorResponse
from kavach.api.dependencies.tenancy import get_compatible_tenant_context
from kavach.datasets import (
    dataset_object_store_from_environment,
    dataset_id_for_upload,
    inspect_uploaded_dataset_stream,
    object_key_for_upload,
)
from kavach.services.datasets import (
    DatasetNotFoundError,
    DatasetDuplicateContentError,
    DatasetVersionConflictError,
)

router = APIRouter(
    prefix="/api/v1/datasets",
    tags=["Datasets"],
)


@router.post(
    "/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Upload and register a dataset version",
    description=(
        "Store one CSV or JSONL dataset in the configured S3-compatible object "
        "store and register an immutable DRAFT dataset version."
    ),
)
async def upload_dataset(
    name: Annotated[str, Form()],
    version: Annotated[str, Form()],
    description: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    schema_version: Annotated[str, Form()] = "1.0",
    dataset_registry_service: Annotated[
        object, Depends(get_dataset_registry_service)
    ] = None,
    context=Depends(get_compatible_tenant_context),
) -> DatasetResponse:
    """Write uploaded immutable bytes, then register the resulting dataset version."""

    object_store = dataset_object_store_from_environment()
    if object_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dataset object storage is not configured.",
        )
    versions = [
        item for item in dataset_registry_service.list_versions(name)
        if getattr(item, "organization_id", "org_default") == context.organization_id
        and getattr(item, "project_id", "project_default") == context.project_id
    ]
    if any(item.version == version for item in versions):
        raise DatasetVersionConflictError(
            f"Dataset '{name}' version '{version}' already exists."
        )
    content = inspect_uploaded_dataset_stream(
        filename=file.filename,
        stream=file.file,
        max_bytes=int(os.getenv("KAVACH_DATASET_MAX_UPLOAD_BYTES", "10485760")),
        max_record_bytes=int(os.getenv("KAVACH_DATASET_MAX_RECORD_BYTES", "1048576")),
        max_fields=int(os.getenv("KAVACH_DATASET_MAX_FIELDS", "256")),
    )
    if any(item.checksum == content.checksum for item in versions):
        raise DatasetDuplicateContentError(
            f"Dataset '{name}' already contains this exact artifact checksum."
        )
    bucket = os.getenv("KAVACH_DATASET_S3_BUCKET", "kavach-datasets")
    dataset_id = dataset_id_for_upload(
        organization_id=context.organization_id,
        project_id=context.project_id,
        name=name,
        version=version,
        checksum=content.checksum,
    )
    key = object_key_for_upload(
        organization_id=context.organization_id,
        project_id=context.project_id,
        dataset_id=dataset_id,
        version=version,
        checksum=content.checksum,
        extension=content.extension,
    )
    write_result = object_store.put_stream(
        bucket=bucket,
        key=key,
        body=file.file,
        content_length=content.content_length,
        content_type=content.content_type,
        metadata={"dataset_id": dataset_id, "version": version, "checksum": content.checksum},
        if_absent=True,
    )
    try:
        dataset = dataset_registry_service.register_dataset(
            name=name, version=version, description=description,
            storage_uri=f"s3://{bucket}/{key}", storage_type="S3",
            schema_version=schema_version, record_count=content.record_count,
            checksum=content.checksum, creator=context.actor_id,
            organization_id=context.organization_id, project_id=context.project_id,
            dataset_id=dataset_id,
        )
    except Exception:
        if write_result.created:
            object_store.delete_object(bucket=bucket, key=key)
        raise
    return DatasetResponse.from_domain(dataset)


@router.get(
    "",
    response_model=list[DatasetResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="List datasets",
    description="Return metadata for registered dataset versions.",
)
def list_datasets(
    dataset_registry_service: Annotated[
        object,
        Depends(get_dataset_registry_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> list[DatasetResponse]:
    """
    Return dataset registry metadata.
    """

    return [
        DatasetResponse.from_domain(dataset)
        for dataset in dataset_registry_service.list_datasets()
        if getattr(dataset, "organization_id", "org_default") == context.organization_id
        and getattr(dataset, "project_id", "project_default") == context.project_id
    ]


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Dataset was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Unexpected server error.",
        },
    },
    summary="Get dataset",
    description="Return metadata for a registered dataset version by ID.",
)
def get_dataset(
    dataset_id: str,
    dataset_registry_service: Annotated[
        object,
        Depends(get_dataset_registry_service),
    ],
    context=Depends(get_compatible_tenant_context),
) -> DatasetResponse:
    """
    Return dataset metadata by ID.
    """

    dataset = dataset_registry_service.get_dataset(dataset_id)
    if (
        getattr(dataset, "organization_id", "org_default") != context.organization_id
        or getattr(dataset, "project_id", "project_default") != context.project_id
    ):
        raise DatasetNotFoundError(f"Dataset '{dataset_id}' does not exist.")
    return DatasetResponse.from_domain(dataset)
