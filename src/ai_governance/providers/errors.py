class ProviderRegistryError(Exception):
    """
    Base error for provider registry and capability failures.
    """


class ProviderAlreadyRegisteredError(ProviderRegistryError):
    """
    Raised when a provider name is registered more than once.
    """


class ProviderNotFoundError(ProviderRegistryError):
    """
    Raised when a provider cannot be resolved by name.
    """


class ProviderCapabilityError(ProviderRegistryError):
    """
    Raised when a provider cannot satisfy requested capabilities.
    """


class ProviderContractError(ProviderRegistryError):
    """
    Raised when a provider does not satisfy AI Governance Control Plane's provider contract.
    """
