import logging

from hypothesis import given

from data_assistant.config import Scheme

from ..scheme_generation import (
    scheme_st_to_cls,
    scheme_st_to_instance,
    scheme_st_to_instances,
    st_scheme_gen_single_trait,
)

log = logging.getLogger(__name__)


# gen = SchemeGenerator("test", dict(a=BoolGen(), b=FloatGen(), c=ListGen(BoolGen())))


@given(cls=scheme_st_to_cls(st_scheme_gen_single_trait()))
def test_default(cls: type[Scheme]):
    cls()


@given(scheme=scheme_st_to_instance(st_scheme_gen_single_trait()))
def test_instance(scheme: Scheme):
    print(repr(scheme))


@given(schemes=scheme_st_to_instances(st_scheme_gen_single_trait(), n=2))
def test_update(schemes: tuple[Scheme, ...]):
    schemeA, schemeB = schemes
    valA = schemeA.values_recursive(flatten=True)
    valB = schemeB.values_recursive(flatten=True)
    schemeA.update(schemeB)
    valA.update(valB)
    assert schemeA.values_recursive(flatten=True) == valA
