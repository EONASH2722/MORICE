"""Small deterministic bindings inside the existing NLUI, not another router."""
from ..nlui.contracts import IntentResolution,Operation
from ..kernel import CapabilityDescriptor,ExecutionResult,ErrorCode,VerificationResult,VerificationStatus

COMMANDS={
 'analyze this file':'inspect','analyse this file':'inspect','analyze this unknown file':'inspect',
 'analyze this encrypted archive':'inspect','inspect this binary format':'inspect','decode this file':'decode',
 'tell me whether this file is encrypted or simply encoded':'inspect','identify the language in this document':'inspect',
 'try the recovery hints i provided':'recover','recover this file':'recover','decrypt this archive using my supplied password':'recover',
 'estimate whether password recovery is feasible':'estimate','check whether i have a matching recovery key':'estimate',
 'cancel recovery':'cancel','cancel file recovery':'cancel','show what has been tested':'status','show the security report':'status',
 'show my authorized android debugging devices':'devices','show my authorized android devices':'devices',
 'run the vox hackathon challenge':'vox','run the local security challenge':'challenge','run the vox challenge':'vox',
 'run the owned messaging challenge':'challenge','audit this project':'audit','scan this source project':'audit',
 'inspect paired bluetooth devices':'bluetooth','export the recovered files':'export',
 'open security lab':'open','open private security lab':'open','open file forensics':'open',
}

def resolve(clean,context):
    operation=COMMANDS.get(clean)
    if not operation:return IntentResolution()
    return IntentResolution(operations=(Operation('nlui.security.lab',{'action':operation}),),route='security_lab')

def register(controller):
    def execute(args,context):
        # UI port supplies current selection, transient secret inputs and existing
        # one-use approvals. A language model cannot invent credential material.
        port=controller._port(context)
        def action():
            window=port._owner()
            window.navigate('security');workspace=window.routes['security'];workspace.tabs.setCurrentWidget(workspace.lab_panel)
            panel=workspace.lab_panel
            if args['action']=='open':return {'message':'Security Lab is open. Select your local file or owned test target.'}
            return panel.prepare_nlui(args['action'],context.conversation_id)
        value=port.bridge.invoke_on_ui(action,cancellation=context.cancellation_token)
        if value.get('question'):return ExecutionResult.failure(ErrorCode.INVALID_INPUT,value['question'])
        if value.get('job_id'):
            if args['action']=='cancel':controller.runtime.security_lab.cancel(value['job_id'])
            result=controller.runtime.security_lab.run(args['action'],value['job_id'],approval_token=value.get('approval_token',''),cancellation=context.cancellation_token,progress=context.progress,conversation=context.conversation_id)
            return result
        from ..nlui.domains import success
        return success(value['message'])
    controller.kernel.registry.register(CapabilityDescriptor('nlui.security.lab','Use Security Lab with actual selected inputs',provider='morice-security-lab',category='security',
        input_schema={'type':'object','required':['action'],'properties':{'action':{'type':'string','enum':sorted(set(COMMANDS.values()))}},'additionalProperties':False},
        supports_verification=True,supports_cancellation=True,timeout=1215,natural_language_intents=tuple(COMMANDS),
        verification_contract='Read back the selected conversation-owned job receipt and actual artifact hashes; failed recovery is never inferred successful.',
        ui_action='Existing Security Lab target and transient secret controls'),execute,
        verifier=lambda result,expected,context: controller.runtime.security_lab.verify(result,context) if (result.output or {}).get('lab_job_id') else
            VerificationResult(VerificationStatus.VERIFIED,('Existing native Security Lab workspace was opened.',)))
