"""Test more integrated features of the Application."""


def test_logger():
    # test it goes to the correct logger ? idk
    assert 0


def test_strict_parsing_off():
    assert 0


class TestStartup:
    def test_ignore_cli(self):
        assert 0

    def auto_instanciate(self):
        assert 0


class TestCLIParsing:
    def test_parse_argv(self):
        # parse *those* argv and not default
        assert 0

    def test_add_extra_parameter(self):
        # check it adds stuff in the right places
        assert 0

    def test_extra_parameters_values(self):
        # check we parsed some good values out of it
        assert 0


def test_resolve_config():
    # normal keys
    # class keys
    # aliases
    assert 0


class TestWriteConfig:
    # parmetrize for multiple loaders
    def test_write_no_comment(self):
        # check no comments in output
        assert 0

    def test_clobber_abort(self):
        assert 0

    def test_clobber_overwriter(self):
        assert 0

    def test_clobber_update(self):
        assert 0

    def test_clobber_ask(self):
        # How do you test this ?
        assert 0
