from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from kavach.domain.jobs import IdempotencyConflictError
from kavach.providers.errors import (
    ProviderContractError,
    ProviderNotFoundError,
    ProviderRegistryError,
)
from kavach.services.decision_application_service import (
    DecisionConflictError,
    DecisionNotFoundError,
    DecisionPersistenceFailedError,
    DecisionReasoningFailedError,
    EvidenceUnavailableError,
    InvalidDecisionRequestError,
    PolicyNotFoundError,
)
from kavach.services.datasets import (
    DatasetDuplicateContentError,
    DatasetNotFoundError,
    DatasetVersionConflictError,
)
from kavach.services.evaluation_api_service import (
    EvaluationNotFoundError,
    EvaluationProviderNotFoundError,
    UnsupportedMetricError,
)
from kavach.services.provider_installation_service import (
    ProviderInstallationDisabledError,
    ProviderInstallationNotFoundError,
    ProviderInstallationTypeUnavailableError,
)
from kavach.services.experiment_api_service import (
    InvalidExperimentRequestError,
)
from kavach.services.experiments import (
    ExperimentCandidateNotFoundError,
    ExperimentNotFoundError,
)
from kavach.services.governance_api_service import (
    GovernanceReportNotImplementedError,
    InvalidGovernanceRequestError,
)
from kavach.services.job_api_service import (
    InvalidJobRequestError,
    JobNotFoundError,
)
from kavach.services.job_submission_service import (
    JobSubmissionValidationError,
)
from kavach.services.models import ModelNotFoundError, ModelVersionConflictError
from kavach.services.policies import (
    InvalidPolicyRequestError as AdminInvalidPolicyRequestError,
    PolicyActivationFailedError,
    PolicyAdminNotFoundError,
    PolicyArchiveFailedError,
    PolicyConflictError as AdminPolicyConflictError,
    PolicySchemaUnavailableError,
    PolicySimulationFailedError,
    PolicyValidationFailedError,
    PolicyVersionNotFoundError,
)
from kavach.services.prompts import PromptNotFoundError, PromptVersionConflictError
from kavach.services.audit_service import AuditRecordNotFoundError
from kavach.domain.replay.errors import (
    ReplayConflict,
    ReplayError,
    ReplayIdempotencyConflict,
    ReplayInvalidMode,
    ReplayInvalidTransition,
    ReplayNotFound,
    ReplayUnauthorized,
)
from kavach.tenancy.authentication import AuthenticationError
from kavach.tenancy.errors import (
    AuthorizationDenied,
    LastOrganizationAdministrator,
    MembershipConflict,
    MembershipNotFound,
    OrganizationNotFound,
    OrganizationSlugConflict,
    ProjectNotFound,
    ProjectSlugConflict,
    RoleAssignmentConflict,
    RoleAssignmentNotFound,
    TenantContextInvalid,
    TenantContextMissing,
    TenantScopeMismatch,
    TenancyError,
)


def register_exception_handlers(
    app: FastAPI,
) -> None:
    """
    Register centralized REST exception handlers.
    """

    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,
    )
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(
        ProviderContractError,
        provider_contract_exception_handler,
    )
    app.add_exception_handler(
        ProviderNotFoundError,
        not_found_exception_handler,
    )
    app.add_exception_handler(
        EvaluationProviderNotFoundError,
        evaluation_provider_not_found_exception_handler,
    )
    app.add_exception_handler(
        UnsupportedMetricError,
        unsupported_metric_exception_handler,
    )
    app.add_exception_handler(
        EvaluationNotFoundError,
        evaluation_not_found_exception_handler,
    )
    app.add_exception_handler(
        ProviderInstallationNotFoundError,
        provider_installation_not_found_exception_handler,
    )
    app.add_exception_handler(
        ProviderInstallationDisabledError,
        provider_installation_disabled_exception_handler,
    )
    app.add_exception_handler(
        ProviderInstallationTypeUnavailableError,
        provider_installation_type_unavailable_exception_handler,
    )
    app.add_exception_handler(ReplayError, replay_exception_handler)
    app.add_exception_handler(
        ExperimentNotFoundError,
        experiment_not_found_exception_handler,
    )
    app.add_exception_handler(
        ExperimentCandidateNotFoundError,
        candidate_not_found_exception_handler,
    )
    app.add_exception_handler(
        InvalidExperimentRequestError,
        invalid_experiment_request_exception_handler,
    )
    app.add_exception_handler(
        InvalidGovernanceRequestError,
        invalid_governance_request_exception_handler,
    )
    app.add_exception_handler(
        DecisionNotFoundError,
        decision_not_found_exception_handler,
    )
    app.add_exception_handler(
        InvalidDecisionRequestError,
        invalid_decision_request_exception_handler,
    )
    app.add_exception_handler(
        DecisionConflictError,
        decision_conflict_exception_handler,
    )
    app.add_exception_handler(
        PolicyNotFoundError,
        policy_not_found_exception_handler,
    )
    app.add_exception_handler(
        EvidenceUnavailableError,
        evidence_unavailable_exception_handler,
    )
    app.add_exception_handler(
        DecisionPersistenceFailedError,
        decision_persistence_failed_exception_handler,
    )
    app.add_exception_handler(
        DecisionReasoningFailedError,
        decision_reasoning_failed_exception_handler,
    )
    app.add_exception_handler(
        GovernanceReportNotImplementedError,
        governance_report_not_implemented_exception_handler,
    )
    app.add_exception_handler(
        JobNotFoundError,
        job_not_found_exception_handler,
    )
    app.add_exception_handler(
        InvalidJobRequestError,
        invalid_job_request_exception_handler,
    )
    app.add_exception_handler(
        JobSubmissionValidationError,
        job_submission_validation_exception_handler,
    )
    app.add_exception_handler(
        AuditRecordNotFoundError,
        audit_record_not_found_exception_handler,
    )
    app.add_exception_handler(
        IdempotencyConflictError,
        idempotency_conflict_exception_handler,
    )
    app.add_exception_handler(
        PromptNotFoundError,
        not_found_exception_handler,
    )
    app.add_exception_handler(
        PromptVersionConflictError,
        asset_version_conflict_exception_handler,
    )
    app.add_exception_handler(
        PolicyAdminNotFoundError,
        policy_admin_not_found_exception_handler,
    )
    app.add_exception_handler(
        PolicyVersionNotFoundError,
        policy_version_not_found_exception_handler,
    )
    app.add_exception_handler(
        AdminPolicyConflictError,
        policy_admin_conflict_exception_handler,
    )
    app.add_exception_handler(
        AdminInvalidPolicyRequestError,
        policy_admin_invalid_request_exception_handler,
    )
    app.add_exception_handler(
        PolicyValidationFailedError,
        policy_admin_invalid_request_exception_handler,
    )
    app.add_exception_handler(
        PolicyActivationFailedError,
        policy_admin_invalid_request_exception_handler,
    )
    app.add_exception_handler(
        PolicyArchiveFailedError,
        policy_admin_invalid_request_exception_handler,
    )
    app.add_exception_handler(
        PolicySimulationFailedError,
        policy_admin_invalid_request_exception_handler,
    )
    app.add_exception_handler(
        PolicySchemaUnavailableError,
        policy_schema_unavailable_exception_handler,
    )
    app.add_exception_handler(
        ModelNotFoundError,
        not_found_exception_handler,
    )
    app.add_exception_handler(
        ModelVersionConflictError,
        asset_version_conflict_exception_handler,
    )
    app.add_exception_handler(
        DatasetNotFoundError,
        not_found_exception_handler,
    )
    app.add_exception_handler(
        DatasetVersionConflictError,
        dataset_version_conflict_exception_handler,
    )
    app.add_exception_handler(
        DatasetDuplicateContentError,
        dataset_version_conflict_exception_handler,
    )
    app.add_exception_handler(
        ProviderRegistryError,
        provider_registry_exception_handler,
    )
    app.add_exception_handler(ValueError, value_error_exception_handler)
    app.add_exception_handler(TenancyError, tenancy_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)


async def tenancy_exception_handler(
    request: Request, exc: TenancyError
) -> JSONResponse:
    not_found = (
        OrganizationNotFound,
        ProjectNotFound,
        MembershipNotFound,
        RoleAssignmentNotFound,
    )
    conflict = (
        OrganizationSlugConflict,
        ProjectSlugConflict,
        MembershipConflict,
        RoleAssignmentConflict,
        LastOrganizationAdministrator,
    )
    invalid = (TenantContextInvalid, TenantContextMissing, TenantScopeMismatch)
    if isinstance(exc, AuthorizationDenied):
        decision = exc.decision
        if not hasattr(decision, "permission"):
            return _error_response(
                status_code=403,
                code="authorization_denied",
                message=str(exc),
                details={
                    "reason_code": str(getattr(decision, "reason_code", "DENIED")),
                    "decision_id": getattr(decision, "decision_id", None),
                },
            )
        return _error_response(
            status_code=403,
            code="authorization_denied",
            message=str(exc),
            details={
                "permission": decision.permission.value,
                "reason_code": decision.reason_code.value,
                "permission_model_version": decision.permission_model_version,
            },
        )
    if isinstance(exc, not_found):
        return _error_response(
            status_code=404, code=exc.__class__.__name__, message=str(exc)
        )
    if isinstance(exc, conflict):
        return _error_response(
            status_code=409, code=exc.__class__.__name__, message=str(exc)
        )
    if isinstance(exc, invalid):
        return _error_response(
            status_code=400, code=exc.__class__.__name__, message=str(exc)
        )
    return _error_response(
        status_code=400, code=exc.__class__.__name__, message=str(exc)
    )


async def replay_exception_handler(
    request: Request,
    exc: ReplayError,
) -> JSONResponse:
    if isinstance(exc, ReplayNotFound):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ReplayUnauthorized):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (ReplayConflict, ReplayIdempotencyConflict)):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, (ReplayInvalidMode, ReplayInvalidTransition)):
        code = status.HTTP_400_BAD_REQUEST
    else:
        code = status.HTTP_400_BAD_REQUEST
    return _error_response(
        status_code=code, code=exc.__class__.__name__, message=str(exc)
    )


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Handle FastAPI request validation failures.
    """

    return _error_response(
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        details=jsonable_encoder(exc.errors()),
    )


async def validation_exception_handler(
    request: Request,
    exc: ValidationError,
) -> JSONResponse:
    """
    Handle Pydantic validation failures outside request parsing.
    """

    return _error_response(
        status_code=422,
        code="validation_error",
        message="Validation failed.",
        details=jsonable_encoder(exc.errors()),
    )


async def provider_contract_exception_handler(
    request: Request,
    exc: ProviderContractError,
) -> JSONResponse:
    """
    Handle provider contract failures.
    """

    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="provider_contract_error",
        message=str(exc),
    )


async def not_found_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Handle registry resource lookup failures.
    """

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="not_found",
        message=str(exc),
    )


async def evaluation_provider_not_found_exception_handler(
    request: Request,
    exc: EvaluationProviderNotFoundError,
) -> JSONResponse:
    """
    Handle provider lookup failures for evaluation submissions.
    """

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="PROVIDER_NOT_FOUND",
        message=str(exc),
        details={"provider_name": exc.provider_name},
    )


async def provider_installation_not_found_exception_handler(
    request: Request,
    exc: ProviderInstallationNotFoundError,
) -> JSONResponse:
    """Return a tenant-scoped provider-installation lookup failure."""
    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="PROVIDER_INSTALLATION_NOT_FOUND",
        message=str(exc),
    )


async def provider_installation_disabled_exception_handler(
    request: Request,
    exc: ProviderInstallationDisabledError,
) -> JSONResponse:
    """Prevent disabled installations from being used by runtime operations."""
    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="PROVIDER_INSTALLATION_DISABLED",
        message=str(exc),
    )


async def provider_installation_type_unavailable_exception_handler(
    request: Request,
    exc: ProviderInstallationTypeUnavailableError,
) -> JSONResponse:
    """Report an installation whose shipped adapter is unavailable."""
    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="PROVIDER_TYPE_UNAVAILABLE",
        message=str(exc),
    )


async def unsupported_metric_exception_handler(
    request: Request,
    exc: UnsupportedMetricError,
) -> JSONResponse:
    """
    Handle unsupported metric requests for evaluation submissions.
    """

    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="UNSUPPORTED_METRIC",
        message=str(exc),
        details={
            "metric": exc.metric,
            "provider_name": exc.provider_name,
        },
    )


async def evaluation_not_found_exception_handler(
    request: Request,
    exc: EvaluationNotFoundError,
) -> JSONResponse:
    """
    Handle evaluation result lookup failures.
    """

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="EVALUATION_NOT_FOUND",
        message=str(exc),
        details={
            "evaluation_id": exc.evaluation_id,
            "execution_id": exc.execution_id,
        },
    )


async def experiment_not_found_exception_handler(
    request: Request,
    exc: ExperimentNotFoundError,
) -> JSONResponse:
    """
    Handle experiment lookup failures.
    """

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="EXPERIMENT_NOT_FOUND",
        message=str(exc),
    )


async def candidate_not_found_exception_handler(
    request: Request,
    exc: ExperimentCandidateNotFoundError,
) -> JSONResponse:
    """
    Handle experiment candidate lookup failures.
    """

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="CANDIDATE_NOT_FOUND",
        message=str(exc),
    )


async def invalid_experiment_request_exception_handler(
    request: Request,
    exc: InvalidExperimentRequestError,
) -> JSONResponse:
    """
    Handle invalid experiment requests.
    """

    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_EXPERIMENT_REQUEST",
        message=str(exc),
    )


async def invalid_governance_request_exception_handler(
    request: Request,
    exc: InvalidGovernanceRequestError,
) -> JSONResponse:
    """
    Handle invalid governance requests.
    """

    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_GOVERNANCE_REQUEST",
        message=str(exc),
    )


async def decision_not_found_exception_handler(
    request: Request,
    exc: DecisionNotFoundError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="DecisionNotFound",
        message=str(exc),
        details={"decision_id": exc.decision_id},
    )


async def invalid_decision_request_exception_handler(
    request: Request,
    exc: InvalidDecisionRequestError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="InvalidDecisionRequest",
        message=str(exc),
    )


async def decision_conflict_exception_handler(
    request: Request,
    exc: DecisionConflictError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_409_CONFLICT,
        code="DecisionConflict",
        message=str(exc),
    )


async def policy_not_found_exception_handler(
    request: Request,
    exc: PolicyNotFoundError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="PolicyNotFound",
        message=str(exc),
        details={"policy_ids": list(exc.policy_ids)},
    )


async def evidence_unavailable_exception_handler(
    request: Request,
    exc: EvidenceUnavailableError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="EvidenceUnavailable",
        message=str(exc),
    )


async def decision_persistence_failed_exception_handler(
    request: Request,
    exc: DecisionPersistenceFailedError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="DecisionPersistenceFailed",
        message=str(exc),
    )


async def decision_reasoning_failed_exception_handler(
    request: Request,
    exc: DecisionReasoningFailedError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="DecisionReasoningFailed",
        message=str(exc),
    )


async def governance_report_not_implemented_exception_handler(
    request: Request,
    exc: GovernanceReportNotImplementedError,
) -> JSONResponse:
    """
    Handle governance report requests without a report generator.
    """

    return _error_response(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        code="GOVERNANCE_REPORT_NOT_IMPLEMENTED",
        message=str(exc),
        details={"evaluation_id": exc.evaluation_id},
    )


async def job_not_found_exception_handler(
    request: Request,
    exc: JobNotFoundError,
) -> JSONResponse:
    """
    Handle job lookup failures.
    """

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="JOB_NOT_FOUND",
        message=str(exc),
        details={"job_id": exc.job_id},
    )


async def invalid_job_request_exception_handler(
    request: Request,
    exc: InvalidJobRequestError,
) -> JSONResponse:
    """
    Handle invalid public job operations.
    """

    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_JOB_REQUEST",
        message=str(exc),
    )


async def job_submission_validation_exception_handler(
    request: Request,
    exc: JobSubmissionValidationError,
) -> JSONResponse:
    """
    Handle invalid job submission payloads from the service layer.
    """

    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="INVALID_JOB_SUBMISSION",
        message=str(exc),
    )


async def audit_record_not_found_exception_handler(
    request: Request,
    exc: AuditRecordNotFoundError,
) -> JSONResponse:
    """
    Handle audit record lookup failures.
    """

    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="AUDIT_RECORD_NOT_FOUND",
        message=str(exc),
        details={"audit_id": exc.audit_id},
    )


async def idempotency_conflict_exception_handler(
    request: Request,
    exc: IdempotencyConflictError,
) -> JSONResponse:
    """
    Handle idempotency key reuse with different job input.
    """

    return _error_response(
        status_code=status.HTTP_409_CONFLICT,
        code="IDEMPOTENCY_CONFLICT",
        message=str(exc),
    )


async def policy_admin_not_found_exception_handler(
    request: Request,
    exc: PolicyAdminNotFoundError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="PolicyNotFound",
        message=str(exc),
    )


async def policy_version_not_found_exception_handler(
    request: Request,
    exc: PolicyVersionNotFoundError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="PolicyVersionNotFound",
        message=str(exc),
    )


async def policy_admin_conflict_exception_handler(
    request: Request,
    exc: AdminPolicyConflictError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_409_CONFLICT,
        code="PolicyConflict",
        message=str(exc),
    )


async def dataset_version_conflict_exception_handler(
    request: Request,
    exc: DatasetVersionConflictError | DatasetDuplicateContentError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_409_CONFLICT,
        code="DatasetVersionConflict",
        message=str(exc),
    )


async def asset_version_conflict_exception_handler(
    request: Request,
    exc: PromptVersionConflictError | ModelVersionConflictError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_409_CONFLICT,
        code=exc.__class__.__name__.removesuffix("Error"),
        message=str(exc),
    )


async def policy_admin_invalid_request_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=exc.__class__.__name__.removesuffix("Error"),
        message=str(exc),
    )


async def policy_schema_unavailable_exception_handler(
    request: Request,
    exc: PolicySchemaUnavailableError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="PolicySchemaUnavailable",
        message=str(exc),
    )


async def provider_registry_exception_handler(
    request: Request,
    exc: ProviderRegistryError,
) -> JSONResponse:
    """
    Handle provider registry failures.
    """

    return _error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="provider_registry_error",
        message=str(exc),
    )


async def authentication_error_handler(
    request: Request,
    exc: AuthenticationError,
) -> JSONResponse:
    """
    Handle JWT authentication failures.
    """

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "error": {
                "code": exc.code,
                "message": str(exc),
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def value_error_exception_handler(
    request: Request,
    exc: ValueError,
) -> JSONResponse:
    """
    Handle invalid values raised by dependency or service layers.
    """

    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="value_error",
        message=str(exc),
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Handle unexpected failures without exposing implementation details.
    """

    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_server_error",
        message="An unexpected error occurred.",
    )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )
