"""Test more integrated features of the Application."""

def test_logger():
    # test it goes to the correct logger ? idk
    pass


def test_strict_parsing_off():
    pass


class TestStartup:

    def test_ignore_cli(self):
        pass

    def auto_instanciate(self):
        pass


class TestCLIParsing:

    def test_parse_argv(self):
        # parse *those* argv and not default
        pass

    def test_add_extra_parameter(self):
        # check it adds stuff in the right places
        pass

    def test_extra_parameters_values(self):
        # check we parsed some good values out of it
        pass

def test_resolve_config():
    # normal keys
    # class keys
    # aliases
    pass


class TestWriteConfig:

    # parmetrize for multiple loaders
    def test_write_no_comment(self):
        # check no comments in output
        pass

    def test_clobber_abort(self):
        pass

    def test_clobber_overwriter(self):
        pass

    def test_clobber_update(self):
        pass

    def test_clobber_ask(self):
        # How do you test this ?
        pass
