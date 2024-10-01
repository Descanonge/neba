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


class TestDefinition:
    """Test defining schemes.

    Especially metaclass stuff.
    """

    def test_dynamic_definition(self):
        """Test that nested class defs will be found.

        And only those. Make sure name must follow rules.
        """
        pass

    def test_dynamic_definition_random(self):
        """Test that nested class defs will be found.

        Randomize the names and number of subschemes using hypothesis.recursive.
        """
        pass

    def test_dynamic_definition_disabled(self):
        """Test that disabling dynamic def works.

        And on the correct classes only (no unintented side-effects).
        """
        pass

    def test_wrong_alias(self):
        """Make sure we detect wrong aliases."""
        pass


class TestInstanciation:
    """Test instanciation of Schemes.

    Make sure the recursive config is passed correctly.
    """

    # What about weird traits, like hidden traits ? "_mytrait"

    def test_simple(self):
        """Simple instanciation (no scheme)."""
        pass

    def test_recursive(self):
        """Recursive instanciation (with subscheme)."""
        pass

    def test_wrong(self):
        # subscheme missing: will be okay
        # trait that does not exist: raise
        # value is not valid: raise from traitlets
        pass

    def test_needed_value(self):
        """Check scheme that has a trait without default value."""
        # check exception at instanciation
        # check it makes it if value is given at instanciation
        pass

    def test_twin_siblings(self):
        """Two subschemes on are from the same class."""
        pass

    def test_twin_recursive(self):
        """Two schemes at different nesting level are from the same class."""
        pass

class TestMappingInterface:
    """Test the Mapping interface of Schemes."""

    def test_is_mapping(self):
        # assert isinstance()
        # assert issubclass()
        pass

    def test_getitem(self):
        pass

    def test_get(self):
        pass

    def test_contains(self):
        pass

    def test_iter(self):
        pass

    def test_length(self):
        pass

    def test_eq(self):
        pass

    def test_keys(self):
        pass

    def test_values(self):
        pass

    def test_items(self):
        pass


class TestMutableMappingInterface:
    """Test the mutable mapping interface of Schemes.

    With some dictionnary functions as well.
    """

    def test_setitem(self):
        pass

    def test_setdefault(self):
        pass

    def test_pop(self):
        pass

    def test_popitem(self):
        pass

    def test_clear(self):
        pass

    def test_reset(self):
        pass

    def test_update(self):
        pass

    def test_add_trait(self):
        pass

class TestTraitListing:
    """Test the trait listing abilities.

    To filter out some traits, select some, list all recursively, etc.
    """

    def test_is_mutable_mapping(self):
        # assert isinstance()
        # assert issubclass()
        pass

    def test_select(self):
        pass

    def test_subscheme_recursive(self):
        pass

    def test_class_traits_recursive(self):
        pass

    def test_traits_recursive(self):
        pass

    def test_default_recursive(self):
        pass

    def test_values_recursive(self):
        pass

    def test_value_from_func_signature(self):
        pass


class TestRemap:
    def test_remap(self):
        """Test the remap function.

        Ensure all keys are visited (but no unexepected ones), that their path is correct.
        Ensure the modifications are kept, without side effect.
        """
        pass

    def test_remap_twins(self):
        """Test the remap function when some subschemes are the same class.

        Make sure there is no unintended consequences.
        """
        pass



class TestResolveKey:
    """Test key resolution."""

    def test_resolve_class_key(self):
        pass

    def test_class_resolve_key(self):
        pass

    def test_resolve_key(self):
        pass

    def test_wrong_keys(self):
        # missing subscheme
        # missing trait
        # nested class key
        pass

def test_merge_configs():
    """Test merge two different configuration dicts."""
    pass


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
