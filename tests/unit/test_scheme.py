import logging

from hypothesis import given
from util import (
    BoolGen,
    FloatGen,
    SchemeGenerator,
    st_scheme_cls,
    st_scheme_instance,
    st_scheme_instances,
)

from data_assistant.config import Scheme

log = logging.getLogger(__name__)


gen = SchemeGenerator(
    "test", dict(a=BoolGen(has_default=True), b=FloatGen(has_default=True))
)


@given(cls=st_scheme_cls(gen))
def test_default(cls: type[Scheme]):
    cls()


@given(scheme=st_scheme_instance(gen))
def test_instance(scheme: Scheme):
    print(repr(scheme))


@given(schemes=st_scheme_instances(gen, 2))
def test_update(schemes: tuple[Scheme, ...]):
    schemeA, schemeB = schemes
    valA = schemeA.values_recursive(flatten=True)
    valB = schemeB.values_recursive(flatten=True)
    schemeA.update(schemeB)
    valA.update(valB)
    assert schemeA.values_recursive(flatten=True) == valA
