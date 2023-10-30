
from __future__ import annotations

from traitlets import Instance, TraitType
from traitlets.config import Configurable, Config


class Scheme(Configurable):
    """Automatically tag its traits as configurable.

    On class definition (using the ``__init_subclass__`` hook) tag
    all class traits as configurable, unless already tagged as False.
    Just save you from adding ``...).tag(config=True)`` to every trait.

    Also add a class method to generate the config for a single trait.
    """
    _subschemes: dict[str, type[Scheme]] = {}

    def __init_subclass__(cls, /, **kwargs):
        super().__init_subclass__(**kwargs)

        classdict = cls.__dict__
        cls._subschemes = {}

        for k, v in classdict.items():
            # tag trait as configurable
            if isinstance(v, TraitType):
                if v.metadata.get('config', True):
                    v.tag(config=True)

            # register nested schemes
            if isinstance(v, type) and issubclass(v, Scheme):
                cls._subschemes[k] = v
                setattr(cls, k,
                        Instance(v, args=(), kw={}))

        cls.setup_class(classdict)


    @classmethod
    def class_traits_recursive(cls) -> Config:
        config = Config()
        config.update(cls.class_own_traits(config=True))
        for name, subscheme in cls._subschemes.items():
            config[name] = subscheme.class_traits_recursive()
        return config

    def defaults_recursive(self) -> Config:
        config = Config()
        config.update(self.trait_defaults(config=True))
        for name in self._subschemes.keys():
            subscheme_inst = getattr(self, name)
            config[name] = subscheme_inst.defaults_recursive()
        return config

    @classmethod
    def _subschemes_recursive(cls):
        for subscheme in cls._subschemes.values():
            yield from subscheme._subschemes_recursive()
        yield cls


    # @classmethod
    # def class_values_recursive(cls) -> dict:
    #     config = {}
    #     config.update(cls.(config=True))
    #     for name, subscheme in cls._subschemes.items():
    #         config[name] = subscheme.class_traits_recursive()
    #     return config
