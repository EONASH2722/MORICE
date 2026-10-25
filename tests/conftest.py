"""Retire native Qt test objects on the application thread between cases."""
import gc
import sys

import pytest


@pytest.fixture(autouse=True)
def settle_native_teardown():
    yield
    # PySide widgets can participate in Python reference cycles. Leaving a
    # completed test's deferred deletes/cycles for the next allocating worker
    # can destroy native GUI objects on that worker. Drain them after ordinary
    # fixtures have closed their owners, while the GUI thread still owns Qt.
    # Automatic GC remains enabled and no test assertion or worker is skipped.
    widgets=sys.modules.get('PySide6.QtWidgets')
    if widgets is None:return
    application=widgets.QApplication.instance()
    if application is None:return
    from PySide6.QtCore import QCoreApplication,QEvent,QThread
    if QThread.currentThread()!=application.thread():
        raise RuntimeError('Native Qt test teardown must run on the application thread.')
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    application.processEvents()
    gc.collect()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    application.processEvents()
