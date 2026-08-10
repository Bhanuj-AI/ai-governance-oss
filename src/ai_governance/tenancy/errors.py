class TenancyError(Exception):
    pass


class OrganizationNotFound(TenancyError):
    pass


class OrganizationSlugConflict(TenancyError):
    pass


class OrganizationInactive(TenancyError):
    pass


class ProjectNotFound(TenancyError):
    pass


class ProjectSlugConflict(TenancyError):
    pass


class ProjectInactive(TenancyError):
    pass


class MembershipNotFound(TenancyError):
    pass


class MembershipConflict(TenancyError):
    pass


class RoleAssignmentNotFound(TenancyError):
    pass


class RoleAssignmentConflict(TenancyError):
    pass


class TenantContextMissing(TenancyError):
    pass


class TenantContextInvalid(TenancyError):
    pass


class TenantScopeMismatch(TenancyError):
    pass


class LastOrganizationAdministrator(TenancyError):
    pass


class AuthorizationDenied(TenancyError):
    def __init__(self, decision: object) -> None:
        self.decision = decision
        super().__init__("Actor is not authorized for this operation")
