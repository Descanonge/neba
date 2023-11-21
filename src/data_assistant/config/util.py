from typing import Callable

from traitlets.config import Configurable


def tag_all_traits(**metadata) -> Callable:
    """Tag all class-own traits.

    Parameters
    ----------
    metadata:
        Are passed to ``trait.tag(**metadata)``.
    """

    def decorator(cls: type[Configurable]):
        for trait in cls.class_own_traits().values():
            trait.tag(**metadata)
        return cls

    return decorator
