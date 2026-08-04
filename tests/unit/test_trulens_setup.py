from trulens.core import TruSession  # type: ignore


def test_trulens_session():

    session = TruSession()
    print(type(session))

    assert session is not None
