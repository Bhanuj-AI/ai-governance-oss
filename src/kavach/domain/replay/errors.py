from __future__ import annotations


class ReplayError(Exception):
    """Base class for structured Replay Management errors."""


class ReplayNotFound(ReplayError):
    pass


class ReplaySourceNotFound(ReplayError):
    pass


class ReplaySourceUnavailable(ReplayError):
    pass


class ReplayNotReplayable(ReplayError):
    pass


class ReplayInvalidMode(ReplayError):
    pass


class ReplayInvalidTransition(ReplayError):
    pass


class ReplayIdempotencyConflict(ReplayError):
    pass


class ReplayConflict(ReplayError):
    pass


class ReplayPersistenceFailed(ReplayError):
    pass


class ReplayUnauthorized(ReplayError):
    pass


class ReplayNotReady(ReplayError):
    pass


class ReplayAlreadySubmitted(ReplayError):
    pass


class ReplaySubmissionConflict(ReplayError):
    pass


class ReplayJobSubmissionFailed(ReplayError):
    pass


class ReplayAdapterNotFound(ReplayError):
    pass


class ReplayAdapterConfigurationInvalid(ReplayError):
    pass


class ReplayReconstructionFailed(ReplayError):
    pass


class ReplayExecutionFailed(ReplayError):
    pass


class ReplayExecutionPersistenceFailed(ReplayError):
    pass


class ReplayLineagePersistenceFailed(ReplayError):
    pass


class ReplayCancellationFailed(ReplayError):
    pass


class ReplayNotCancellable(ReplayError):
    pass


class ReplayExecutionIdentityConflict(ReplayError):
    pass


class ReplayEvaluationNotReady(ReplayError):
    pass


class ReplayEvaluationAlreadySubmitted(ReplayError):
    pass


class ReplayEvaluationSubmissionFailed(ReplayError):
    pass


class ReplayEvaluationFailed(ReplayError):
    pass


class ReplayBaselineUnavailable(ReplayError):
    pass


class ReplayBaselineIncompatible(ReplayError):
    pass


class ReplayComparisonFailed(ReplayError):
    pass


class ReplayDriftAnalysisFailed(ReplayError):
    pass


class ReplayResultNotFound(ReplayError):
    pass


class ReplayResultConflict(ReplayError):
    pass


class ReplayResultPersistenceFailed(ReplayError):
    pass


class ReplayOntologySyncFailed(ReplayError):
    pass
