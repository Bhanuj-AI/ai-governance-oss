from importlib.metadata import version

from ai_governance import __version__


def test_package_version_comes_from_distribution_metadata() -> None:
    assert __version__ == version("ai-governance")
