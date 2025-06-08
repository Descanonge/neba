import logging
from collections import abc

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from traitlets import Bool, Int

from data_assistant.config import Section, Subsection
from data_assistant.config.util import UnknownConfigKeyError

from ..conftest import todo
from ..generic_sections import (
    GenericConfig,
    GenericConfigInfo,
    GenericSection,
    SectionInfo,
    TwinSubsection,
)
from ..section_generation import (
    section_st_to_cls,
    section_st_to_instance,
    section_st_to_instances,
    st_section_gen_single_trait,
)

log = logging.getLogger(__name__)


class SectionTest:
    """Make available a config and information about it."""

    @pytest.fixture
    def info(self) -> GenericConfigInfo:
        return GenericConfigInfo()

    @pytest.fixture
    def section(self, info) -> GenericConfig:
        return info.section()


class TestDefinition(SectionTest):
    """Test defining sections.

    Especially metaclass stuff.
    """

    def test_dynamic_definition(self) -> None:
        """Test that nested class defs will be found.

        And only those. Make sure name must follow rules.
        """

        class NormalSubsection(Section):
            control = Int(0)

        class S(Section):
            normal = Subsection(NormalSubsection)

            class a(Section):
                control = Int(0)

            class b(Section):
                class c(Section):
                    control = Int(0)

        cls_a = S._aSectionDef
        cls_b = S._bSectionDef
        cls_c = S._bSectionDef._cSectionDef

        assert issubclass(S._subsections["a"], cls_a)
        assert issubclass(S._subsections["b"], cls_b)
        assert issubclass(S._subsections["b"]._subsections["c"], cls_c)
        assert issubclass(S._subsections["normal"], NormalSubsection)

        inst = S()
        assert isinstance(inst.a, cls_a)
        assert isinstance(inst.b, cls_b)
        assert isinstance(inst.b.c, cls_c)
        assert isinstance(inst.normal, NormalSubsection)

        assert isinstance(inst["a"], cls_a)
        assert isinstance(inst["b"], cls_b)
        assert isinstance(inst["b.c"], cls_c)
        assert isinstance(inst["normal"], NormalSubsection)

        assert list(inst.keys()) == [
            "normal.control",
            "a.control",
            "b.c.control",
        ]

    @todo
    def test_dynamic_definition_random(self):
        """Test that nested class defs will be found.

        Randomize the names and number of subsections using hypothesis.recursive.
        """
        assert 0

    def test_dynamic_definition_disabled(self):
        """Test that disabling dynamic def works.

        And on the correct classes only (no unintented side-effects).
        """

        class Dynamic(Section):
            class a(Section):
                control = Int(0)

        class Static(Section):
            _dynamic_subsections = False

            class a(Section):
                control = Int(0)

            dynamic = Subsection(Dynamic)

        assert "a" not in Static._subsections
        assert "dynamic" in Static._subsections

        inst = Static()
        assert isinstance(inst.dynamic, Dynamic)
        assert isinstance(inst.a, type)

        assert list(inst.keys()) == ["dynamic.a.control"]

    def test_traits_tagged(self, info: GenericConfigInfo, section: GenericConfig):
        """Test that trait are automatically tagged configurable."""

        def test_tagged_section(info: SectionInfo, section: Section):
            for key in info.traits_this_level:
                trait = section.traits()[key]
                assert trait.metadata["config"] is True

            for name, sub_info in info.subsections.items():
                test_tagged_section(sub_info, section[name])

        test_tagged_section(info, section)

    def test_traits_tag_overwrite(self):
        """Test that traits forcefully specified as not configurable are kept that way."""

        class S(Section):
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
    def test_wrong_alias(self, alias, section: GenericConfig):
        """Make sure we detect wrong aliases."""
        with pytest.raises(KeyError):

            class Subclass(Section):
                aliases = {"short": "alias"}


class TestInstantiation(SectionTest):
    """Test instantiation of Sections.

    Make sure the recursive config is passed correctly.

    There is no test for 'config correctness'. The check of trait existence is done
    when resolving configs. And value-checking is done by traitlets so we don't check
    for that.
    """

    # What about weird traits, like hidden traits ? "_mytrait"

    def test_basic(self):
        _ = Section()
        cls = type("Subclass", (Section,), {})
        _ = cls()

    def test_subsections(self, info: GenericConfigInfo, section: GenericConfig):
        def test_subsection_class(info, section):
            for name, sub_info in info.subsections.items():
                assert issubclass(section._subsections[name], sub_info.section)
                assert isinstance(section[name], sub_info.section)
                test_subsection_class(sub_info, section[name])

        test_subsection_class(info, section)

    @given(values=GenericConfigInfo.values_strat())
    def test_recursive(self, values: dict):
        """Recursive instantiation (with subsection)."""
        info = GenericConfigInfo
        s = info.section(values)
        for key in info.traits_total:
            if key in values:
                assert s[key] == values[key]
            else:
                assert s[key] == info.default(key)


# Do it for default values and changed values ?
class TestMappingInterface(SectionTest):
    """Test the Mapping interface of Sections."""

    def test_is_mapping(self, info: GenericConfigInfo):
        assert issubclass(Section, abc.Mapping)
        assert isinstance(Section(), abc.Mapping)

        assert issubclass(info.section, abc.Mapping)
        assert isinstance(info.section(), abc.Mapping)

    def test_getitem(self, info: GenericConfigInfo, section: GenericConfig):
        for key in info.keys_total:
            if key in info.traits_total:
                assert section[key] == info.default(key)
            else:
                assert isinstance(section[key], Section)

    def test_get(self, info: GenericConfigInfo, section: GenericConfig):
        for key in info.keys_total:
            if key in info.traits_total:
                assert section.get(key) == info.default(key)
            else:
                assert isinstance(section.get(key), Section)

        assert section.get("wrong_key") is None
        assert section.get("sub_generic.wrong_key") is None
        assert section.get("empty_a.wrong_key") is None
        assert section.get("wrong_subsection.wrong_key") is None
        assert section.get("wrong_subsection.wrong_key", 2) == 2

    def test_missing_keys(self, info: GenericConfigInfo, section: GenericConfig):
        for key in ["missing_key", "missing_sub.key"]:
            assert key not in section
        with pytest.raises(KeyError):
            section[key]

    def test_iter(self, info: GenericConfigInfo, section: GenericConfig):
        for ref, key in zip(info.traits_total, section, strict=True):
            assert ref == key

    def test_contains(self, info: GenericConfigInfo, section: GenericConfig):
        for key in info.keys_total:
            assert key in section

        assert "invalid" not in section
        assert "nested.invalid" not in section

    def test_length(self, info: GenericConfigInfo, section: GenericConfig):
        assert len(section) == len(info.traits_total)

    def test_eq_basic(self, info: GenericConfigInfo):
        section_a = GenericConfigInfo.section()
        section_b = GenericConfigInfo.section()

        assert section_a == section_b

        section_b["int"] += 2
        assert section_a != section_b

    @given(values=GenericConfigInfo.values_strat())
    @settings(deadline=None)
    def test_eq_values(self, values: dict):
        section_a = GenericConfigInfo.section(values)
        section_b = GenericConfigInfo.section()

        for k, v in values.items():
            section_b[k] = v

        assert section_a == section_a
        assert section_a == section_b

    def test_keys(self, info: GenericConfigInfo, section: GenericConfig):
        assert info.keys_total == list(section.keys(subsections=True))
        assert info.keys_this_level == list(
            section.keys(subsections=True, recursive=False)
        )
        assert info.traits_total == list(section.keys())
        assert info.traits_this_level == list(section.keys(recursive=False))

    def test_values(self, info: GenericConfigInfo, section: GenericConfig):
        for k, v in zip(info.traits_total, section.values(), strict=True):
            assert info.default(k) == v

    def test_items(self, info: GenericConfigInfo, section: GenericConfig):
        for ref, (k, v) in zip(info.traits_total, section.items(), strict=True):
            assert ref == k
            if ref in info.traits_total:
                assert info.default(k) == v
            else:
                assert isinstance(v, Section)


class TestMutableMappingInterface(SectionTest):
    """Test the mutable mapping interface of Sections.

    With some dictionnary functions as well.
    """

    def test_is_mutable_mapping(self, info: GenericConfigInfo):
        assert issubclass(Section, abc.MutableMapping)
        assert isinstance(Section(), abc.MutableMapping)

        assert issubclass(info.section, abc.MutableMapping)
        assert isinstance(info.section(), abc.MutableMapping)

    @given(values=GenericConfigInfo.values_strat())
    def test_set(self, values):
        """Test __set__ with random values.

        Random keys are selected and appropriate values drawn as well. We check that set
        keys are correctly changed, and that no other keys than those selected were
        changed, to make sure we have no side effect (especially in twin sections). Which
        only works for our generic section that has no observe events or stuff like that.
        """
        info = GenericConfigInfo
        section = info.section()

        for key, val in values.items():
            section[key] = val

        for key in info.traits_total:
            if key in values:
                assert section[key] == values[key]
            else:
                assert section[key] == info.default(key)

    def test_setdefault(self, section: GenericConfig):
        # set with trait existing
        assert section.setdefault("int") == 0

        # set with new trait
        assert section.setdefault("new_int", Int(0)) == 0
        assert section["new_int"] == 0
        assert section.setdefault("sub_generic.new_int", Int(0), value=2) == 2
        assert section["sub_generic.new_int"] == 2

        # set with new trait, argument trait not passed
        with pytest.raises(TypeError):
            section.setdefault("new_int_wrong")

    def test_pop(self, section):
        with pytest.raises(TypeError):
            section.pop("anything")

    def test_popitem(self, section):
        with pytest.raises(TypeError):
            section.pop("anything")

    def test_clear(self, section):
        with pytest.raises(TypeError):
            section.pop("anything")

    @given(values=GenericConfigInfo.values_strat())
    def test_reset(self, values: dict):
        info = GenericConfigInfo
        section = info.section()
        section.update(values)
        section.reset()
        for key in values:
            assert section[key] == info.default(key)

    def test_twin_siblings(self, section: GenericConfig):
        """Two subsections on are from the same class."""
        # non-mutable trait
        section.twin_a.int = 0
        section.twin_b.int = 0
        section.twin_a.int = 1
        assert section.twin_b.int == 0

        # mutable trait
        section.twin_a.list_int = [0]
        section.twin_b.list_int = [0]
        section.twin_a.list_int.append(1)
        assert section.twin_b.list_int == [0]

    def test_twin_recursive(self, section: GenericConfig):
        """Two sections at different nesting level are from the same class."""
        # non-mutable trait
        section.twin_a.int = 0
        section.sub_twin.twin_c.int = 0
        section.twin_a.int = 1
        assert section.sub_twin.twin_c.int == 0

        # mutable trait
        section.twin_a.list_int = [0]
        section.sub_twin.twin_c.list_int = [0]
        section.twin_a.list_int.append(1)
        assert section.sub_twin.twin_c.list_int == [0]

    def test_add_trait(self, section: GenericConfig):
        # simple
        section.add_trait("new_trait", Int(1))
        assert "new_trait" in section
        assert "new_trait" in section.trait_names()
        assert isinstance(section.traits()["new_trait"], Int)
        assert section["new_trait"] == 1
        section["new_trait"] = 3
        assert section.new_trait == 3  # type: ignore[attr-defined]
        assert section["new_trait"] == 3

        # already in use
        with pytest.raises(KeyError):
            section.add_trait("dict_any", Int(1))

        # recursive (not adding sections)
        section.add_trait("deep_sub.new_trait", Int(2))
        assert "deep_sub.new_trait" in section

        section.add_trait("deep_sub.sub_generic_deep.new_trait", Int(10))
        assert "deep_sub.sub_generic_deep.new_trait" in section
        assert "new_trait" in section.deep_sub.sub_generic_deep.trait_names()
        assert isinstance(section.deep_sub.sub_generic_deep.traits()["new_trait"], Int)
        assert section["deep_sub.sub_generic_deep.new_trait"] == 10
        section["deep_sub.sub_generic_deep.new_trait"] = 3
        assert section.deep_sub.sub_generic_deep.new_trait == 3  # type: ignore[attr-defined]
        assert section["deep_sub.sub_generic_deep.new_trait"] == 3

        # recursive (adding)
        section.add_trait("new_section1.new_section2.new_trait", Int(20))
        assert "new_section1.new_section2.new_trait" in section
        assert "new_trait" in section.new_section1.new_section2.trait_names()  # type: ignore[attr-defined]
        assert isinstance(section.new_section1.new_section2.traits()["new_trait"], Int)  # type: ignore[attr-defined]
        assert section["new_section1.new_section2.new_trait"] == 20
        section["new_section1.new_section2.new_trait"] = 3
        assert section.new_section1.new_section2.new_trait == 3  # type: ignore[attr-defined]
        assert section["new_section1.new_section2.new_trait"] == 3

        # recursive (not allowed)
        with pytest.raises(KeyError):
            section.add_trait(
                "new_section3.new_section4.new_trait", Int(1), allow_recursive=False
            )

    @given(values=GenericConfigInfo.values_strat())
    def test_update_base(self, values):
        info = GenericConfigInfo
        section = info.section()
        section.update(values)

        for key in info.traits_total:
            if key in values:
                assert section[key] == values[key]
            else:
                assert section[key] == info.default(key)

    def test_update_add_traits(self, section: GenericConfig):
        section.update(
            {"new_trait": Int(10)},
            allow_new=True,
        )
        assert section["new_trait"] == 10
        section.update(
            {"sub_generic.new_trait": Int(20), "new_section.new_trait": Int(30)},
            allow_new=True,
        )
        assert section["sub_generic.new_trait"] == 20
        assert section["new_section.new_trait"] == 30

    def test_update_wrong(self, section: GenericConfig):
        with pytest.raises(RuntimeError):
            section.update({"new_trait": Int(10)})
        with pytest.raises(KeyError):
            section.update({"new_trait": Int(10)}, raise_on_miss=True)
        with pytest.raises(TypeError):
            section.update({"new_trait": 10}, allow_new=True)


class TestTraitListing(SectionTest):
    """Test the trait listing abilities that use remap.

    To filter out some traits, select some, list all recursively, etc.
    """

    @given(
        keys=st.lists(
            st.sampled_from(GenericConfigInfo.keys_total), max_size=12, unique=True
        )
    )
    def test_select(self, keys: list[str]):
        # We only test flattened, we assume nest_dict() works and is tested
        section = GenericConfig()
        out = section.select(*keys)
        assert keys == list(out.keys())

    def test_metadata_select(self):
        class MetaSection(Section):
            no_config = Int(0).tag(config=False)
            no_config_tagged = Int(0).tag(config=False, tagged=True)
            normal = Int(0)
            normal_tagged = Int(0).tag(tagged=True)

            class sub(Section):
                no_config = Int(0).tag(config=False)
                no_config_tagged = Int(0).tag(config=False, tagged=True)
                normal = Int(0)
                normal_tagged = Int(0).tag(tagged=True)

        sec = MetaSection()
        keys = list(sec.trait_names())
        assert keys == ["no_config", "no_config_tagged", "normal", "normal_tagged"]
        keys = list(sec.traits_recursive(config=True).keys())
        assert keys == ["normal", "normal_tagged", "sub.normal", "sub.normal_tagged"]
        keys = list(sec.traits_recursive(tagged=True).keys())
        assert keys == [
            "no_config_tagged",
            "normal_tagged",
            "sub.no_config_tagged",
            "sub.normal_tagged",
        ]
        keys = list(sec.traits_recursive(config=True, tagged=None).keys())
        assert keys == ["normal", "sub.normal"]

    def test_default_recursive(self, info: GenericConfigInfo, section: GenericConfig):
        assert list(section.defaults_recursive().keys()) == info.traits_total
        for k, v in section.defaults_recursive().items():
            assert info.default(k) == v

    @todo
    def test_value_from_func_signature(self):
        assert 0


class TestResolveKey(SectionTest):
    """Test key resolution."""

    def test_resolve_key(self):
        key, section_cls, trait = GenericConfig.resolve_key("bool")
        assert key == "bool"
        assert issubclass(section_cls, GenericConfig)
        assert isinstance(trait, Bool)

        key, section_cls, trait = GenericConfig.resolve_key("sub_generic.int")
        assert key == "sub_generic.int"
        assert issubclass(section_cls, GenericSection)
        assert isinstance(trait, Int)

        key, section_cls, trait = GenericConfig.resolve_key("twin_a.int")
        assert key == "twin_a.int"
        assert issubclass(section_cls, TwinSubsection)
        assert isinstance(trait, Int)

    @todo
    def test_aliases(self):
        assert 0

    def test_wrong_keys(self, info: GenericConfigInfo):
        def assert_bad_key(key: str):
            with pytest.raises(UnknownConfigKeyError):
                cls.resolve_key(key)

        cls = info.section
        assert_bad_key("invalid_trait")
        assert_bad_key("invalid_sub.trait_name")
        assert_bad_key("sub_generic.invalid_trait")
        assert_bad_key("empty_b.empty_c.invalid_trait")


class TestNestFlatten(SectionTest):
    single_level_flat = dict(int=0, bool=1, str=2)

    two_levels_flat = {
        "int": 0,
        "bool": 1,
        "sub_generic.int": 10,
        "sub_generic.bool": 11,
        "sub_generic.str": 12,
        "sub_generic.enum_int": 13,
        "twin_a.int": 20,
        "twin_a.list_int": 21,
    }
    two_levels_nested = dict(
        int=0,
        bool=1,
        sub_generic=dict(int=10, bool=11, str=12, enum_int=13),
        twin_a=dict(int=20, list_int=21),
    )

    deep_flat = {
        "deep_sub.sub_generic_deep.int": 0,
        "deep_sub.sub_generic_deep.bool": 1,
    }
    deep_nested = {"deep_sub": {"sub_generic_deep": {"int": 0, "bool": 1}}}

    def test_nest_dict(self, section: GenericConfig):
        assert section.nest_dict({}) == {}
        assert section.nest_dict(self.single_level_flat) == self.single_level_flat
        assert section.nest_dict(self.two_levels_flat) == self.two_levels_nested
        assert section.nest_dict(self.deep_flat) == self.deep_nested

    def test_flatten_dict(self, section: GenericConfig):
        assert section.flatten_dict({}) == {}
        assert section.flatten_dict(self.single_level_flat) == self.single_level_flat
        assert section.flatten_dict(self.two_levels_nested) == self.two_levels_flat
        assert section.flatten_dict(self.deep_nested) == self.deep_flat

    @given(flat=GenericConfigInfo.values_strat())
    def test_flat_to_nest_around(self, flat: dict):
        section = GenericConfigInfo.section
        nested = section.nest_dict(flat)
        assert flat == section.flatten_dict(nested)

    @given(dicts=GenericConfigInfo.values_strat_nested())
    def test_flat_and_nested(self, dicts: dict):
        nested, flat = dicts
        section = GenericConfigInfo.section
        assert nested == section.nest_dict(flat)
        assert flat == section.flatten_dict(nested)


@todo
def test_merge_configs():
    """Test merge two different configuration dicts."""
    assert 0


class TestAutoGeneratedSection:
    @given(cls=section_st_to_cls(st_section_gen_single_trait()))
    def test_default(self, cls: type[Section]):
        cls()

    @given(section=section_st_to_instance(st_section_gen_single_trait()))
    def test_instance(self, section: Section):
        print(repr(section))

    @given(sections=section_st_to_instances(st_section_gen_single_trait(), n=2))
    def test_update(self, sections: tuple[Section, ...]):
        sectionA, sectionB = sections
        valA = dict(sectionA.items())
        valB = dict(sectionB.items())
        sectionA.update(sectionB)
        valA.update(valB)
        assert dict(sectionA.items()) == valA
