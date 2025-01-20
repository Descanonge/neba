import logging
from collections import abc

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from traitlets import Bool, Int

from data_assistant.config import Scheme, subscheme
from data_assistant.config.util import nest_dict

from ..conftest import todo
from ..scheme_generation import (
    GenericScheme,
    GenericSchemeInfo,
    GenericTraits,
    SchemeInfo,
    TwinSubscheme,
    scheme_st_to_cls,
    scheme_st_to_instance,
    scheme_st_to_instances,
    st_scheme_gen_single_trait,
)

log = logging.getLogger(__name__)


class SchemeTest:
    @pytest.fixture
    def info(self) -> GenericSchemeInfo:
        return GenericSchemeInfo()

    @pytest.fixture
    def scheme(self, info) -> GenericScheme:
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
            "normal.control",
            "a.control",
            "b.c.control",
        ]

    @todo
    def test_dynamic_definition_random(self):
        """Test that nested class defs will be found.

        Randomize the names and number of subschemes using hypothesis.recursive.
        """
        assert 0

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

        assert list(inst.keys()) == ["dynamic.a.control"]

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
        """Simple instanciation."""
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

    @todo
    def test_needed_value(self):
        """Check scheme that has a trait without default value."""
        # check exception at instanciation
        # check it makes it if value is given at instanciation
        assert 0

    @todo
    def test_twin_siblings(self):
        """Two subschemes on are from the same class."""
        assert 0

    @todo
    def test_twin_recursive(self):
        """Two schemes at different nesting level are from the same class."""
        assert 0


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

    def test_get(self, info, scheme):
        for key in info.keys_total:
            if key in info.traits_total:
                assert scheme.get(key) == info.default(key)
            else:
                assert isinstance(scheme.get(key), Scheme)

        assert scheme.get("wrong_key") is None
        assert scheme.get("sub_generic.wrong_key") is None
        assert scheme.get("empty_a.wrong_key") is None
        assert scheme.get("wrong_subscheme.wrong_key") is None
        assert scheme.get("wrong_subscheme.wrong_key", 2) == 2

    def test_contains(self, info, scheme):
        for key in info.keys_total:
            assert key in scheme

    def test_missing_keys(self, info, scheme):
        for key in ["missing_key", "missing_sub.key"]:
            assert key not in scheme
        with pytest.raises(KeyError):
            scheme[key]

    @todo
    def test_iter(self):
        assert 0

    def test_length(self, info: GenericSchemeInfo, scheme: GenericScheme):
        assert len(scheme) == len(info.traits_total)

    def test_eq_basic(self, info):
        scheme_a = GenericSchemeInfo.scheme()
        scheme_b = GenericSchemeInfo.scheme()

        assert scheme_a == scheme_b

        scheme_b["int"] += 2
        assert scheme_a != scheme_b

    @given(values=GenericSchemeInfo.values_strat())
    @settings(deadline=None)
    def test_eq_values(self, values):
        scheme_a = GenericSchemeInfo.scheme.instanciate_recursively(nest_dict(values))
        scheme_b = GenericSchemeInfo.scheme()

        for k, v in values.items():
            scheme_b[k] = v

        assert scheme_a == scheme_a
        assert scheme_a == scheme_b

    def test_keys(self, info, scheme):
        assert info.keys_total == list(scheme.keys(subschemes=True))
        assert info.keys_this_level == list(
            scheme.keys(subschemes=True, recursive=False)
        )
        assert info.traits_total == list(scheme.keys())
        assert info.traits_this_level == list(scheme.keys(recursive=False))

    def test_values(self, info, scheme):
        for k, v in zip(info.traits_total, scheme.values(), strict=True):
            assert info.default(k) == v

    def test_items(self, info, scheme):
        for ref, (k, v) in zip(info.traits_total, scheme.items(), strict=True):
            assert ref == k
            if ref in info.traits_total:
                assert info.default(k) == v
            else:
                assert isinstance(v, Scheme)


class TestMutableMappingInterface(SchemeTest):
    """Test the mutable mapping interface of Schemes.

    With some dictionnary functions as well.
    """

    def test_is_mutable_mapping(self, info: GenericSchemeInfo):
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

    def test_setdefault(self, scheme: GenericScheme):
        # set with trait existing
        assert scheme.setdefault("int") == 0

        # set with new trait
        assert scheme.setdefault("new_int", Int(0)) == 0
        assert scheme["new_int"] == 0
        assert scheme.setdefault("sub_generic.new_int", Int(0), value=2) == 2
        assert scheme["sub_generic.new_int"] == 2

        # set with new trait, argument trait not passed
        with pytest.raises(TypeError):
            scheme.setdefault("new_int_wrong")

    def test_pop(self, scheme):
        with pytest.raises(TypeError):
            scheme.pop("anything")

    def test_popitem(self, scheme):
        with pytest.raises(TypeError):
            scheme.pop("anything")

    def test_clear(self, scheme):
        with pytest.raises(TypeError):
            scheme.pop("anything")

    @given(values=GenericSchemeInfo.values_strat())
    def test_reset(self, values: dict):
        info = GenericSchemeInfo
        scheme = info.scheme()
        scheme.update(values)
        scheme.reset()
        for key in values:
            assert scheme[key] == info.default(key)

    def test_add_trait(self, scheme: GenericScheme):
        # simple
        scheme.add_trait("new_trait", Int(1))
        assert "new_trait" in scheme
        assert "new_trait" in scheme.trait_names()
        assert isinstance(scheme.traits()["new_trait"], Int)
        assert scheme["new_trait"] == 1
        scheme["new_trait"] = 3
        assert scheme.new_trait == 3  # type: ignore[attr-defined]
        assert scheme["new_trait"] == 3

        # already in use
        with pytest.raises(KeyError):
            scheme.add_trait("dict_any", Int(1))

        # recursive (no adding)
        scheme.add_trait("deep_sub.sub_generic_deep.new_trait", Int(10))
        assert "deep_sub.sub_generic_deep.new_trait" in scheme
        assert "new_trait" in scheme.deep_sub.sub_generic_deep.trait_names()
        assert isinstance(scheme.deep_sub.sub_generic_deep.traits()["new_trait"], Int)
        assert scheme["deep_sub.sub_generic_deep.new_trait"] == 10
        scheme["deep_sub.sub_generic_deep.new_trait"] = 3
        assert scheme.deep_sub.sub_generic_deep.new_trait == 3  # type: ignore[attr-defined]
        assert scheme["deep_sub.sub_generic_deep.new_trait"] == 3

        # recursive (adding)
        scheme.add_trait("new_scheme1.new_scheme2.new_trait", Int(20))
        assert "new_scheme1.new_scheme2.new_trait" in scheme
        assert "new_trait" in scheme.new_scheme1.new_scheme2.trait_names()  # type: ignore[attr-defined]
        assert isinstance(scheme.new_scheme1.new_scheme2.traits()["new_trait"], Int)  # type: ignore[attr-defined]
        assert scheme["new_scheme1.new_scheme2.new_trait"] == 20
        scheme["new_scheme1.new_scheme2.new_trait"] = 3
        assert scheme.new_scheme1.new_scheme2.new_trait == 3  # type: ignore[attr-defined]
        assert scheme["new_scheme1.new_scheme2.new_trait"] == 3

        # recursive (not allowed)
        with pytest.raises(KeyError):
            scheme.add_trait(
                "new_scheme3.new_scheme4.new_trait", Int(1), allow_recursive=False
            )

    @given(values=GenericSchemeInfo.values_strat())
    def test_update_base(self, values):
        info = GenericSchemeInfo
        scheme = info.scheme()
        scheme.update(values)

        for key in info.traits_total:
            if key in values:
                assert scheme[key] == values[key]
            else:
                assert scheme[key] == info.default(key)

    @todo
    def test_update_add_traits(self):
        assert 0

    @todo
    def test_update_wrong(self):
        # refuse permission to add traits
        # wrong inputs to add a trait
        assert 0

    @todo
    def test_twin_siblings(self):
        """Two subschemes are from the same class."""
        # check changing one does not affect the other. On mutable and non-mutable
        # traits.
        assert 0


class TestTraitListing(SchemeTest):
    """Test the trait listing abilities.

    To filter out some traits, select some, list all recursively, etc.
    """

    @given(
        keys=st.lists(
            st.sampled_from(GenericSchemeInfo.keys_total), max_size=12, unique=True
        )
    )
    def test_select(self, keys: list[str]):
        # We only test flattened, we assume nest_dict() works and is tested
        scheme = GenericScheme()
        out = scheme.select(*keys, flatten=True)
        assert keys == list(out.keys())

    @todo
    def test_subscheme_recursive(self):
        assert 0

    @todo
    def test_class_traits_recursive(self):
        assert 0

    @todo
    def test_traits_recursive(self):
        assert 0

    @todo
    def test_default_recursive(self):
        assert 0

    @todo
    def test_values_recursive(self):
        assert 0

    @todo
    def test_value_from_func_signature(self):
        assert 0


class TestRemap:
    @todo
    def test_remap(self):
        """Test the remap function.

        Ensure all keys are visited (but no unexepected ones), that their path is correct.
        Ensure the modifications are kept, without side effect.
        """
        assert 0

    @todo
    def test_remap_twins(self):
        """Test the remap function when some subschemes are the same class.

        Make sure there is no unintended consequences.
        """
        assert 0


class TestResolveKey(SchemeTest):
    """Test key resolution."""

    def test_resolve_class_key(self):
        keys = GenericScheme.resolve_class_key("GenericScheme.bool")
        assert keys == ["bool"]

        keys = GenericScheme.resolve_class_key("GenericTraits.bool")
        assert keys == ["sub_generic.bool", "deep_sub.sub_generic_deep.bool"]

        keys = GenericScheme.resolve_class_key("TwinSubscheme.int")
        assert keys == ["twin_a.int", "twin_b.int", "sub_twin.twin_c.int"]

    def test_resolve_key(self):
        key, scheme_cls, trait = GenericScheme.resolve_key("bool")
        assert key == "bool"
        assert issubclass(scheme_cls, GenericScheme)
        assert isinstance(trait, Bool)

        key, scheme_cls, trait = GenericScheme.resolve_key("sub_generic.int")
        assert key == "sub_generic.int"
        assert issubclass(scheme_cls, GenericTraits)
        assert isinstance(trait, Int)

        key, scheme_cls, trait = GenericScheme.resolve_key("twin_a.int")
        assert key == "twin_a.int"
        assert issubclass(scheme_cls, TwinSubscheme)
        assert isinstance(trait, Int)

        # TODO: test alias

    @todo
    def test_wrong_keys(self):
        # missing subscheme
        # missing trait
        # missing trait in empty subscheme
        # nested class key
        assert 0


@todo
def test_merge_configs():
    """Test merge two different configuration dicts."""
    assert 0


class TestAutoGeneratedScheme:
    @given(cls=scheme_st_to_cls(st_scheme_gen_single_trait()))
    def test_default(self, cls: type[Scheme]):
        cls()

    @given(scheme=scheme_st_to_instance(st_scheme_gen_single_trait()))
    def test_instance(self, scheme: Scheme):
        print(repr(scheme))

    @given(schemes=scheme_st_to_instances(st_scheme_gen_single_trait(), n=2))
    def test_update(self, schemes: tuple[Scheme, ...]):
        schemeA, schemeB = schemes
        valA = schemeA.values_recursive(flatten=True)
        valB = schemeB.values_recursive(flatten=True)
        schemeA.update(schemeB)
        valA.update(valB)
        assert schemeA.values_recursive(flatten=True) == valA
