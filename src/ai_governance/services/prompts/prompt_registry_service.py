from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from difflib import unified_diff
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid4, uuid5

from ai_governance.domain.assets import AssetProvenance
from ai_governance.domain.prompts import (
    Prompt,
    PromptDiff,
    PromptStatus,
)
from ai_governance.events import EventPublisher, ResourceLifecycleEvent
from ai_governance.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from ai_governance.repositories.prompt_repository import PromptRepository
from ai_governance.tenancy.domain import TenantContext


class PromptNotFoundError(Exception):
    """
    Raised when a prompt registry operation references an unknown prompt.
    """


class PromptVersionConflictError(Exception):
    """
    Raised when a prompt name and version already exist in the registry.
    """


class PromptLifecycleError(Exception):
    """
    Raised when a prompt lifecycle transition is not allowed.
    """


class PromptRegistryService:
    """
    Application service for enterprise prompt governance.

    The registry owns prompt lifecycle rules: create, version, diff, activate,
    and archive. Repositories store prompt records; this service decides what
    state transitions are valid.
    """

    def __init__(
        self,
        prompt_repository: PromptRepository,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol
        | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._prompt_repository = prompt_repository
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ontology_event_publisher = ontology_event_publisher
        self._event_publisher = event_publisher

    def create_prompt(
        self,
        name: str,
        version: str,
        template: str,
        variables: Iterable[str],
        created_by: str,
        context: TenantContext,
    ) -> Prompt:
        """
        Register a new prompt version in DRAFT status.
        """

        self._ensure_version_available(
            name=name,
            version=version,
            context=context,
        )

        prompt = Prompt(
            prompt_id=self._id_generator(),
            name=name,
            version=version,
            template=template,
            variables=tuple(variables),
            created_at=self._clock(),
            created_by=created_by,
            status=PromptStatus.DRAFT,
            tenant_id=context.organization_id,
            organization_id=context.organization_id,
            project_id=self._project_id(context),
        )

        self._prompt_repository.save(prompt)
        self._publish_prompt_event("PromptVersionRegistered", prompt)

        return prompt

    def version_prompt(
        self,
        prompt_id: str,
        version: str,
        created_by: str,
        context: TenantContext,
        template: str | None = None,
        variables: Iterable[str] | None = None,
    ) -> Prompt:
        """
        Create a new DRAFT version from an existing prompt.

        If template or variables are omitted, the new version inherits them
        from the source prompt.
        """

        source = self._get_prompt(prompt_id, context)
        self._ensure_version_available(
            name=source.name,
            version=version,
            context=context,
        )

        prompt = Prompt(
            prompt_id=self._id_generator(),
            name=source.name,
            version=version,
            template=template if template is not None else source.template,
            variables=(
                tuple(variables)
                if variables is not None
                else source.variables
            ),
            created_at=self._clock(),
            created_by=created_by,
            status=PromptStatus.DRAFT,
            tenant_id=context.organization_id,
            organization_id=context.organization_id,
            project_id=self._project_id(context),
        )

        self._prompt_repository.save(prompt)
        self._publish_prompt_event("PromptVersionRegistered", prompt)

        return prompt

    def observe_prompt(
        self,
        *,
        name: str,
        version: str,
        source_system: str,
        source_reference: str | None,
        template: str | None,
        content_hash: str | None,
        variables: Iterable[str],
        observed_by: str,
        context: TenantContext,
    ) -> Prompt:
        """Record runtime evidence without claiming authorship of a prompt.

        The same observed identity is idempotent. A different payload for an
        existing logical version is rejected instead of silently overwriting a
        historical execution fact.
        """

        resolved_hash = content_hash
        if template is not None:
            resolved_hash = f"sha256:{sha256(template.encode()).hexdigest()}"
        if resolved_hash is None:
            raise ValueError("Observed prompts require content or content_hash.")

        existing = self._prompt_repository.find_by_name_and_version(
            name, version, context.organization_id, self._project_id(context)
        )
        if existing is not None:
            if (
                existing.provenance == AssetProvenance.OBSERVED
                and existing.source_system == source_system
                and existing.source_reference == source_reference
                and existing.content_hash == resolved_hash
            ):
                return existing
            raise PromptVersionConflictError(
                f"Prompt '{name}' version '{version}' is already recorded with different evidence."
            )

        identity = "|".join((context.organization_id, self._project_id(context), source_system, source_reference or "", name, version, resolved_hash))
        prompt = Prompt(
            prompt_id=str(uuid5(NAMESPACE_URL, f"ai-governance:observed-prompt:{identity}")),
            name=name,
            version=version,
            template=template,
            variables=tuple(variables),
            created_at=self._clock(),
            created_by=observed_by,
            status=PromptStatus.ACTIVE,
            provenance=AssetProvenance.OBSERVED,
            source_system=source_system,
            source_reference=source_reference,
            content_hash=resolved_hash,
            content_available=template is not None,
            tenant_id=context.organization_id,
            organization_id=context.organization_id,
            project_id=self._project_id(context),
        )
        self._prompt_repository.save(prompt)
        self._publish_prompt_event("PromptVersionObserved", prompt)
        return prompt

    def diff_prompts(
        self,
        baseline_prompt_id: str,
        candidate_prompt_id: str,
        context: TenantContext,
    ) -> PromptDiff:
        """
        Compare two prompt versions by template and variables.
        """

        baseline = self._get_prompt(baseline_prompt_id, context)
        candidate = self._get_prompt(candidate_prompt_id, context)

        baseline_variables = set(baseline.variables)
        candidate_variables = set(candidate.variables)

        return PromptDiff(
            baseline_prompt_id=baseline.prompt_id,
            candidate_prompt_id=candidate.prompt_id,
            template_changed=baseline.template != candidate.template,
            variables_added=tuple(
                sorted(candidate_variables - baseline_variables)
            ),
            variables_removed=tuple(
                sorted(baseline_variables - candidate_variables)
            ),
            unified_template_diff=tuple(
                unified_diff(
                    (baseline.template or "").splitlines(),
                    (candidate.template or "").splitlines(),
                    fromfile=f"{baseline.name}:{baseline.version}",
                    tofile=f"{candidate.name}:{candidate.version}",
                    lineterm="",
                )
            ),
        )

    def activate_prompt(
        self,
        prompt_id: str,
        context: TenantContext,
    ) -> Prompt:
        """
        Activate one prompt version and deprecate other active versions.
        """

        prompt = self._get_prompt(prompt_id, context)

        if prompt.status == PromptStatus.ARCHIVED:
            raise PromptLifecycleError(
                "Archived prompts cannot be activated."
            )

        for existing in self._prompt_repository.find_by_name(
            prompt.name, context.organization_id, self._project_id(context)
        ):
            if (
                existing.prompt_id != prompt.prompt_id
                and existing.status == PromptStatus.ACTIVE
            ):
                deprecated = replace(
                    existing,
                    status=PromptStatus.DEPRECATED,
                )
                self._prompt_repository.save(deprecated)
                self._publish_prompt_event(
                    "PromptVersionDeprecated",
                    deprecated,
                )

        activated = replace(
            prompt,
            status=PromptStatus.ACTIVE,
        )
        self._prompt_repository.save(activated)
        self._publish_prompt_event("PromptVersionActivated", activated)

        return activated

    def archive_prompt(
        self,
        prompt_id: str,
        context: TenantContext,
    ) -> Prompt:
        """
        Archive a prompt version so it is no longer deployable.
        """

        prompt = self._get_prompt(prompt_id, context)

        if prompt.status == PromptStatus.ARCHIVED:
            return prompt

        archived = replace(
            prompt,
            status=PromptStatus.ARCHIVED,
        )
        self._prompt_repository.save(archived)
        self._publish_prompt_event("PromptVersionArchived", archived)

        return archived

    def get_prompt(
        self,
        prompt_id: str,
        context: TenantContext,
    ) -> Prompt:
        """
        Return a prompt by ID.
        """

        return self._get_prompt(prompt_id, context)

    def list_prompts(self, context: TenantContext) -> list[Prompt]:
        """
        Return every prompt version in the registry.
        """

        return self._prompt_repository.find_all(
            context.organization_id, self._project_id(context)
        )

    def list_visible_prompts(self, context: TenantContext) -> list[Prompt]:
        """
        Return prompt versions visible through read-only discovery APIs.
        """

        return [
            prompt
            for prompt in self.list_prompts(context)
            if prompt.status != PromptStatus.ARCHIVED
        ]

    def list_prompt_versions(
        self,
        name: str,
        context: TenantContext,
    ) -> list[Prompt]:
        """
        Return non-archived versions for one logical prompt name.
        """

        prompts = [
            prompt
            for prompt in self._prompt_repository.find_by_name(
                name, context.organization_id, self._project_id(context)
            )
            if prompt.status != PromptStatus.ARCHIVED
        ]

        if not prompts:
            raise PromptNotFoundError(
                f"Prompt '{name}' does not exist."
            )

        return prompts

    def _get_prompt(
        self,
        prompt_id: str,
        context: TenantContext,
    ) -> Prompt:
        prompt = self._prompt_repository.find_by_id(
            prompt_id, context.organization_id, self._project_id(context)
        )

        if prompt is None:
            raise PromptNotFoundError(
                f"Prompt '{prompt_id}' does not exist."
            )

        return prompt

    def _ensure_version_available(
        self,
        name: str,
        version: str,
        context: TenantContext,
    ) -> None:
        if (
            self._prompt_repository.find_by_name_and_version(
                name=name,
                version=version,
                organization_id=context.organization_id,
                project_id=self._project_id(context),
            )
            is not None
        ):
            raise PromptVersionConflictError(
                f"Prompt '{name}' version '{version}' already exists."
            )

    @staticmethod
    def _project_id(context: TenantContext) -> str:
        if context.project_id is None:
            raise ValueError("Prompt registry operations require project scope.")
        return context.project_id

    def _publish_prompt_event(
        self,
        event_type: str,
        prompt: Prompt,
    ) -> None:
        if self._ontology_event_publisher is not None:
            self._ontology_event_publisher.publish_entity_event(
                event_type,
                entity_type="PromptVersion",
                entity_id=prompt.prompt_id,
                scope_identifier="prompt_registry",
                payload={
                    "prompt_id": prompt.prompt_id,
                    "name": prompt.name,
                    "version": prompt.version,
                    "status": prompt.status.value,
                    "provenance": prompt.provenance.value,
                    "source_system": prompt.source_system,
                },
            )
        if self._event_publisher is None:
            return
        state = {
            "PromptVersionRegistered": "registered",
            "PromptVersionObserved": "version.created",
            "PromptVersionArchived": "archived",
        }.get(event_type)
        if state is not None:
            import asyncio

            asyncio.run(
                self._event_publisher.publish(
                    ResourceLifecycleEvent(
                        tenant={
                            "tenant_id": prompt.tenant_id,
                            "organization_id": prompt.organization_id,
                            "project_id": prompt.project_id,
                        },
                        resource_kind="asset",
                        resource_id=prompt.prompt_id,
                        state=state,
                        payload={
                            "asset_type": "PromptVersion",
                            "version": prompt.version,
                            "status": prompt.status.value,
                        },
                    )
                )
            )
