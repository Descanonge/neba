"""Test loaders and associated functionalities."""

from data_assistant.config.loaders.core import ConfigLoader, FileLoader

LOADERS: list[type[ConfigLoader]]
FILE_LOADERS: list[type[FileLoader]]


class TestConfigValue:
    """Test ConfigValue related features."""

    def test_copy(self):
        pass

    def test_get_value(self):
        pass

    def test_parse(self):
        """Test parsing to a trait.

        to test with most trait possible I guess ? See for nested traits
        """
        pass

    def test_aliases(self):
        pass


class DictLikeLoader:
    """Test on python dict.

    This behavior should be the same for other loaders (json, yaml) but easier to test.
    """

    def test_reading(self):
        pass


class TestCLILoader:
    def test_setting_new_action(self):
        pass

    def test_help(self):
        pass

    def test_values_are_parsed(self):
        pass

    def test_parsing(self):
        # test by hand all traits in the typical scheme
        # it should include pretty much all reasonable traits
        pass


def test_file_choose_loader():
    # maybe in application ?
    pass


class TestPythonLoader:
    """Test loading from executing python file."""

    def test_pyconfig_container(self):
        """Test behavior of the `c` container object."""
        pass

    def test_exception(self):
        """Test when file throw exception."""
        pass


# Parametrize for all loaders
class TestConfigLoader:
    def test_add_multiple(self):
        """Key already in config."""
        pass

    def test_application_traits(self):
        """Check application traits are applied."""
        pass


# Parametrize for all file loaders
def test_reading():
    """Test reading a configuration file.

    File is written by hand to change some values from default.
    """
    pass


# Parametrize for all file loaders
def test_to_lines_some():
    # for the typical scheme
    # change SOME values
    # to_lines in a temp file
    # read file
    # check same values
    pass


# Parametrize for all file loaders
def test_to_lines_all():
    # for the typical scheme
    # specify ALL values
    # to_lines in a temp file
    # read file
    # check same values
    pass
