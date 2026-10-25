"""Verified artifact copies use the existing Kernel and selected-file policy."""
from pathlib import Path
from dataclasses import dataclass

from ..kernel import CapabilityDescriptor,ExecutionResult,TaskStatus,VerificationResult,VerificationStatus
from ..unified_intelligence import PermissionDecision,PermissionState
from .contracts import SourceRef
from .sources import ResponseSources


@dataclass
class ResponseRender:
    """In-process native rendering receipt, never accepted from model JSON."""
    owner:ResponseSources
    source:SourceRef
    path:Path
    format:str
    temporary:object
    sources:tuple=()

    def cleanup(self):self.temporary.cleanup()


def register_response_exports(runtime):
    kernel=runtime.kernel;identifier='response.artifact.export'
    if kernel.registry.lookup(identifier) and kernel.registry.lookup('response.render.export'):return

    def permission(args,context):
        state=kernel.permissions.controller.state('file_write')
        destination=str(Path(args['destination']).resolve())
        selected={str(Path(value).resolve()) for value in context.active_files}
        allowed=state==PermissionState.GRANTED or state==PermissionState.ASK and destination in selected
        return PermissionDecision(allowed,required=() if allowed else ('file_write',),
            reason='' if allowed else 'Select the export destination under the existing file-write policy. Denied permissions remain in force.')

    def execute(args,context):
        from ..media_lab.artifacts import atomic_export
        owner=ResponseSources(runtime,context.conversation_id)
        snapshot=owner.resolve(SourceRef.from_dict(args['source']))
        artifact=next((a for a in snapshot.artifacts if a.id==args['artifact']),None)
        if artifact is None:raise ValueError('That artifact does not belong to this current verified source.')
        if not artifact.available:raise ValueError(artifact.reason)
        receipt=atomic_export(artifact.path,args['destination'],artifact.sha256)
        return ExecutionResult(TaskStatus.SUCCEEDED,True,receipt,verification_required=True)

    def verify(result,expected,context):
        from ..media_lab.storage import file_hash
        receipt=result.output;path=Path(receipt['path'])
        valid=path.is_file() and file_hash(path)==receipt['sha256']
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
            ('Actual selected destination read back and SHA-256 matched the owned source artifact.',) if valid else ())

    if not kernel.registry.lookup(identifier):
        kernel.registry.register(CapabilityDescriptor(identifier,'Export an actual response artifact',category='artifact',
            required_permissions=('file_write',),supports_verification=True,
            input_schema={'type':'object','required':['source','artifact','destination'],'properties':{
                'source':{'type':'object'},'artifact':{'type':'string','maxLength':200},
                'destination':{'type':'string','maxLength':4096}},'additionalProperties':False},
            verification_contract='Existing atomic no-overwrite copy; independent destination hash readback.',timeout=60),
            execute,permission_check=permission,verifier=verify)

    def export_render(args,context):
        from ..media_lab.artifacts import atomic_export,verify_image
        from ..media_lab.storage import file_hash
        receipt=context.metadata.get('response_render')
        if not isinstance(receipt,ResponseRender) or receipt.owner.runtime is not runtime or receipt.owner.conversation_id!=context.conversation_id:
            raise ValueError('An actual native chart capture in this conversation is required.')
        path=receipt.path.resolve();root=(Path(runtime.directory)/'response-cache').resolve()
        if not path.is_relative_to(root) or receipt.format not in {'png','svg','pdf','csv','json'} or path.suffix!='.'+receipt.format or not path.is_file() or path.stat().st_size>32*1024**2:
            raise ValueError('Native chart capture is outside its bounded owner cache.')
        with receipt.owner.using_cancellation(context.cancellation_token):
            for source in receipt.sources or (receipt.source,):receipt.owner.resolve(source)
        if receipt.format=='png':verify_image(path,allow_constant=True)
        elif receipt.format=='svg':
            from xml.etree import ElementTree
            if ElementTree.parse(path).getroot().tag.rsplit('}',1)[-1]!='svg':raise ValueError('Native SVG capture failed readback.')
        elif receipt.format=='pdf':
            try:from pypdf import PdfReader
            except ImportError as exc:raise ValueError('Verified PDF export needs the installed research package extra.') from exc
            if not PdfReader(path).pages:raise ValueError('Native PDF capture has no readable page.')
        elif receipt.format=='json':
            import json
            if not isinstance(json.loads(path.read_text(encoding='utf-8')),dict):raise ValueError('Data export failed JSON readback.')
        elif receipt.format=='csv':
            import csv
            with path.open(encoding='utf-8',newline='') as stream:
                if not next(csv.reader(stream),None):raise ValueError('Data export has no CSV header.')
        return ExecutionResult(TaskStatus.SUCCEEDED,True,atomic_export(path,args['destination'],file_hash(path)),verification_required=True)

    if not kernel.registry.lookup('response.render.export'):
        kernel.registry.register(CapabilityDescriptor('response.render.export','Export actual response data, charts or reports',category='artifact',
            required_permissions=('file_write',),supports_verification=True,timeout=60,
            input_schema={'type':'object','required':['destination'],'properties':{'destination':{'type':'string','maxLength':4096}},'additionalProperties':False},
            verification_contract='Actual native capture decoded, source revision checked, atomic no-overwrite copy and destination hash readback.'),
            export_render,permission_check=permission,verifier=verify)


def capture_data(owner,snapshot,format):
    """Export the bounded source sample, never invent a full-data claim."""
    import csv,json,tempfile
    from dataclasses import replace
    if format not in {'csv','json'}:raise ValueError('Choose CSV or JSON for source data.')
    root=Path(owner.runtime.directory)/'response-cache';root.mkdir(parents=True,exist_ok=True)
    temporary=tempfile.TemporaryDirectory(prefix='data-',dir=root);path=Path(temporary.name)/('data.'+format)
    rows=snapshot.rows[:1000]
    if not rows:temporary.cleanup();raise ValueError('This source has no tabular data to export.')
    try:
        if format=='json':
            path.write_text(json.dumps({'title':snapshot.title,'source':snapshot.source.__dict__,'revision':snapshot.revision,
                'provenance':snapshot.provenance,'units':snapshot.units,'limitation':snapshot.limitation,
                'sample_rows':len(rows),'total_rows':snapshot.data.get('completed_runs',len(rows)),'rows':rows},ensure_ascii=False,allow_nan=False),encoding='utf-8')
        else:
            fields=[k for k in dict.fromkeys(k for row in rows for k in row) if not k.startswith('__source_row_id')][:32]
            def cell(value):
                value=value if type(value) in (int,float) else str(value if value is not None else '')
                return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r')) else value
            with path.open('w',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream);writer.writerow([cell(k+(' ['+snapshot.units[k]+']' if snapshot.units.get(k) else '')) for k in fields])
                for row in rows:writer.writerow([cell(row.get(k)) for k in fields])
        return ResponseRender(owner,replace(snapshot.source,revision=snapshot.revision),path,format,temporary)
    except BaseException:temporary.cleanup();raise
