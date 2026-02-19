"""Test Section class."""

import logging
from collections.abc import Mapping, MutableMapping

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from traitlets import Bool, Int, Unicode

from neba.config import Section, Subsection
from neba.config.types import UnknownConfigKeyError
from tests.config.generic_config import (
    GenericConfigInfo,
    GenericSection,
    SectionInfo,
    TwinSubsection,
)
from tests.config.section_generation import st_section_inst

log = logging.getLogger(__name__)

info = GenericConfigInfo


class SimpleSection(Section):
    aliases = {"deep": "sub.sub2"}

    a = Unicode("a").tag(test_meta=True)
    b = Unicode("b")

    class sub(Section):
        c = Unicode("c").tag(test_meta=True)
        d = Unicode("d")

        class sub2(Section):
            e = Unicode("e").tag(test_meta=True)
            f = Unicode("f")


class TestDefinition:
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

        assert S._subsections["a"].klass is cls_a
        assert S._subsections["b"].klass is cls_b
        assert S._subsections["b"].klass._subsections["c"].klass is cls_c
        assert S._subsections["normal"].klass is NormalSubsection
        # check using descriptors
        assert S.a.klass is cls_a
        assert S.b.klass is cls_b
        assert S.b.klass.c.klass is cls_c
        assert S.normal.klass is NormalSubsection

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

    @given(inst=st_section_inst())
    def test_random_definition(self, inst: tuple[Section]):
        """Test for randomly generated Section class."""
        print(repr(inst[0]))

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

    def test_traits_tagged(self):
        """Test that trait are automatically tagged configurable."""

        def test_tagged_section(info: type[SectionInfo], section: Section):
            for key in info.keys(recursive=False, subsections=False):
                trait = section.traits()[key]
                assert trait.metadata["config"] is True

            for name, sub_info in info.subsections.items():
                test_tagged_section(sub_info, section[name])

        test_tagged_section(info, info.section())

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
    def test_wrong_alias(self, alias):
        """Make sure we detect wrong aliases."""
        with pytest.raises(KeyError):

            class Subclass(Section):
                aliases = {"short": "alias"}

        with pytest.raises(ValueError):

            class SubclassB(Section):
                aliases = {"short.with.dots": "alias"}

    def test_iter_subsections(self):
        """Test iterating on subsections.

        Also test Subsection descriptors access.
        """
        cls = info.section_subclass()
        section = cls()
        section.add_trait("new_empty.new_trait", Int(0))
        ref_list = [
            GenericSection,
            TwinSubsection,
            TwinSubsection,
            cls.sub_twin.klass,
            cls.deep_sub.klass,
            cls.empty_a.klass,
            cls.empty_b.klass,
            section._subsections["new_empty"].klass,
        ]
        for sub_inst, ref in zip(section.subsections().values(), ref_list, strict=True):
            assert isinstance(sub_inst, ref)
        for sub_cls, ref in zip(
            section.class_subsections().values(), ref_list, strict=True
        ):
            assert issubclass(sub_cls, ref)

    def test_iter_subsections_recursive(self):
        cls = info.section_subclass()
        section = cls()
        section.add_trait("new_empty.new_trait", Int(0))
        ref_list = [
            cls,
            GenericSection,
            TwinSubsection,
            TwinSubsection,
            cls.sub_twin.klass,
            cls.sub_twin.klass.twin_c.klass,
            cls.deep_sub.klass,
            GenericSection,
            cls.empty_a.klass,
            cls.empty_b.klass,
            cls.empty_b.klass.empty_c.klass,
            section._subsections["new_empty"].klass,
        ]
        for sub_inst, ref in zip(
            section.subsections_recursive(), ref_list, strict=True
        ):
            assert isinstance(sub_inst, ref)
        for sub_cls, ref in zip(
            section.class_subsections_recursive(), ref_list, strict=True
        ):
            assert issubclass(sub_cls, ref)


class TestInstantiation:
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

    def test_subsections(self):
        def test_subsection_class(info, section):
            for name, sub_info in info.subsections.items():
                assert issubclass(section._subsections[name].klass, sub_info.section)
                assert isinstance(section[name], sub_info.section)
                test_subsection_class(sub_info, section[name])

        test_subsection_class(info, info.section())

    @given(values=GenericConfigInfo.values_strat())
    def test_recursive(self, values: dict):
        """Recursive instantiation (with subsection)."""
        info = GenericConfigInfo
        s = info.section(values)
        for key in info.keys():
            if key in values:
                assert s[key] == values[key]
            else:
                assert s[key] == info.default(key)

    def test_init_kwargs(self):
        conf = dict(int=10, str="a")
        s = info.section(conf, int=20)
        assert s.int == 20
        assert s.str == "a"
        # conf dict has not been modified
        assert conf == dict(int=10, str="a")

    def test_wrong_extra_parameters(self):
        bad_keys = [
            "bad_trait",
            "sub_generic.bad_trait",
            "bad_subsection.bad_trait",
        ]
        for key in bad_keys:
            with pytest.raises(KeyError):
                Section({key: 0})
            with pytest.raises(KeyError):
                Section({}, **{key: 0})  # type: ignore[arg-type]
            with pytest.raises(KeyError):
                Section({key: 0}, **{key: 0})  # type: ignore[arg-type]

    def test_repr(self):
        prefixes = "\u2574\u251c\u2514\u251d\u2501\u2511\u2515\u2502 "
        section = info.section(init_subsections=False)

        lines = repr(section).splitlines()
        traits = info.keys(subsections=False, recursive=False)
        assert len(lines) == len(traits) + 1
        assert lines.pop(0) == "GenericConfig"
        for line, name in zip(lines, traits, strict=True):
            assert line.lstrip(prefixes).startswith(name + ":")

        section = info.section()
        lines = repr(section).splitlines()
        lines = [line.lstrip(prefixes) for line in lines]
        lines = [line for line in lines if line]
        traits = info.keys(subsections=True, recursive=True)
        assert lines.pop(0) == "GenericConfig"
        for line, name in zip(lines, traits, strict=True):
            assert line.startswith(name.split(".")[-1] + ":")

    @given(values=GenericConfigInfo.values_strat())
    def test_copy(self, values: dict):
        section = info.section(values)
        copy = section.copy()

        assert section == copy

    def test_copy_no_link(self):
        section = info.section()
        copy = section.copy()
        copy.int = 2
        copy.list_int.append(1)
        assert section.int == 0
        assert section.list_int == [0]


def bool_param(name: str):
    values = [True, False]
    ids = [name + "FT"[v] for v in values]
    return pytest.mark.parametrize(name, values, ids=ids)


class TestMappingInterface:
    """Test the Mapping interface of Sections."""

    def test_is_mapping(self):
        assert issubclass(Section, Mapping)
        assert isinstance(Section(), Mapping)

        assert issubclass(info.section, Mapping)
        assert isinstance(info.section(), Mapping)

    def test_getitem(self):
        section = info.section()
        for key in info.keys(subsections=True, aliases=True):
            if key in info.keys(aliases=True):
                assert section[key] == info.default(key)
            else:
                assert isinstance(section[key], Section)

    def test_get(self):
        section = info.section()
        for key in info.keys(subsections=True, aliases=True):
            if key in info.keys(aliases=True):
                assert section.get(key) == info.default(key)
            else:
                assert isinstance(section.get(key), Section)

        assert section.get("wrong_key") is None
        assert section.get("sub_generic.wrong_key") is None
        assert section.get("empty_a.wrong_key") is None
        assert section.get("wrong_subsection.wrong_key") is None
        assert section.get("wrong_subsection.wrong_key", 2) == 2

    def test_missing_keys(self):
        section = info.section()
        for key in ["missing_key", "missing_sub.key"]:
            assert key not in section
        with pytest.raises(KeyError):
            section[key]

    def test_iter(self):
        section = info.section()
        for ref, key in zip(info.keys(), section, strict=True):
            assert ref == key

    def test_contains(self):
        section = info.section()
        for key in info.keys(subsections=True, aliases=True):
            assert key in section

        assert "invalid" not in section
        assert "nested.invalid" not in section

    def test_length(self):
        section = info.section()
        assert len(section) == len(info.keys())

    def test_eq_basic(self):
        section_a = info.section()
        section_b = info.section()

        assert section_a == section_b

        section_b["int"] += 2
        assert section_a != section_b

        # other is not a section
        assert section_a is not None
        assert section_a != {}

        # test other has not same keys
        class OtherSection(Section):
            key = Int(0)

        assert OtherSection() != section_a

    @given(values=GenericConfigInfo.values_strat())
    @settings(deadline=None)
    def test_eq_values(self, values: dict):
        section_a = info.section(values)
        section_b = info.section()

        for k, v in values.items():
            section_b[k] = v

        assert section_a == section_a
        assert section_a == section_b

    @bool_param("recursive")
    @bool_param("subsections")
    @bool_param("aliases")
    def test_keys(self, recursive: bool, subsections: bool, aliases: bool):
        section = info.section()
        assert info.keys(
            recursive=recursive, subsections=subsections, aliases=aliases
        ) == list(
            section.keys(recursive=recursive, subsections=subsections, aliases=aliases)
        )

    def test_values(self):
        section = info.section()
        for k, v in zip(info.keys(), section.values(), strict=True):
            assert info.default(k) == v

    def test_items(self):
        section = info.section()
        for ref, (k, v) in zip(info.keys(), section.items(), strict=True):
            assert ref == k
            assert info.default(k) == v
            # if ref in info.traits_total:
            # else:
            #     assert isinstance(v, Section)

    @given(values=GenericConfigInfo.values_strat())
    def test_as_dict(self, values: dict):
        section = info.section(values)

        as_dict = section.as_dict()
        for k in info.keys():
            value = values[k] if k in values else info.default(k)
            assert as_dict[k] == value


class TestMutableMappingInterface:
    """Test the mutable mapping interface of Sections.

    With some dictionnary functions as well.
    """

    def test_is_mutable_mapping(self):
        assert issubclass(Section, MutableMapping)
        assert isinstance(Section(), MutableMapping)

        assert issubclass(info.section, MutableMapping)
        assert isinstance(info.section(), MutableMapping)

    @given(values=GenericConfigInfo.values_strat())
    def test_set(self, values: dict):
        """Test __set__ with random values.

        Random keys are selected and appropriate values drawn as well. We check that set
        keys are correctly changed, and that no other keys than those selected were
        changed, to make sure we have no side effect (especially in twin sections). Which
        only works for our generic section that has no observe events or stuff like that.
        """
        section = info.section()

        for key, val in values.items():
            section[key] = val

        for key in info.keys():
            if key in values:
                assert section[key] == values[key]
            else:
                assert section[key] == info.default(key)

    def test_set_manual(self):
        section = info.section()

        section["bool"] = False
        assert section["bool"] is False

        section["sub_generic.list_int"] = [0, 1, 2]
        assert section.sub_generic.list_int == [0, 1, 2]
        assert section["sub_generic.list_int"] == [0, 1, 2]

        section["deep_sub.sub_generic_deep.str"] = "DOTARO"
        assert section["deep_sub.sub_generic_deep.str"] == "DOTARO"
        section.deep_sub.sub_generic_deep.str = "JIO"
        assert section.deep_sub.sub_generic_deep.str == "JIO"

        # plus aliases
        section["deep_short.float"] = 5.0
        assert section["deep_sub.sub_generic_deep.float"] == 5.0
        assert section.deep_sub.sub_generic_deep.float == 5.0

    def test_set_wrong(self):
        section = info.section()
        bad_keys = ["bad_trait", "sub_generic.bad_trait", "bad_section.bad_trait"]
        for key in bad_keys:
            with pytest.raises(KeyError):
                section[key] = 0

    def test_add_trait(self):
        section = info.section_subclass_inst()

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

        # check original section class has not been affected
        section = info.section()
        assert "new_trait" not in section
        assert "deep_sub.sub_generic_deep.new_trait" not in section
        assert "new_trait" not in section.deep_sub.sub_generic_deep

    def test_setdefault(self):
        section = info.section_subclass_inst()

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

        # check original section class has not been affected
        section = info.section()
        assert "new_int" not in section
        assert "sub_generic.new_int" not in section
        assert "new_int" not in section.sub_generic

    def test_unavailable(self):
        section = info.section()

        with pytest.raises(TypeError):
            section.pop("anything")

        with pytest.raises(TypeError):
            section.popitem()

        with pytest.raises(TypeError):
            section.clear()

    @given(values=GenericConfigInfo.values_strat())
    def test_reset(self, values: dict):
        section = info.section()
        section.update(values)
        section.reset()
        for key in values:
            assert section[key] == info.default(key)

    def test_twin_siblings(self):
        """Two subsections on are from the same class."""
        section = info.section_subclass_inst()

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

        # adding traits
        section.twin_a.add_trait("new_trait", Int(0))
        assert not hasattr(section.twin_b, "new_trait")
        assert "new_trait" not in section.twin_b.traits_recursive()
        assert "twin_b.new_trait" not in type(section).traits_recursive()
        assert "new_trait" not in type(section).twin_b.klass.class_traits()

    def test_twin_recursive(self):
        """Two sections at different nesting level are from the same class."""
        section = info.section_subclass_inst()

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

        # adding traits
        section.add_trait("sub_twin.twin_c.new_trait", Int(0))
        assert not hasattr(section.twin_a, "new_trait")
        assert "new_trait" not in section.twin_a.traits_recursive()
        assert "twin_a.new_trait" not in type(section).traits_recursive()
        assert "new_trait" not in type(section).twin_a.klass.class_traits()

    @given(values=GenericConfigInfo.values_strat())
    def test_update_dict(self, values: dict):
        section = info.section()
        section.update(values)

        for key in info.keys():
            if key in values:
                assert section[key] == values[key]
            else:
                assert section[key] == info.default(key)

    @given(values=GenericConfigInfo.values_strat())
    def test_update_section(self, values: dict):
        sectionA = info.section()
        sectionB = info.section(values)
        sectionA.update(sectionB)
        assert sectionB == sectionA
        for k, v in values.items():
            assert sectionA[k] == v

    @given(sections=st_section_inst(n_set=2))
    def test_update_random(self, sections: tuple[Section, Section]):
        """Test with randomly generated sections."""
        sectionA, sectionB = sections
        sectionA.update(sectionB)
        # Same operation with dicts
        valA = dict(sectionA.items())
        valB = dict(sectionB.items())
        valA.update(valB)
        assert dict(sectionA.items()) == valA

    def test_update_add_traits(self):
        section = info.section_subclass_inst()
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

        # other is section
        class Other(Section):
            new_trait_from_section = Int(1)

        other = Other()
        other.new_trait_from_section = 10
        section.update(other, allow_new=True)
        assert section["new_trait_from_section"] == 10

    def test_update_wrong(self):
        section = info.section()
        with pytest.raises(KeyError):
            section.update({"new_trait": Int(10)})
        with pytest.raises(TypeError):
            section.update({"new_trait": 10}, allow_new=True)

        assert "new_trait" not in section


class TestDidYouMean:
    def test_getattr(self):
        section = info.section()

        with pytest.raises(AttributeError) as excinfo:
            _ = section.int_
        assert str(excinfo.value) == (
            "'GenericConfig' object has no attribute 'int_' (did you mean 'int'?)"
        )

        with pytest.raises(AttributeError) as excinfo:
            _ = section.sub_generic_
        assert str(excinfo.value) == (
            "'GenericConfig' object has no attribute 'sub_generic_'"
            " (did you mean 'sub_generic'?)"
        )

        with pytest.raises(AttributeError) as excinfo:
            _ = section.sub_generic.int_
        assert str(excinfo.value) == (
            "Section 'sub_generic' (GenericSection) has no attribute 'int_'"
            " (did you mean 'int'?)"
        )

    def test_getitem(self):
        section = info.section()

        with pytest.raises(KeyError) as excinfo:
            _ = section["int_"]
        assert str(excinfo.value).strip('"') == (
            "Could not resolve key 'int_' (did you mean 'int'?)"
        )

        with pytest.raises(KeyError) as excinfo:
            _ = section["sub_generic_"]
        assert str(excinfo.value).strip('"') == (
            "Could not resolve key 'sub_generic_' (did you mean 'sub_generic'?)"
        )

        with pytest.raises(KeyError) as excinfo:
            _ = section["sub_generic.int_"]
        assert str(excinfo.value).strip('"') == (
            "Could not resolve key 'sub_generic.int_' (did you mean 'sub_generic.int'?)"
        )

    def test_setitem(self):
        section = info.section()

        with pytest.raises(KeyError) as excinfo:
            section["int_"] = 0
        assert str(excinfo.value).strip('"') == (
            "Could not resolve key 'int_' (did you mean 'int'?)"
        )

        with pytest.raises(KeyError) as excinfo:
            section["sub_generic.int_"] = 0
        assert str(excinfo.value).strip('"') == (
            "Could not resolve key 'sub_generic.int_' (did you mean 'sub_generic.int'?)"
        )


class TestTraitListing:
    """Test the trait listing abilities."""

    def test_dir(self):
        section = info.section()
        section._attr_completion_only_traits = True
        assert dir(section) == sorted(info.keys(subsections=True, recursive=False))

    @given(
        keys=st.lists(
            st.sampled_from(GenericConfigInfo.keys()), max_size=12, unique=True
        )
    )
    def test_select(self, keys: list[str]):
        # We only test flattened, we assume nest_dict() works and is tested
        section = info.section()
        out = section.select(*keys)
        assert keys == list(out.keys())

    def test_metadata_select(self):
        class MetadataSection(Section):
            no_config = Int(0).tag(config=False)
            no_config_tagged = Int(0).tag(config=False, tagged=True)
            normal = Int(0)
            normal_tagged = Int(0).tag(tagged=True)

            class sub(Section):
                no_config = Int(0).tag(config=False)
                no_config_tagged = Int(0).tag(config=False, tagged=True)
                normal = Int(0)
                normal_tagged = Int(0).tag(tagged=True)

        sec = MetadataSection()
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

    def test_iter_traits(self):
        traits = dict(SimpleSection._iter_traits(subsections=True, aliases=True))
        for key in [
            "a",
            "b",
            "sub.c",
            "sub.d",
            "sub.sub2.e",
            "sub.sub2.f",
            "deep.e",
            "deep.f",
        ]:
            assert isinstance(traits[key], Unicode)
            assert traits[key].default_value == key.rsplit(".", 1)[-1]
        for key in ["sub", "sub.sub2", "deep"]:
            assert issubclass(traits[key], Section)

        assert "deep.e" not in dict(SimpleSection._iter_traits(aliases=False))

    def test_own_traits(self):
        class ChildSection(GenericSection):
            a = Int(0)

            class sub(Section):
                b = Int(0)

        names = [
            k
            for k, _ in ChildSection._iter_traits(
                subsections=True, own_traits=True, config=True
            )
        ]
        assert names == ["a", "sub", "sub.b"]

    def test_traits_recursive_simple(self):
        traits = SimpleSection.traits_recursive(recursive=False)
        assert list(traits.keys()) == ["a", "b"]
        traits = SimpleSection.sub.klass.traits_recursive(recursive=False)
        assert list(traits.keys()) == ["c", "d"]

        traits = SimpleSection.traits_recursive()
        assert list(traits.keys()) == [
            "a",
            "b",
            "sub.c",
            "sub.d",
            "sub.sub2.e",
            "sub.sub2.f",
        ]
        for key, trait in traits.items():
            assert trait.default_value == key.rsplit(".", 1)[-1]

        traits = SimpleSection.traits_recursive(aliases=True)
        keys = [
            "a",
            "b",
            "sub.c",
            "sub.d",
            "sub.sub2.e",
            "sub.sub2.f",
            "deep.e",
            "deep.f",
        ]
        assert list(traits.keys()) == keys
        for key, trait in traits.items():
            assert trait.default_value == key.rsplit(".", 1)[-1]

        traits = SimpleSection.traits_recursive(nest=True)
        assert list(traits.keys()) == ["a", "b", "sub"]

        traits = SimpleSection.traits_recursive(nest=True, aliases=True)
        assert list(traits.keys()) == ["a", "b", "sub", "deep"]
        assert list(traits["sub"].keys()) == ["c", "d", "sub2"]
        assert list(traits["sub"]["sub2"].keys()) == ["e", "f"]
        assert list(traits["deep"].keys()) == ["e", "f"]
        assert traits["a"].default_value == "a"
        assert traits["sub"]["sub2"]["e"].default_value == "e"
        assert traits["deep"]["f"].default_value == "f"

    def test_defaults_recursive(self):
        section = info.section()

        assert list(section.defaults_recursive().keys()) == info.keys()
        for k, v in section.defaults_recursive().items():
            assert info.default(k) == v

        assert SimpleSection.defaults_recursive() == {
            "a": "a",
            "b": "b",
            "sub.c": "c",
            "sub.d": "d",
            "sub.sub2.e": "e",
            "sub.sub2.f": "f",
        }

        assert SimpleSection.defaults_recursive(aliases=True) == {
            "a": "a",
            "b": "b",
            "sub.c": "c",
            "sub.d": "d",
            "sub.sub2.e": "e",
            "sub.sub2.f": "f",
            "deep.e": "e",
            "deep.f": "f",
        }

        assert SimpleSection.defaults_recursive(nest=True) == {
            "a": "a",
            "b": "b",
            "sub": {
                "c": "c",
                "d": "d",
                "sub2": {"e": "e", "f": "f"},
            },
        }
        assert SimpleSection.defaults_recursive(nest=True, aliases=True) == {
            "a": "a",
            "b": "b",
            "sub": {
                "c": "c",
                "d": "d",
                "sub2": {"e": "e", "f": "f"},
            },
            "deep": {"e": "e", "f": "f"},
        }

    def test_value_from_func_signature(self):
        def func(list_int, enum_int, tuple_float, other_a, other_b):
            pass

        section = info.section()
        values = section.trait_values_from_func_signature(func)
        assert all(k in values for k in ["list_int", "enum_int", "tuple_float"])
        assert "other_a" not in values
        assert "other_b" not in values


class TestResolveKey:
    """Test key resolution."""

    def test_resolve_key(self):
        section_cls = info.section

        key, container_cls, trait = section_cls.resolve_key("bool")
        assert key == "bool"
        assert issubclass(container_cls, section_cls)
        assert isinstance(trait, Bool)

        key, container_cls, trait = section_cls.resolve_key("sub_generic.int")
        assert key == "sub_generic.int"
        assert issubclass(container_cls, GenericSection)
        assert isinstance(trait, Int)

        key, container_cls, trait = section_cls.resolve_key("twin_a.int")
        assert key == "twin_a.int"
        assert issubclass(container_cls, TwinSubsection)
        assert isinstance(trait, Int)

        key, container_cls, trait = section_cls.resolve_key("deep_short.int")
        assert key == "deep_sub.sub_generic_deep.int"
        assert issubclass(container_cls, GenericSection)
        assert isinstance(trait, Int)

    def test_wrong_keys(self):
        def assert_bad_key(key: str):
            with pytest.raises(UnknownConfigKeyError):
                info.section.resolve_key(key)

        assert_bad_key("invalid_trait")
        assert_bad_key("invalid_sub.trait_name")
        assert_bad_key("sub_generic.invalid_trait")
        assert_bad_key("empty_b.empty_c.invalid_trait")


class TestNestFlatten:
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
        "deep_short.int": 30,
    }
    two_levels_nested = dict(
        int=0,
        bool=1,
        sub_generic=dict(int=10, bool=11, str=12, enum_int=13),
        twin_a=dict(int=20, list_int=21),
        deep_short=dict(int=30),
    )

    deep_flat = {
        "deep_sub.sub_generic_deep.int": 0,
        "deep_sub.sub_generic_deep.bool": 1,
    }
    deep_nested = {"deep_sub": {"sub_generic_deep": {"int": 0, "bool": 1}}}

    def test_nest_dict(self):
        section = info.section()
        assert section.nest_dict({}) == {}
        assert section.nest_dict(self.single_level_flat) == self.single_level_flat
        assert section.nest_dict(self.two_levels_flat) == self.two_levels_nested
        assert section.nest_dict(self.deep_flat) == self.deep_nested

    def test_flatten_dict(self):
        section = info.section()
        assert section.flatten_dict({}) == {}
        assert section.flatten_dict(self.single_level_flat) == self.single_level_flat
        assert section.flatten_dict(self.two_levels_nested) == self.two_levels_flat
        assert section.flatten_dict(self.deep_nested) == self.deep_flat

    @given(flat=GenericConfigInfo.values_strat())
    def test_flat_to_nest_around(self, flat: dict):
        section = info.section()
        nested = section.nest_dict(flat)
        assert flat == section.flatten_dict(nested)

    @given(dicts=GenericConfigInfo.values_strat_nested())
    def test_flat_and_nested(self, dicts: dict):
        nested, flat = dicts
        section = info.section()
        assert nested == section.nest_dict(flat)
        assert flat == section.flatten_dict(nested)

    def test_nest_wrong(self):
        section = info.section()
        flat = {"int": 0, "sub_generic.float": 0.0}
        bad_keys = ["bad_trait", "sub_generic.bad_trait", "bad_subsection.bad_trait"]
        for bad_key in bad_keys:
            flat_bad = flat.copy()
            flat_bad[bad_key] = 0
            with pytest.raises(KeyError):
                section.nest_dict(flat_bad)

    def test_flatten_wrong(self):
        section = info.section()
        # bad trait
        nested = dict(int=0, sub_generic=dict(float=0.0), bad_trait=0)
        with pytest.raises(KeyError):
            section.flatten_dict(nested)

        # bad trait in subsection
        nested = dict(int=0, sub_generic=dict(float=0.0, bad_trait=0))
        with pytest.raises(KeyError):
            section.flatten_dict(nested)

        # bad subsection
        nested = dict(
            int=0, sub_generic=dict(float=0.0), bad_subsection=dict(bad_trait=0)
        )
        with pytest.raises(KeyError):
            section.flatten_dict(nested)

        # subsection is not a mapping
        nested = dict(int=0, sub_generic=5.0)
        with pytest.raises(KeyError):
            section.flatten_dict(nested)
