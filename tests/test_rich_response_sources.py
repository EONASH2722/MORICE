"""Use real stores/calculations/files; stale content cannot become a verified preview."""
import hashlib
from pathlib import Path
import struct
import time
from types import SimpleNamespace

import pytest

from morice.research.runtime import ResearchRuntime
from morice.rich_response import SourceRef
from morice.rich_response.mesh import load_stl
from morice.rich_response.sources import ResponseSources,StaleSourceError


@pytest.fixture
def sources(tmp_path):
    research=ResearchRuntime(tmp_path/'research.db',tmp_path/'research')
    try:yield ResponseSources(SimpleNamespace(research=research),'chat'),research
    finally:research.close()


def test_actual_generated_stl_is_loaded_and_changed_or_stale_files_are_blocked(sources):
    owner,research=sources;project=research.create('Owned geometry fixture')
    inputs={key:{'value':value,'unit':'mm'} for key,value in (('width',20),('height',30),('depth',40))}
    recorded=research.run_recorded(project,'research.cad',inputs)
    assert recorded['execution'].success
    reference=SourceRef('research_record',project+':'+recorded['record_id'],scope='chat')
    snapshot=owner.resolve(reference)
    artifact=next(a for a in snapshot.artifacts if a.id=='stl')
    mesh=load_stl(artifact.path,artifact.sha256)
    assert mesh.triangles==12 and mesh.degenerate_faces==0
    assert mesh.maximum==pytest.approx((.02,.03,.04)) and mesh.minimum==(0,0,0)
    artifact.path.write_bytes(artifact.path.read_bytes()+b'changed')
    changed=owner.resolve(reference)
    assert not next(a for a in changed.artifacts if a.id=='stl').available
    assert next(a for a in changed.artifacts if a.id=='bom').available
    with pytest.raises(ValueError):load_stl(artifact.path,artifact.sha256)
    research.store.invalidate(project,recorded['record_id'],'Owned stale-input fixture')
    with pytest.raises(StaleSourceError,match='stale'):owner.resolve(reference)


def test_cross_chat_reference_and_changed_revision_are_rejected(sources):
    owner,research=sources;project=research.create('Actual notebook')
    with pytest.raises(PermissionError):owner.resolve(SourceRef('research_project',project,scope='other-chat'))
    with pytest.raises(StaleSourceError):owner.resolve(SourceRef('research_project',project,'not-the-real-revision','chat'))


def test_session_disabled_source_retains_duplicate_user_rows_without_writing_history(tmp_path):
    from unittest.mock import Mock
    message={'message_id':'actual-user','role':'user','content':'x,y\n1,2\n1,2\n3,4'}
    history=Mock();history.fetch_message.return_value=None
    owner=ResponseSources(SimpleNamespace(chat_history=history),'chat',messages=[message])
    snapshot=owner.resolve(SourceRef('chat_dataset','actual-user',scope='chat'))
    key=snapshot.data['row_identity_field']
    assert snapshot.rows[0]['x']==snapshot.rows[1]['x'] and snapshot.rows[0][key]!=snapshot.rows[1][key]
    assert [row['y'] for row in owner.table_page(snapshot.source)['rows']]==[2,2,4]
    assert not history.save.called


def test_saved_geographic_response_keeps_original_coordinates_after_workspace_changes(sources,tmp_path):
    from morice.spatial.service import SpatialService
    from morice.research.history import ChatHistory
    from morice.rich_response.sources import digest
    owner,research=sources;spatial=SpatialService(research.kernel)
    value=spatial.handle_text('Show Chennai and Tokyo')['context']
    history=ChatHistory(research.store.database)
    saved=history.save('chat',[{'role':'assistant','content':'Actual geographic result.'}])
    message=history.fetch_range('chat')[0]['message_id']
    assert history.set_response_source('chat',message,'spatial',value)
    sources=ResponseSources(SimpleNamespace(chat_history=history,spatial=spatial),'chat')
    reference=SourceRef('spatial',message,digest(value),'chat')
    original=sources.resolve(reference)
    spatial.handle_text('Show London and New York')
    restored=sources.resolve(reference)
    assert restored.data==original.data==value
    assert restored.data['destination']['identifier']!=spatial.snapshot()['destination']['identifier']


def test_saved_transcript_query_uses_indexed_source_messages_and_excludes_private_and_current_chats(tmp_path):
    from morice.research.history import ChatHistory
    history=ChatHistory(tmp_path/'actual-history.db')
    messages=[{'role':'user','content':'A neutral saved title'},{'role':'assistant','content':'The fusion reactor uses tungsten walls.'},{'role':'assistant','content':'A neutral final preview'}]
    history.save('earlier',messages);history.save('private',messages);history.configure('private','Private archive',retention='session')
    history.save('current',[{'role':'user','content':'Find the chat about fusion'},{'role':'assistant','content':'Actual query results'}])
    rows=history.search_transcripts('fusion',exclude_chat='current')
    assert [r['id'] for r in rows]==['earlier'] and 'fusion reactor' in rows[0]['matching_excerpt']
    assert history.fetch_message('earlier',rows[0]['matching_message_id'])['content']=='The fusion reactor uses tungsten walls.'
    assistant=history.fetch_range('current')[-1]['message_id'];history.set_response_source('current',assistant,'chat_search',{'query':'fusion'})
    owner=ResponseSources(SimpleNamespace(chat_history=history),'current')
    snapshot=owner.resolve(SourceRef('chat_metadata',assistant,scope='current'))
    assert [row['id'] for row in snapshot.rows]==['earlier']
    history.edit_message('earlier',rows[0]['matching_message_id'],'Different supplied topic.')
    assert not owner.resolve(snapshot.source).rows


def test_ascii_mesh_bounds_and_malformed_vertices_are_checked(tmp_path):
    path=tmp_path/'actual.stl'
    raw=b'solid actual\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid actual\n'
    path.write_bytes(raw);mesh=load_stl(path,hashlib.sha256(raw).hexdigest())
    assert mesh.triangles==1 and mesh.maximum==(1,1,0)
    for malformed in (raw.replace(b'endfacet',b'bad'),raw.replace(b'vertex 1 0 0',b'vertex nan 0 0'),raw.replace(b'endloop',b'bad')):
        path.write_bytes(malformed)
        with pytest.raises(ValueError):load_stl(path,hashlib.sha256(malformed).hexdigest())
    binary=b'actual'.ljust(80,b' ')+struct.pack('<I',100001)
    path.write_bytes(binary)
    with pytest.raises(ValueError):load_stl(path,hashlib.sha256(binary).hexdigest())


def test_artifact_reference_cannot_escape_its_domain_root(tmp_path):
    outside=tmp_path/'outside.txt';outside.write_text('Owned fixture')
    with pytest.raises(ValueError):ResponseSources._artifact('a','a',outside,hashlib.sha256(outside.read_bytes()).hexdigest(),tmp_path/'allowed')


def test_actual_export_requires_selected_destination_and_never_overwrites_or_ignores_denial(sources,tmp_path):
    from dataclasses import asdict
    from morice.kernel import ExecutionContext
    from morice.rich_response.exports import register_response_exports
    from morice.unified_intelligence import PermissionState
    owner,research=sources;project=research.create('Owned export fixture')
    inputs={key:{'value':10,'unit':'mm'} for key in ('width','height','depth')}
    result=research.run_recorded(project,'research.cad',inputs)
    source=SourceRef('research_record',project+':'+result['record_id'],scope='chat')
    runtime=SimpleNamespace(kernel=research.kernel,research=research)
    register_response_exports(runtime)
    destination=tmp_path/'selected.stl'
    arguments={'source':asdict(source),'artifact':'stl','destination':str(destination)}
    assert not research.kernel.dispatch('response.artifact.export',arguments,ExecutionContext(conversation_id='chat')).success
    assert not destination.exists()
    context=ExecutionContext(conversation_id='chat',active_files=(str(destination),))
    exported=research.kernel.dispatch('response.artifact.export',arguments,context)
    assert exported.success and exported.verification.status.value=='verified'
    actual=destination.read_bytes()
    assert not research.kernel.dispatch('response.artifact.export',arguments,context).success
    assert destination.read_bytes()==actual
    research.kernel.permissions.controller.set_state('file_write',PermissionState.DENIED)
    denied=tmp_path/'denied.stl';arguments['destination']=str(denied)
    assert not research.kernel.dispatch('response.artifact.export',arguments,ExecutionContext(conversation_id='chat',active_files=(str(denied),))).success
    assert not denied.exists()


def test_native_render_export_cannot_be_forged_by_json_inputs(sources,tmp_path):
    from morice.kernel import ExecutionContext
    from morice.rich_response.exports import register_response_exports
    _,research=sources;runtime=SimpleNamespace(kernel=research.kernel,research=research,directory=tmp_path/'runtime')
    register_response_exports(runtime);destination=tmp_path/'selected.png'
    result=research.kernel.dispatch('response.render.export',{'destination':str(destination)},
        ExecutionContext(conversation_id='chat',active_files=(str(destination),),metadata={'response_render':{'path':'forged','format':'png'}}))
    assert not result.success and not destination.exists()


def test_data_csv_export_neutralizes_formula_cells_and_preserves_numeric_values(tmp_path):
    import csv
    from morice.rich_response.sources import SourceSnapshot
    from morice.rich_response.exports import capture_data
    owner=ResponseSources(SimpleNamespace(directory=tmp_path),'chat')
    snapshot=SourceSnapshot(SourceRef('chat_dataset','actual',scope='chat'),'Actual supplied data','USER_DATA','revision',{},
        rows=[{'label':'=1+1','value':-2},{'label':'  @SUM(A1)','value':4}])
    rendered=capture_data(owner,snapshot,'csv')
    try:
        with rendered.path.open(newline='',encoding='utf-8') as stream:rows=list(csv.reader(stream))
        assert rows[1]==["'=1+1",'-2'] and rows[2][0].startswith("'")
    finally:rendered.cleanup()
