"""Unit tests for tir/technologies/core/browser_prompts.py."""

import contextlib
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from tir.technologies.core import browser_prompts  # noqa: E402


class _Driver:
    CONTEXT_CHROME = "chrome"

    def __init__(self, result=None, error=None):
        self.result = result if result is not None else []
        self.error = error
        self.contexts = []
        self.scripts = 0

    @contextlib.contextmanager
    def context(self, name):
        self.contexts.append(name)
        yield

    def execute_script(self, script, *args):
        self.scripts += 1
        if self.error is not None:
            raise self.error
        return self.result


def setUpModule():
    # TIR's logger() needs a configured run (config.json, log folder)
    patcher = mock.patch.object(browser_prompts, "logger")
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


class AcceptPromptsTests(unittest.TestCase):
    def test_runs_in_chrome_context_and_reports_accepted(self):
        driver = _Driver(result=["popup:local-network"])
        self.assertEqual(browser_prompts.accept_browser_prompts(driver), ["popup:local-network"])
        self.assertEqual(driver.contexts, ["chrome"])

    def test_chrome_context_unavailable_disables_check(self):
        driver = _Driver(error=Exception("System access is required to switch to chrome scope"))
        self.assertEqual(browser_prompts.accept_browser_prompts(driver), [])
        self.assertEqual(browser_prompts.accept_browser_prompts(driver), [])
        self.assertEqual(driver.scripts, 1)

    def test_other_errors_never_propagate(self):
        driver = _Driver(error=RuntimeError("session gone"))
        self.assertEqual(browser_prompts.accept_browser_prompts(driver), [])
        self.assertFalse(getattr(driver, "_tir_prompts_disabled", False))

    def test_driver_without_chrome_context_is_ignored(self):
        # Chrome/Electron: no Marionette chrome context
        driver = mock.Mock(spec=["execute_script"])
        self.assertEqual(browser_prompts.accept_browser_prompts(driver), [])
        driver.execute_script.assert_not_called()

    def test_none_driver(self):
        self.assertEqual(browser_prompts.accept_browser_prompts(None), [])


class CheckPromptsTests(unittest.TestCase):
    def test_check_is_throttled(self):
        driver = _Driver()
        for _ in range(5):
            browser_prompts.check_browser_prompts(driver)
        self.assertEqual(driver.scripts, 1)

    def test_force_ignores_interval(self):
        driver = _Driver()
        driver._tir_prompts_checked_at = time.monotonic()
        browser_prompts.check_browser_prompts(driver, force=True)
        self.assertEqual(driver.scripts, 1)

    def test_none_driver(self):
        browser_prompts.check_browser_prompts(None, force=True)


class PromptAwareWaitTests(unittest.TestCase):
    def test_wait_checks_prompts_while_polling(self):
        # The prompt opens after driver_get, while TIR waits for the start
        # program screen: the wait itself must accept it.
        driver = _Driver()
        answers = iter([False, False, True])
        wait = browser_prompts.PromptAwareWait(driver, timeout=5, poll_frequency=0)
        self.assertTrue(wait.until(lambda d: next(answers)))
        self.assertEqual(driver.scripts, 1)
        self.assertEqual(driver.contexts, ["chrome"])


class SystemAccessTests(unittest.TestCase):
    def test_allow_system_access_sets_env(self):
        with mock.patch.dict("os.environ", clear=False) as env:
            env.pop(browser_prompts.SYSTEM_ACCESS_ENV, None)
            browser_prompts.allow_system_access()
            self.assertEqual(env[browser_prompts.SYSTEM_ACCESS_ENV], "1")

    def test_allow_system_access_keeps_existing_value(self):
        with mock.patch.dict("os.environ", {browser_prompts.SYSTEM_ACCESS_ENV: "0"}):
            browser_prompts.allow_system_access()
            self.assertEqual(browser_prompts.os.environ[browser_prompts.SYSTEM_ACCESS_ENV], "0")


if __name__ == "__main__":
    unittest.main()
