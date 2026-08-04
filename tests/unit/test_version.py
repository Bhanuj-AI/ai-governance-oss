from importlib.metadata import version

from kavach import __version__


def test_package_version_comes_from_distribution_metadata() -> None:
    assert __version__ == version("kavach")
