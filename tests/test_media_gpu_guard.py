"""Native vision must share media/local reasoning GPU admission."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from morice.kernel import CapabilityKernel, ResourceClaim, ResourceDescriptor
from morice.live_vision import _shared_vision_gpu_claim
from morice.media_lab.hardware import HardwareSnapshot


def test_native_gpu_vision_waits_for_existing_media_lease(tmp_path):
    kernel = CapabilityKernel()
    kernel.resources.register(ResourceDescriptor('GPU', 1))
    kernel.resources.register(ResourceDescriptor('LOCAL_MODEL', 1))
    provider = SimpleNamespace(gpu_layers=99, model_path=None, mmproj_path=None, _process=None)
    assert kernel.resources.acquire('media', (ResourceClaim('GPU', exclusive=True),))
    try:
        with patch('morice.runtime_services.peek_runtime_services', return_value=SimpleNamespace(kernel=kernel)), patch('morice.media_lab.hardware.probe_hardware') as probe:
            with pytest.raises(RuntimeError, match='busy'):
                with _shared_vision_gpu_claim(provider):
                    pytest.fail('Native provider cannot run while media owns GPU.')
            probe.assert_not_called()
        assert set(kernel.resources.snapshot()) == {'media'}
    finally:
        kernel.resources.release('media'); kernel.shutdown()


def test_native_vision_probes_model_and_projector_and_releases(tmp_path):
    kernel = CapabilityKernel()
    kernel.resources.register(ResourceDescriptor('GPU', 1))
    kernel.resources.register(ResourceDescriptor('LOCAL_MODEL', 1))
    model = tmp_path / 'vision.gguf'; model.write_bytes(b'model')
    projector = tmp_path / 'mmproj.gguf'; projector.write_bytes(b'projector')
    provider = SimpleNamespace(gpu_layers=99, model_path=model, mmproj_path=projector, _process=None)
    snapshot = HardwareSnapshot(total_vram_mb=6144, free_vram_mb=5000)
    try:
        with patch('morice.runtime_services.peek_runtime_services', return_value=SimpleNamespace(kernel=kernel)), patch('morice.media_lab.hardware.probe_hardware', return_value=snapshot):
            with _shared_vision_gpu_claim(provider):
                assert kernel.resources.current_holds('GPU')
                assert kernel.resources.current_holds('LOCAL_MODEL')
        assert not kernel.resources.snapshot()
        with patch('morice.runtime_services.peek_runtime_services', return_value=SimpleNamespace(kernel=kernel)), patch('morice.media_lab.hardware.probe_hardware', return_value=HardwareSnapshot(total_vram_mb=6144, free_vram_mb=800)):
            with pytest.raises(RuntimeError, match='Insufficient measured VRAM'):
                with _shared_vision_gpu_claim(provider):
                    pytest.fail('Cannot allocate after live memory rejection.')
        assert not kernel.resources.snapshot()
    finally:
        kernel.shutdown()


def test_cpu_vision_does_not_probe_or_claim_gpu():
    with patch('morice.runtime_services.peek_runtime_services', return_value=object()), patch('morice.media_lab.hardware.probe_hardware') as probe:
        with _shared_vision_gpu_claim(SimpleNamespace(gpu_layers=0)):
            pass
        probe.assert_not_called()
