
from traitlets import TraitType
from traitlets.utils.text import wrap_paragraphs

def make_all_configurable(cls):
    """Mark all this class traits as configurable.

    No need to tag every trait with `.tag(config=True)`.
    """
    for _, trait in cls.class_own_traits().items():
        trait.tag(config=True)
    cls.setup_class(cls.__dict__)


def generate_config_trait(trait: TraitType) -> str:
    """Generate config text for a single trait."""
    # Taken from traitlets.Configurable.class_config_section()
    def c(s):
        s = '\n\n'.join(wrap_paragraphs(s, 78))
        return '## ' + s.replace('\n', '\n#  ')

    lines = []
    default_repr = trait.default_value_repr()

    # cls owns the trait, show full help
    if trait.help:
        lines.append(c(trait.help))
    if 'Enum' in type(trait).__name__:
        # include Enum choices
        lines.append(f'#  Choices: {trait.info}')
    lines.append(f'#  Default: {default_repr}')

    return '\n'.join(lines)
