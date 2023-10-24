
from __future__ import annotations

from traitlets import Instance
from traitlets.config import Configurable, Config


class Scheme(Configurable):
    """Automatically tag its traits as configurable.

    On class definition (using the ``__init_subclass__`` hook) tag
    all class traits as configurable, unless already tagged as False.
    Just save you from adding ``...).tag(config=True)`` to every trait.

    Also add a class method to generate the config for a single trait.
    """

    _subschemes: dict[str, type[Scheme]]

    def __init_subclass__(cls, /, **kwargs) -> None:
        """Subclass init hook."""
        super().__init_subclass__(**kwargs)

        # first setup class descriptors
        cls.setup_class(cls.__dict__)

        # tag all trait not inherited from parent
        for trait in cls.class_own_traits().values():
            # do not tag if metadata already set to False
            if trait.metadata.get('config', True):
                trait.tag(config=True)

        # Register nested schemes
        cls._subschemes = {}
        for k, v in cls.__dict__.items():
            if isinstance(v, type) and issubclass(v, Scheme):
                cls._subschemes[k] = v
                setattr(
                    cls, k,
                    Instance(v, args=(), kw={}).tag(config=True)
                )

        # re-setup class descriptors
        cls.setup_class(cls.__dict__)

    # def __init__(self, config: dict | None = None):
    #     # Configurable subclasses should execute this first:
    #     super(Scheme, self).__init__()  # noqa: UP008

    #     # self._subschemes_instances = {}

    #     # if config is None:
    #     #     config = {}

    #     # for name, subscheme in self._subschemes.items():
    #     #     self._subschemes_instances[name] = subscheme(
    #     #         config=config.get(name, {})
    #     #     )

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


    # @classmethod
    # def class_values_recursive(cls) -> dict:
    #     config = {}
    #     config.update(cls.(config=True))
    #     for name, subscheme in cls._subschemes.items():
    #         config[name] = subscheme.class_traits_recursive()
    #     return config
