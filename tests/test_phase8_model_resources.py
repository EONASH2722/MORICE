"""Local chat and agent backends use the same physical model admission."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from morice.agent_runtime import AgentCoordinator
from morice.agent_runtime.models import ModelBudget,ModelReply
from morice.kernel import CapabilityKernel,ExecutionContext,ResourceClaim,ResourceDescriptor
from morice import llm_client


@pytest.fixture
def model_system():
    kernel=CapabilityKernel();agents=AgentCoordinator(kernel)
    runtime=SimpleNamespace(kernel=kernel)
    with patch('morice.runtime_services._RUNTIME_SERVICES',runtime),patch.object(llm_client,'_resolve_gguf_path',return_value='owned-fixture.gguf'),patch.object(llm_client,'DEFAULT_USE_SERVER',False):
        yield kernel,agents
    agents.shutdown();kernel.shutdown()
    assert not kernel.resources.snapshot()


def test_busy_shared_model_rejects_chat_without_wait_or_second_backend(model_system):
    kernel,_=model_system
    assert kernel.resources.acquire('active-agent',(ResourceClaim('LOCAL_MODEL'),))
    try:
        with patch.object(llm_client,'local_stream_chat') as backend:
            with pytest.raises(RuntimeError,match='busy'):list(llm_client.stream_chat([],'Hello',gguf_path='owned-fixture.gguf'))
            backend.assert_not_called()
        assert set(kernel.resources.snapshot())=={'active-agent'}
    finally:kernel.resources.release('active-agent')


def test_closing_stream_releases_claim_and_active_model_cannot_unload(model_system):
    kernel,_=model_system
    with patch.object(llm_client,'local_stream_chat',return_value=iter(['first','second'])):
        stream=llm_client.stream_chat([],'Hello',gguf_path='owned-fixture.gguf')
        assert next(stream)=='first'
        assert len(kernel.resources.snapshot())==1 and not kernel.resources.current_holds('LOCAL_MODEL')
        with pytest.raises(RuntimeError,match='busy'):
            next(llm_client.stream_chat([],'Independent second stream',gguf_path='owned-fixture.gguf'))
        with pytest.raises(RuntimeError,match='active local model lease'):llm_client.reset_model_runtime()
        stream.close()
        assert not kernel.resources.snapshot() and not kernel.resources.current_holds('LOCAL_MODEL')


def test_agent_backend_reuses_existing_kernel_claim_without_self_deadlock(model_system):
    kernel,agents=model_system;calls=[]
    def local(*args,**kwargs):
        calls.append(len(kernel.resources.snapshot()))
        assert kernel.resources.current_holds('LOCAL_MODEL')
        return 'A bounded model fixture reply.'
    def backend(*,prompt,model_id,max_output_tokens,context):
        return ModelReply(llm_client.chat([],prompt,gguf_path='owned-fixture.gguf'),model_id,4,4)
    agents.models.configure('phase8-model',backend)
    with patch.object(llm_client,'local_chat',side_effect=local):
        result=kernel.dispatch('agent.reason',{'prompt':'Hello'},ExecutionContext(metadata={
            'model_budget':ModelBudget(1,5000),'model_config':{'selected_model':'phase8-model','max_output_tokens':64}}))
    assert result.success and calls==[1] and not kernel.resources.snapshot()


def test_remote_model_lease_cannot_authorize_a_busy_local_model(model_system):
    kernel,_=model_system
    kernel.resources.register(ResourceDescriptor('LOCAL_MODEL',node_id='owned-peer'))
    assert kernel.resources.acquire('remote-work',(ResourceClaim('LOCAL_MODEL',node_id='owned-peer'),))
    assert kernel.resources.acquire('local-work',(ResourceClaim('LOCAL_MODEL'),))
    try:
        with kernel.resources.execution_scope('remote-work'),patch.object(llm_client,'local_chat') as backend:
            assert kernel.resources.current_holds('LOCAL_MODEL',node_id='owned-peer')
            with pytest.raises(RuntimeError,match='busy'):llm_client.chat([],'Hello',gguf_path='owned-fixture.gguf')
            backend.assert_not_called()
    finally:
        kernel.resources.release('remote-work');kernel.resources.release('local-work')


def test_optional_dependency_check_does_not_import_native_provider():
    from morice.runtime_services import StartupHealthChecker
    with patch('morice.runtime_services.importlib.util.find_spec',return_value=None):
        check=StartupHealthChecker()._dependency_check('vosk','vosk')
    assert check.status=='unavailable' and not check.critical
