"""
Browser permission prompts that block the test.

Some pages make Firefox open prompts that belong to the browser UI, not to
the page - the same panel used for camera/microphone permission, e.g.:

- "Allow <site> to open the <protocol> link with <application>?" (external
  protocol dialog);
- "<site> wants to access other apps and services on this device" (Local
  Network Access).

Selenium only sees the page content, so TIR would wait until the timeout. The
functions here enter Marionette's "chrome" context (the browser UI) and accept
the prompt. They run inside TIR's own flow - after each navigation, on every
poll of the waits before the login screen, inside the scraping loops and on
entry of the login screens - always on the thread already using the driver.

Firefox only. On other browsers (no chrome context) every call is a no-op.
"""

import os
import time

from selenium.webdriver.support.ui import WebDriverWait

from tir.technologies.core.logging_config import logger

# Marionette only allows the "chrome" context with this variable in Firefox's
# environment. Firefox inherits it from geckodriver, which inherits it from
# us, so it must be set before the browser opens. Older versions ignore it.
SYSTEM_ACCESS_ENV = "MOZ_REMOTE_ALLOW_SYSTEM_ACCESS"

# Minimum interval between non-forced checks (waits and scraping loops)
CHECK_INTERVAL = 1.5

# Notifications that are not permission requests and must not be accepted
IGNORED_NOTIFICATIONS = ("password", "addon", "webauthn")

# Runs in the browser UI. Accepts the open permission prompts (doorhangers)
# and the external protocol dialog; returns what was accepted.
_ACCEPT_PROMPTS_JS = r"""
const ignored = arguments[0];
const accepted = [];
for (const win of Services.wm.getEnumerator("navigator:browser")) {
  // Permission prompts (same panel as camera/microphone). In headless mode
  // the panel never actually opens, so clicking its button does nothing: we
  // call the prompt's main action (what "Allow" calls, with "remember"
  // checked) and remove the prompt.
  const popups = win.PopupNotifications;
  const browsers = win.gBrowser ? win.gBrowser.browsers : [];
  for (const browser of browsers) {
    let notifications = [];
    try {
      notifications = popups._getNotificationsForBrowser
        ? popups._getNotificationsForBrowser(browser)
        : (browser === win.gBrowser.selectedBrowser ? popups._currentNotifications : []);
    } catch (e) {}
    for (const notification of [...(notifications || [])]) {
      const id = String(notification.id || "");
      if (!notification.mainAction || ignored.some((prefix) => id.startsWith(prefix))) continue;
      try {
        notification.mainAction.callback({ checkboxChecked: true, source: "button" });
        popups.remove(notification);
        accepted.push("popup:" + id);
      } catch (e) {}
    }
  }

  // External protocol dialog (permissionDialog.xhtml), opened as a tab or
  // window dialog
  const managers = [];
  try { if (win.gDialogBox) managers.push(win.gDialogBox.getManager()); } catch (e) {}
  for (const browser of (win.gBrowser ? win.gBrowser.browsers : [])) {
    try {
      const box = win.gBrowser.getTabDialogBox(browser);
      managers.push(box.getTabDialogManager(), box.getContentDialogManager());
    } catch (e) {}
  }
  for (const manager of managers) {
    for (const dialog of (manager && manager._dialogs) || []) {
      const frameDoc = dialog._frame && dialog._frame.contentDocument;
      const url = String((frameDoc && frameDoc.documentURI) || "");
      if (!url.includes("/handling/permissionDialog")) continue;
      const remember = frameDoc.getElementById("remember");
      if (remember && !remember.hidden) remember.checked = true;
      const dialogEl = frameDoc.querySelector("dialog");
      if (dialogEl) {
        dialogEl.acceptDialog();
        accepted.push("dialog:" + url.split("/").pop());
      }
    }
  }
}
return accepted;
"""


def allow_system_access():
    """Lets Marionette use the chrome context. Call before opening Firefox."""
    os.environ.setdefault(SYSTEM_ACCESS_ENV, "1")


def accept_browser_prompts(driver):
    """
    Accepts the permission prompts open in the Firefox UI and returns what
    was accepted. Never raises: without the chrome context the check is
    disabled for that driver and the test goes on as before.
    """
    if driver is None or getattr(driver, "_tir_prompts_disabled", False):
        return []
    context = getattr(driver, "context", None)
    chrome = getattr(driver, "CONTEXT_CHROME", None)
    if context is None or chrome is None:
        return []
    try:
        with context(chrome):
            accepted = driver.execute_script(_ACCEPT_PROMPTS_JS, list(IGNORED_NOTIFICATIONS))
    except Exception as e:
        if "chrome" in str(e).lower() or "system access" in str(e).lower():
            try:
                driver._tir_prompts_disabled = True
            except AttributeError:
                pass
            logger().warning(f"Firefox permission prompt check unavailable: {e}")
        else:
            logger().debug(f"Firefox permission prompt check failed: {e}")
        return []
    accepted = list(accepted or [])
    if accepted:
        logger().info(f"Firefox permission prompt accepted: {', '.join(accepted)}")
    return accepted


def check_browser_prompts(driver, force=False):
    """
    `accept_browser_prompts` with a minimum interval between calls, so it can
    run inside polling loops. `force` ignores the interval.
    """
    if driver is None:
        return
    now = time.monotonic()
    if not force and now - getattr(driver, "_tir_prompts_checked_at", 0.0) < CHECK_INTERVAL:
        return
    try:
        driver._tir_prompts_checked_at = now
    except AttributeError:
        pass
    accept_browser_prompts(driver)


class PromptAwareWait(WebDriverWait):
    """
    `WebDriverWait` that checks the browser prompts on every poll.

    Before the login screen TIR waits here for the start program screen. The
    prompt opens when the page's JS runs - after the check done by
    `driver_get` - so without this nobody accepts it until the wait times out.
    """

    def until(self, method, message=""):
        driver = self._driver

        def condition(d):
            check_browser_prompts(driver)
            return method(d)

        return super().until(condition, message)
