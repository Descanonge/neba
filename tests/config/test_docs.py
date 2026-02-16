"""Test documentation related functions of neba.config.docs."""

from traitlets import Dict, Enum, Instance, Int, List, Tuple, Type, Unicode, Union

from neba.config.docs import get_trait_typehint
from neba.config.section import Section, tag_all_traits


class TestTypehint:
    """Test the string representation of trait types."""

    def valid(self, x, target: str, **kwargs):
        assert get_trait_typehint(x, **kwargs) == target

    def test_basic_object(self):
        self.valid(1, "~builtins.int")
        self.valid(1, "builtins.int", mode="full")
        self.valid(1, "int", mode="minimal")
        self.valid(dict(), "~builtins.dict")

        class Test:
            pass

        qual_path = "tests.config.test_docs.TestTypehint.test_basic_object.<locals>"

        self.valid(Test(), f"~{qual_path}.Test")
        self.valid(Test(), f"{qual_path}.Test", mode="full")
        self.valid(Test(), "Test", mode="minimal")

        self.valid(Test, f"~{qual_path}.Test")
        self.valid(Test, f"{qual_path}.Test", mode="full")
        self.valid(Test, "Test", mode="minimal")

    def test_basic_trait(self):
        self.valid(Int(), "~traitlets.traitlets.Int")
        self.valid(Int(), "traitlets.traitlets.Int", mode="full")
        self.valid(Int(), "Int", mode="minimal")

        self.valid(Unicode(), "~traitlets.traitlets.Unicode")
        self.valid(Unicode(), "traitlets.traitlets.Unicode", mode="full")
        self.valid(Unicode(), "Unicode", mode="minimal")

        self.valid(Enum([1, 2]), "~traitlets.traitlets.Enum")
        self.valid(Enum([1, 2]), "traitlets.traitlets.Enum", mode="full")
        self.valid(Enum([1, 2]), "Enum", mode="minimal")

    def test_allow_none(self):
        self.valid(Int(allow_none=True), "~traitlets.traitlets.Int | None")
        self.valid(Int(allow_none=True), "traitlets.traitlets.Int | None", mode="full")
        self.valid(Int(allow_none=True), "Int | None", mode="minimal")

    def test_list(self):
        self.valid(List(), "~traitlets.traitlets.List")
        self.valid(List(), "traitlets.traitlets.List", mode="full")
        self.valid(List(), "List", mode="minimal")

        self.valid(List(Int()), "~traitlets.traitlets.List[~traitlets.traitlets.Int]")
        self.valid(
            List(Int()),
            "traitlets.traitlets.List[traitlets.traitlets.Int]",
            mode="full",
        )
        self.valid(List(Int()), "List[Int]", mode="minimal")

    def test_tuple(self):
        # simple
        trait = Tuple(Int(), Int(), Unicode())
        self.valid(
            trait,
            (
                "~traitlets.traitlets.Tuple[~traitlets.traitlets.Int, "
                "~traitlets.traitlets.Int, ~traitlets.traitlets.Unicode]"
            ),
        )
        self.valid(trait, "Tuple[Int, Int, Unicode]", mode="minimal")

        # no trait specified
        self.valid(Tuple(), "~traitlets.traitlets.Tuple")
        self.valid(Tuple(), "Tuple", mode="minimal")

        # Recursive
        trait = Tuple(
            Tuple(Int(allow_none=True)), List(Unicode(), allow_none=True), Unicode()
        )
        self.valid(
            trait,
            "~traitlets.traitlets.Tuple["
            "~traitlets.traitlets.Tuple[~traitlets.traitlets.Int | None], "
            "~traitlets.traitlets.List[~traitlets.traitlets.Unicode] | None, "
            "~traitlets.traitlets.Unicode]",
        )
        self.valid(
            trait,
            "Tuple[Tuple[Int | None], List[Unicode] | None, Unicode]",
            mode="minimal",
        )

    def test_dict(self):
        # Both specified
        trait = Dict(key_trait=Unicode(), value_trait=Int(allow_none=True))
        self.valid(
            trait,
            (
                "~traitlets.traitlets.Dict"
                "[~traitlets.traitlets.Unicode, ~traitlets.traitlets.Int | None]"
            ),
        )
        self.valid(trait, "Dict[Unicode, Int | None]", mode="minimal")

        # Only key specified
        trait = Dict(key_trait=Unicode())
        self.valid(trait, "~traitlets.traitlets.Dict[~traitlets.traitlets.Unicode]")
        self.valid(trait, "Dict[Unicode]", mode="minimal")

        # Only value specified
        trait = Dict(value_trait=Int(allow_none=True))
        self.valid(
            trait,
            ("~traitlets.traitlets.Dict[~typing.Any, ~traitlets.traitlets.Int | None]"),
        )
        self.valid(trait, "Dict[Any, Int | None]", mode="minimal")

        # None specified
        self.valid(Dict(), "~traitlets.traitlets.Dict")
        self.valid(Dict(), "Dict", mode="minimal")

    def test_instance_and_type(self):
        class Test:
            pass

        qual_path = (
            "tests.config.test_docs.TestTypehint.test_instance_and_type.<locals>"
        )

        trait = Instance(Test)
        self.valid(trait, f"~traitlets.traitlets.Instance[~{qual_path}.Test]")
        self.valid(trait, "Instance[Test]", mode="minimal")

        self.valid(Type(), "~traitlets.traitlets.Type")
        trait = Type(klass=Test)
        self.valid(trait, f"~traitlets.traitlets.Type[~{qual_path}.Test]")
        self.valid(trait, "Type[Test]", mode="minimal")

        # Str klass
        trait = Instance("some.Class")
        self.valid(trait, "~traitlets.traitlets.Instance[~some.Class]")
        self.valid(trait, "traitlets.traitlets.Instance[some.Class]", mode="full")
        self.valid(trait, "Instance[Class]", mode="minimal")
        trait = Type(klass="some.Class")
        self.valid(trait, "~traitlets.traitlets.Type[~some.Class]")
        self.valid(trait, "traitlets.traitlets.Type[some.Class]", mode="full")
        self.valid(trait, "Type[Class]", mode="minimal")

    def test_union(self):
        # 2 elements
        trait = Union([Int(), Unicode()])
        self.valid(trait, "~traitlets.traitlets.Int | ~traitlets.traitlets.Unicode")
        self.valid(trait, "Int | Unicode", mode="minimal")

        # 3 elements
        trait = Union([Int(), Unicode(), List(Int())])
        self.valid(
            trait,
            (
                "~traitlets.traitlets.Int | ~traitlets.traitlets.Unicode | "
                "~traitlets.traitlets.List[~traitlets.traitlets.Int]"
            ),
        )
        self.valid(trait, "Int | Unicode | List[Int]", mode="minimal")

    def test_union_allow_none(self):
        kw = dict(target="Int | Unicode | None", mode="minimal")
        self.valid(Union([Int(allow_none=True), Unicode()]), **kw)
        self.valid(Union([Int(), Unicode(allow_none=True)]), **kw)
        self.valid(Union([Int(allow_none=True), Unicode(allow_none=True)]), **kw)
        self.valid(Union([Int(allow_none=True), Unicode()], allow_none=True), **kw)

    def test_deep_nest(self):
        trait = Dict(
            value_trait=List(Union([Int(), Tuple(Int(), Unicode())])),
            key_trait=Unicode(),
        )
        self.valid(
            trait, "Dict[Unicode, List[Int | Tuple[Int, Unicode]]]", mode="minimal"
        )


def test_tag_all_traits():
    @tag_all_traits(test_tag=True)
    class MySection(Section):
        a = Int()
        b = Int()
        c = Int().tag(test_tag=False)

    assert MySection().trait_names(test_tag=True) == ["a", "b"]
