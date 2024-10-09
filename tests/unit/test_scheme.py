import logging
from collections import abc

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings
from traitlets import Int

from data_assistant.config import Scheme, subscheme
from data_assistant.config.util import nest_dict

from ..scheme_generation import (
    GenericSchemeInfo,
    SchemeInfo,
    scheme_st_to_cls,
    scheme_st_to_instance,
    scheme_st_to_instances,
    st_scheme_gen_single_trait,
)

log = logging.getLogger(__name__)


class SchemeTest:
    @pytest.fixture
    def info(self) -> SchemeInfo:
        return GenericSchemeInfo()

    @pytest.fixture
    def scheme(self, info) -> Scheme:
        return info.scheme()


class TestDefinition(SchemeTest):
    """Test defining schemes.

    Especially metaclass stuff.
    """

    def test_dynamic_definition(self):
        """Test that nested class defs will be found.

        And only those. Make sure name must follow rules.
        """

        class NormalSubscheme(Scheme):
            control = Int(0)

        class S(Scheme):
            normal = subscheme(NormalSubscheme)

            class a(Scheme):
                control = Int(0)

            class b(Scheme):
                class c(Scheme):
                    control = Int(0)

        cls_a = S._aSchemeDef
        cls_b = S._bSchemeDef
        cls_c = S._bSchemeDef._cSchemeDef

        assert issubclass(S._subschemes["a"], cls_a)
        assert issubclass(S._subschemes["b"], cls_b)
        assert issubclass(S._subschemes["b"]._subschemes["c"], cls_c)
        assert issubclass(S._subschemes["normal"], NormalSubscheme)

        inst = S()
        assert isinstance(inst.a, cls_a)
        assert isinstance(inst.b, cls_b)
        assert isinstance(inst.b.c, cls_c)
        assert isinstance(inst.normal, NormalSubscheme)

        assert isinstance(inst["a"], cls_a)
        assert isinstance(inst["b"], cls_b)
        assert isinstance(inst["b.c"], cls_c)
        assert isinstance(inst["normal"], NormalSubscheme)

        assert list(inst.keys()) == [
            "normal",
            "normal.control",
            "a",
            "a.control",
            "b",
            "b.c",
            "b.c.control",
        ]

    def test_dynamic_definition_random(self):
        """Test that nested class defs will be found.

        Randomize the names and number of subschemes using hypothesis.recursive.
        """
        pass

    def test_dynamic_definition_disabled(self):
        """Test that disabling dynamic def works.

        And on the correct classes only (no unintented side-effects).
        """

        class Dynamic(Scheme):
            class a(Scheme):
                control = Int(0)

        class Static(Scheme):
            _dynamic_subschemes = False

            class a(Scheme):
                control = Int(0)

            dynamic = subscheme(Dynamic)

        assert "a" not in Static._subschemes
        assert "dynamic" in Static._subschemes

        inst = Static()
        assert isinstance(inst.dynamic, Dynamic)
        assert isinstance(inst.a, type)

        assert list(inst.keys()) == ["dynamic", "dynamic.a", "dynamic.a.control"]

    def test_traits_tagged(self, info, scheme):
        """Test that trait are automatically tagged configurable."""

        def test_tagged_scheme(info, scheme):
            for key in info.traits_this_level:
                trait = scheme.traits()[key]
                assert trait.metadata["config"] is True
                assert trait.metadata.get("subscheme", None) is None

            for name, sub_info in info.subschemes.items():
                trait = scheme.traits()[name]
                assert trait.metadata["config"] is False
                assert trait.metadata["subscheme"] is True
                test_tagged_scheme(sub_info, scheme[name])

        test_tagged_scheme(info, scheme)

    def test_traits_tag_overwrite(self):
        """Test that traits forcefully specified as not configurable are kept that way."""

        class S(Scheme):
            control = Int(0)
            not_config = Int(0).tag(config=False)

        assert S.class_trait_names(config=True) == ["control"]
        assert S.class_trait_names(config=False) == ["not_config"]

    @pytest.mark.parametrize(
        "alias",
        [
            "very_wrong_alias",
            "very.wrong.alias",
            "list_int",
            "sub_generic.very_wrong_alias",
            "sub_generic.very.wrong.alias",
            "sub_generic.dict_any",
        ],
    )
    def test_wrong_alias(self, alias, scheme):
        """Make sure we detect wrong aliases."""
        with pytest.raises(KeyError):

            class Subclass(Scheme):
                aliases = {"short": "alias"}


class TestInstanciation(SchemeTest):
    """Test instanciation of Schemes.

    Make sure the recursive config is passed correctly.

    There is no test for 'config correctness'. The check of trait existence is done
    when resolving configs. And value-checking is done by traitlets so we don't check
    for that.
    """

    # What about weird traits, like hidden traits ? "_mytrait"

    def test_simple(self, info: SchemeInfo):
        """Simple instanciation (no scheme)."""
        _ = Scheme()
        scheme = info.scheme()

        def test_subscheme_class(info, scheme):
            for name, sub_info in info.subschemes.items():
                assert issubclass(scheme._subschemes[name], sub_info.scheme)
                assert isinstance(scheme[name], sub_info.scheme)
                test_subscheme_class(sub_info, scheme[name])

        test_subscheme_class(info, scheme)

    @given(values=GenericSchemeInfo.values_strat())
    def test_recursive(self, values):
        """Recursive instanciation (with subscheme)."""
        config = nest_dict(values)
        info = GenericSchemeInfo
        s = info.scheme.instanciate_recursively(config)
        for key in info.traits_total:
            if key in values:
                assert s[key] == values[key]
            else:
                assert s[key] == info.default(key)

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


# Do it for default values and changed values ?
class TestMappingInterface(SchemeTest):
    """Test the Mapping interface of Schemes."""

    def test_is_mapping(self, info):
        assert issubclass(Scheme, abc.Mapping)
        assert isinstance(Scheme(), abc.Mapping)

        assert issubclass(info.scheme, abc.Mapping)
        assert isinstance(info.scheme(), abc.Mapping)

    def test_getitem(self, info, scheme):
        for key in info.keys_total:
            if key in info.traits_total:
                assert scheme[key] == info.default(key)
            else:
                assert isinstance(scheme[key], Scheme)

    def test_get(self):
        pass

    def test_contains(self, info, scheme):
        for key in info.keys_total:
            assert key in scheme

    def test_missing_keys(self, info, scheme):
        for key in ["missing_key", "missing_sub.key"]:
            assert key not in scheme
        with pytest.raises(KeyError):
            scheme[key]

    def test_iter(self):
        pass

    def test_length(self, info, scheme):
        assert len(scheme) == len(info.keys_total)

    def test_eq(self):
        pass

    def test_keys(self, info, scheme):
        assert info.keys_total == list(scheme.keys())
        assert info.keys_this_level == list(scheme.keys(recursive=False))
        assert info.traits_total == list(scheme.keys(subschemes=False))
        assert info.traits_this_level == list(
            scheme.keys(subschemes=False, recursive=False)
        )

    def test_values(self):
        pass

    def test_items(self):
        pass


class TestMutableMappingInterface(SchemeTest):
    """Test the mutable mapping interface of Schemes.

    With some dictionnary functions as well.
    """

    def test_is_mutable_mapping(self, info):
        assert issubclass(Scheme, abc.MutableMapping)
        assert isinstance(Scheme(), abc.MutableMapping)

        assert issubclass(info.scheme, abc.MutableMapping)
        assert isinstance(info.scheme(), abc.MutableMapping)

    @given(values=GenericSchemeInfo.values_strat())
    def test_set(self, values):
        """Test __set__ with random values.

        Random keys are selected and appropriate values drawn as well. We check that set
        keys are correctly changed, and that no other keys than those selected were
        changed, to make sure we have no side effect (especially in twin schemes). Which
        only works for our generic scheme that has no observe events or stuff like that.
        """
        info = GenericSchemeInfo
        scheme = info.scheme()

        for key, val in values.items():
            scheme[key] = val

        for key in info.traits_total:
            if key in values:
                assert scheme[key] == values[key]
            else:
                assert scheme[key] == info.default(key)

    def test_setdefault(self):
        pass

    def test_pop(self, scheme):
        with pytest.raises(TypeError):
            scheme.pop("anything")

    def test_popitem(self, scheme):
        with pytest.raises(TypeError):
            scheme.pop("anything")

    def test_clear(self, scheme):
        with pytest.raises(TypeError):
            scheme.pop("anything")

    def test_reset(self):
        pass

    def test_update(self):
        pass

    def test_add_trait(self):
        pass

    def test_twin_siblings(self):
        """Two subschemes on are from the same class."""
        pass

    def test_twin_recursive(self):
        """Two schemes at different nesting level are from the same class."""
        pass


class TestTraitListing(SchemeTest):
    """Test the trait listing abilities.

    To filter out some traits, select some, list all recursively, etc.
    """

    @given(
        keys=st.lists(
            st.sampled_from(GenericSchemeInfo.keys_total), max_size=12, unique=True
        )
    )
    def test_select(self, keys):
        # We only test flattened, we assume nest_dict() works and is tested
        scheme = GenericSchemeInfo.scheme()
        out = scheme.select(*keys, flatten=True)
        assert keys == list(out.keys())

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
