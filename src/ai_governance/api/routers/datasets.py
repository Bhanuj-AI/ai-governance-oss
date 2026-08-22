from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ai_governance.api.dependencies import get_dataset_registry_service
from ai_governance.api.dependencies.authorization import enforce_permission
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models import DatasetResponse, ErrorResponse
from ai_governance.datasets import (
    dataset_id_for_upload,
    dataset_object_store_from_environment,
    dataset_object_uri,
    inspect_uploaded_dataset_stream,
    object_key_for_upload,
)
from ai_governance.services.datasets import (
    DatasetDuplicateContentError,
    DatasetLifecycleError,
    DatasetNotFoundError,
    DatasetVersionConflictError,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.permissions import Permission

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
        "Store one CSV or JSONL dataset in the configured immutable object "
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
        item for item in dataset_registry_service.list_versions(name, context)
    ]
    if any(item.version == version for item in versions):
        raise DatasetVersionConflictError(
            f"Dataset '{name}' version '{version}' already exists."
        )
    content = inspect_uploaded_dataset_stream(
        filename=file.filename,
        stream=file.file,
        max_bytes=int(os.getenv("AI_GOVERNANCE_DATASET_MAX_UPLOAD_BYTES", "10485760")),
        max_record_bytes=int(os.getenv("AI_GOVERNANCE_DATASET_MAX_RECORD_BYTES", "1048576")),
        max_fields=int(os.getenv("AI_GOVERNANCE_DATASET_MAX_FIELDS", "256")),
    )
    if any(item.checksum == content.checksum for item in versions):
        raise DatasetDuplicateContentError(
            f"Dataset '{name}' already contains this exact artifact checksum."
        )
    bucket = os.getenv("AI_GOVERNANCE_DATASET_S3_BUCKET", "ai-governance-datasets")
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
    storage_uri = dataset_object_uri(object_store, bucket=bucket, key=key)
    try:
        dataset = dataset_registry_service.register_dataset(
            name=name, version=version, description=description,
            storage_uri=storage_uri,
            storage_type="S3" if storage_uri.startswith("s3://") else "filesystem",
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
        for dataset in dataset_registry_service.list_datasets(context)
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

    return DatasetResponse.from_domain(dataset_registry_service.get_dataset(dataset_id, context))


@router.post(
    "/{dataset_id}/freeze",
    response_model=DatasetResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_permission(Permission.ASSET_MANAGE))],
    summary="Freeze a dataset version for evaluation",
    description=(
        "Transition one managed dataset version to FROZEN. The recorded artifact "
        "and checksum remain immutable and the version becomes eligible for governed experiments."
    ),
)
def freeze_dataset(
    dataset_id: str,
    dataset_registry_service: Annotated[object, Depends(get_dataset_registry_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> DatasetResponse:
    return DatasetResponse.from_domain(
        _transition_dataset(dataset_registry_service.freeze_dataset, dataset_id, context)
    )


@router.post(
    "/{dataset_id}/activate",
    response_model=DatasetResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_permission(Permission.ASSET_MANAGE))],
    summary="Activate a dataset version",
    description=(
        "Activate one managed dataset version and deprecate any other active "
        "version of the same logical dataset in the selected tenant scope."
    ),
)
def activate_dataset(
    dataset_id: str,
    dataset_registry_service: Annotated[object, Depends(get_dataset_registry_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> DatasetResponse:
    return DatasetResponse.from_domain(
        _transition_dataset(dataset_registry_service.promote_dataset, dataset_id, context)
    )


@router.post(
    "/{dataset_id}/deprecate",
    response_model=DatasetResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_permission(Permission.ASSET_MANAGE))],
    summary="Deprecate a dataset version",
    description="Mark a dataset version as deprecated while preserving historical evidence.",
)
def deprecate_dataset(
    dataset_id: str,
    dataset_registry_service: Annotated[object, Depends(get_dataset_registry_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> DatasetResponse:
    return DatasetResponse.from_domain(
        _transition_dataset(dataset_registry_service.deprecate_dataset, dataset_id, context)
    )


@router.post(
    "/{dataset_id}/archive",
    response_model=DatasetResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_permission(Permission.ASSET_MANAGE))],
    summary="Archive a dataset version",
    description="Archive a dataset version so it is no longer available for governed use.",
)
def archive_dataset(
    dataset_id: str,
    dataset_registry_service: Annotated[object, Depends(get_dataset_registry_service)],
    context: Annotated[TenantContext, Depends(get_compatible_tenant_context)],
) -> DatasetResponse:
    return DatasetResponse.from_domain(
        _transition_dataset(dataset_registry_service.archive_dataset, dataset_id, context)
    )


def _transition_dataset(operation, dataset_id: str, context: TenantContext):
    try:
        return operation(dataset_id, context)
    except DatasetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' was not found.",
        ) from exc
    except DatasetLifecycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
