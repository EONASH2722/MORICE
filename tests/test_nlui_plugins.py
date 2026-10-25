"""Actual owned plugin subprocesses keep their existing review boundary."""
from types import SimpleNamespace
from unittest.mock import Mock

from test_plugin_platform import write_plugin
from morice.kernel import CapabilityKernel
from morice.nlui.runtime import NaturalLanguageController
from morice.nlui.contracts import ActiveContext
from morice.plugin_manager import PluginManager


def test_natural_plugin_lifecycle_and_denial_use_existing_manager(tmp_path):
    manager=PluginManager(tmp_path/'plugins');write_plugin(manager.install_root,'owned.extension')
    manager.discover();kernel=CapabilityKernel();controller=NaturalLanguageController(SimpleNamespace(kernel=kernel,plugins=manager))
    port=Mock(window_id='w');port.execute.return_value={'confirmed':False};controller.attach_window(port);context=ActiveContext('chat','w')
    def run(text):return controller.execute(controller.resolve(text,context),context)
    try:
        assert run('Start the owned.extension plugin').status=='failed'
        assert manager.require('owned.extension').sandbox is None
        port.execute.return_value={'confirmed':True}
        assert run('Start the owned.extension plugin').status=='completed'
        assert manager.diagnostics('owned.extension')['state']=='running'
        assert run('Pause the owned.extension plugin').status=='completed'
        assert manager.diagnostics('owned.extension')['state']=='paused'
        assert run('Resume the owned.extension plugin').status=='completed'
        assert run('Disable the owned.extension plugin').status=='completed'
        assert manager.require('owned.extension').sandbox is None
    finally:manager.shutdown();kernel.shutdown()
