import logging

from hypothesis import given
from util import st_scheme_cls, st_scheme_instance, st_scheme_instances

from data_assistant.config import Scheme

log = logging.getLogger(__name__)


@given(cls=st_scheme_cls())
def test_default(cls: type[Scheme]):
    cls()


@given(scheme=st_scheme_instance())
def test_instance(scheme: Scheme):
    print(scheme)


@given(schemes=st_scheme_instances(2))
def test_update(schemes: tuple[Scheme, ...]):
    schemeA, schemeB = schemes
    valA = schemeA.values_recursive(flatten=True)
    valB = schemeB.values_recursive(flatten=True)
    schemeA.update(schemeB)
    valA.update(valB)
    assert schemeA.values_recursive(flatten=True) == valA
