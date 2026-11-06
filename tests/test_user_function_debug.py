"""
Unit tests for WebappInternal.close_user_function_debug_screen: the "USER FUNCTION
debug is active" warning that Protheus opens before the login screen is closed
before TIR looks for the user input.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from bs4 import BeautifulSoup  # noqa: E402

from tir.technologies import webapp_internal  # noqa: E402
from tir.technologies.core.language import LanguagePack  # noqa: E402

WebappInternal = webapp_internal.WebappInternal

WARNING_EN = """
<body><wa-dialog title="TOTVS">
  <wa-text-view caption="USER FUNCTION debug is active, you will have performance cost."></wa-text-view>
  <wa-button caption="Ok"></wa-button>
</wa-dialog></body>
"""
WARNING_PT = """
<body><wa-dialog><wa-text-view caption="O debug da FUN&Ccedil;&Atilde;O DO USU&Aacute;RIO est&aacute; ativo,<br>haver&aacute; custo de performance.">
</wa-text-view></wa-dialog></body>
"""
LOGIN = "<body><wa-text-input name='cGetUser'></wa-text-input></body>"
OTHER_DIALOG = "<body><wa-dialog><wa-text-view caption='Outro aviso'></wa-text-view></wa-dialog></body>"
EMPTY = "<body></body>"
WARNING_OVER_LOGIN = WARNING_EN.replace("<body>", "<body><wa-text-input name='cGetUser'></wa-text-input>")


def build_webapp(*doms, language="en-us", poui_login=False):
    webapp = WebappInternal.__new__(WebappInternal)
    webapp.config = SimpleNamespace(time_out=30, poui_login=poui_login)
    webapp.language = LanguagePack(language)
    webapp.driver = None
    webapp.webapp_shadowroot = mock.Mock(return_value=True)
    webapp.get_current_DOM = mock.Mock(side_effect=[BeautifulSoup(d, "html.parser") for d in doms])
    webapp.SetButton = mock.Mock()
    return webapp


@mock.patch.object(webapp_internal, "logger", mock.Mock())
@mock.patch.object(webapp_internal.time, "sleep", lambda _: None)
class CloseUserFunctionDebugScreenTests(unittest.TestCase):
    def test_closes_warning_shown_before_login(self):
        webapp = build_webapp(EMPTY, WARNING_EN)
        self.assertTrue(webapp.close_user_function_debug_screen())
        webapp.SetButton.assert_called_once_with("Ok", check_error=False)

    def test_portuguese_warning_with_entities_and_br(self):
        webapp = build_webapp(WARNING_PT, language="pt-br")
        self.assertTrue(webapp.close_user_function_debug_screen())
        webapp.SetButton.assert_called_once()

    def test_warning_over_login_input_is_closed(self):
        webapp = build_webapp(LOGIN, WARNING_OVER_LOGIN)
        self.assertTrue(webapp.close_user_function_debug_screen())
        webapp.SetButton.assert_called_once()

    def test_no_warning_waits_only_the_timeout(self):
        webapp = build_webapp(*[OTHER_DIALOG, LOGIN] * 50)
        clock = iter(range(0, 1000))
        with mock.patch.object(webapp_internal.time, "time", lambda: next(clock)):
            self.assertFalse(webapp.close_user_function_debug_screen(timeout=15))
        webapp.SetButton.assert_not_called()
        self.assertLessEqual(webapp.get_current_DOM.call_count, 15)

    def test_closes_warning_with_poui_login(self):
        webapp = build_webapp(WARNING_EN, poui_login=True)
        self.assertTrue(webapp.close_user_function_debug_screen())
        webapp.SetButton.assert_called_once()

    def test_every_language_has_the_text(self):
        for language in ("en-us", "pt-br", "es-es", "ru-ru"):
            self.assertTrue(LanguagePack(language).user_function_debug)


if __name__ == "__main__":
    unittest.main()
