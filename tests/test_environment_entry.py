"""
Unit tests for WebappInternal.check_environment_entry, which runs right after the start
program/environment screen, before the login:

- an environment error ("Invalid setting. Verify STARTPATH variable...") fails the test
  right away, with the Protheus message;
- the "USER FUNCTION debug is active" warning is closed before TIR looks for the user input.
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

STARTPATH_MESSAGE = (
    "Invalid setting. Verify STARTPATH variable in your environment option or verify "
    "if your file settings (.ini) is corrupted"
)

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
STARTPATH_DIALOG = f"""
<body><wa-text-input name='cGetUser'></wa-text-input><wa-dialog title="TOTVS">
  <wa-text-view caption="{STARTPATH_MESSAGE}"></wa-text-view>
  <wa-button caption="Ok"></wa-button>
</wa-dialog></body>
"""
LOGIN = "<body><wa-text-input name='cGetUser'></wa-text-input></body>"
OTHER_DIALOG = "<body><wa-dialog><wa-text-view caption='Outro aviso'></wa-text-view></wa-dialog></body>"
EMPTY = "<body></body>"
WARNING_OVER_LOGIN = WARNING_EN.replace("<body>", "<body><wa-text-input name='cGetUser'></wa-text-input>")


def build_webapp(*doms, language="en-us", poui_login=False):
    webapp = WebappInternal.__new__(WebappInternal)
    webapp.config = SimpleNamespace(time_out=30, poui_login=poui_login, language="pt-br",
                                    json_data={"Language": language})
    webapp.language = LanguagePack("pt-br")
    webapp.driver = None
    webapp.webapp_shadowroot = mock.Mock(return_value=True)
    webapp.get_current_DOM = mock.Mock(side_effect=[BeautifulSoup(d, "html.parser") for d in doms])
    webapp.SetButton = mock.Mock()
    webapp.log_error = mock.Mock()
    return webapp


def fake_clock():
    clock = iter(range(0, 1000))
    return mock.patch.object(webapp_internal.time, "time", lambda: next(clock))


@mock.patch.object(webapp_internal, "logger", mock.Mock())
@mock.patch.object(webapp_internal.time, "sleep", lambda _: None)
class EnvironmentErrorTests(unittest.TestCase):
    def test_startpath_dialog_fails_right_away_with_the_message(self):
        webapp = build_webapp(EMPTY, STARTPATH_DIALOG)
        with self.assertRaises(ValueError) as error:
            webapp.check_environment_entry()
        self.assertIn("Couldn't enter the environment", str(error.exception))
        self.assertIn(STARTPATH_MESSAGE, str(error.exception))
        webapp.log_error.assert_called_once_with(str(error.exception), restart_counter_param=3)
        self.assertEqual(webapp.get_current_DOM.call_count, 2)
        webapp.SetButton.assert_not_called()

    def test_startpath_inside_shadow_root_is_found_by_javascript(self):
        webapp = build_webapp(EMPTY)
        webapp.find_text_in_page = mock.Mock(return_value={
            "needle": "startpath", "where": "page <wa-dialog> shadow root", "text": STARTPATH_MESSAGE,
        })
        with self.assertRaises(ValueError) as error:
            webapp.check_environment_entry()
        self.assertIn(STARTPATH_MESSAGE, str(error.exception))
        needles = webapp.find_text_in_page.call_args.args[0]
        self.assertEqual(needles, ["startpath", "user function debug is active"])

    def test_startpath_alert_fails_right_away(self):
        webapp = build_webapp(EMPTY)
        webapp.driver = SimpleNamespace(switch_to=SimpleNamespace(alert=SimpleNamespace(text=STARTPATH_MESSAGE)))
        with self.assertRaises(ValueError) as error:
            webapp.check_environment_entry()
        self.assertIn(STARTPATH_MESSAGE, str(error.exception))
        webapp.get_current_DOM.assert_not_called()

    def test_every_term_is_normalized(self):
        for term in WebappInternal.ENVIRONMENT_ERROR_TERMS:
            self.assertEqual(term, WebappInternal.normalize_dialog_text(term))


@mock.patch.object(webapp_internal, "logger", mock.Mock())
@mock.patch.object(webapp_internal.time, "sleep", lambda _: None)
class UserFunctionDebugWarningTests(unittest.TestCase):
    def test_closes_warning_shown_before_login(self):
        webapp = build_webapp(EMPTY, WARNING_EN)
        self.assertTrue(webapp.check_environment_entry())
        webapp.SetButton.assert_called_once_with("Ok", check_error=False)
        webapp.log_error.assert_not_called()

    def test_portuguese_warning_with_entities_and_br(self):
        webapp = build_webapp(WARNING_PT, language="pt-br")
        self.assertTrue(webapp.check_environment_entry())
        webapp.SetButton.assert_called_once()

    def test_warning_over_login_input_is_closed(self):
        webapp = build_webapp(LOGIN, WARNING_OVER_LOGIN)
        self.assertTrue(webapp.check_environment_entry())
        webapp.SetButton.assert_called_once()

    def test_nothing_found_waits_only_the_timeout(self):
        webapp = build_webapp(*[OTHER_DIALOG, LOGIN] * 50)
        with fake_clock():
            self.assertFalse(webapp.check_environment_entry(timeout=15))
        webapp.SetButton.assert_not_called()
        webapp.log_error.assert_not_called()
        self.assertLessEqual(webapp.get_current_DOM.call_count, 15)

    def test_closes_warning_with_poui_login(self):
        webapp = build_webapp(WARNING_EN, poui_login=True)
        self.assertTrue(webapp.check_environment_entry())
        webapp.SetButton.assert_called_once()

    def test_warning_only_inside_shadow_root_is_found_by_javascript(self):
        webapp = build_webapp(EMPTY)
        webapp.find_text_in_page = mock.Mock(return_value={
            "needle": "user function debug is active", "where": "page <wa-message-box> shadow root", "text": "",
        })
        self.assertTrue(webapp.check_environment_entry())
        webapp.SetButton.assert_called_once()
        webapp.log_error.assert_not_called()

    def test_logs_what_it_looks_for_and_dialogs_seen(self):
        webapp = build_webapp(OTHER_DIALOG, OTHER_DIALOG, LOGIN)
        log = webapp_internal.logger.return_value
        log.reset_mock()
        with fake_clock():
            self.assertFalse(webapp.check_environment_entry(timeout=4))
        messages = [call.args[0] for call in log.info.call_args_list]
        self.assertIn("startpath", messages[0])
        self.assertIn("user function debug is active", messages[0])
        self.assertIn("Outro aviso", messages[1])
        self.assertEqual(sum("Dialogs on screen" in m for m in messages), 2)
        self.assertIn("No environment error nor user function debug warning found", messages[-1])

    def test_text_comes_from_config_json_language(self):
        webapp = build_webapp(WARNING_EN, language="en-us")
        self.assertTrue(webapp.check_environment_entry())
        webapp.SetButton.assert_called_once()

        webapp = build_webapp(WARNING_EN, language="pt-br")
        webapp.find_text_in_page = mock.Mock(return_value=None)
        self.assertFalse(webapp.check_environment_entry(timeout=0))
        webapp.SetButton.assert_not_called()

    def test_empty_language_tag_falls_back_to_page_language(self):
        webapp = build_webapp(WARNING_EN, language="")
        webapp.config.language = "en-us"
        self.assertTrue(webapp.check_environment_entry())

    def test_every_language_has_the_text(self):
        for language in ("en-us", "pt-br", "es-es", "ru-ru"):
            self.assertTrue(LanguagePack(language).user_function_debug)


if __name__ == "__main__":
    unittest.main()
