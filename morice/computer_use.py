"""Observed Windows accessibility controls over the existing PC action contracts.

No coordinates, generated scripts, arbitrary key macros or elevated-process
workarounds. Unsupported accessibility patterns stay explicitly unsupported.
"""
from __future__ import annotations

from collections import deque
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

from .pc_control import (ControlResult,DESKTOP_AUTOMATION_GUIDANCE,
    PermissionCategory,PolicyMode)


class NativeComputerUseAdapter:
    adapter_id='computer_use.windows_uia'
    verbs=frozenset({'inspect','focus','type','set_value','invoke','scroll'})

    def __init__(self,desktop,permissions):
        self.desktop=desktop;self.permissions=permissions

    def supports(self,action):return action.domain=='computer' and action.verb in self.verbs

    def availability(self,action=None):
        available=os.name=='nt' and importlib.util.find_spec('uiautomation') is not None
        return available,'' if available else 'Windows accessibility automation needs Windows and the declared uiautomation provider.'

    def _allowed(self):
        if self.permissions.policy(PermissionCategory.DESKTOP_AUTOMATION)!=PolicyMode.ALLOW:
            raise PermissionError(DESKTOP_AUTOMATION_GUIDANCE)

    def _window(self,target):
        from .action_runtime.desktop import window_values
        target=str(target).strip().casefold()
        if not target:raise ValueError('Which third-party app window should I use?')
        windows=window_values(self.desktop.windows)
        exact=[w for w in windows if target in {str(w['handle']),str(w.get('pid','')),
            str(w.get('title','')).casefold(),Path(w.get('image','')).stem.casefold()}]
        matches=exact or [w for w in windows if target in str(w.get('title','')).casefold()]
        if len(matches)!=1:
            raise ValueError('More than one window matches; specify its window handle.' if matches else 'That app window is not available. Open it first or specify its exact title.')
        if int(matches[0].get('pid',0))==os.getpid():
            raise ValueError('Use MORICE internal navigation and controls for its own interface.')
        return matches[0]

    @staticmethod
    def _identifier(window,control):
        identity=[window['handle'],window['pid'],list(control.GetRuntimeId())]
        return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]

    @staticmethod
    def _value(auto,control):
        if control.IsPassword:return None
        pattern=control.GetPattern(auto.PatternId.ValuePattern)
        return str(pattern.Value)[:4096] if pattern else None

    def _walk(self,auto,root,window,cancel=None):
        queue=deque([(root,0)]);values=[]
        while queue and len(values)<200:
            if cancel is not None:cancel.raise_if_cancelled()
            self._allowed()
            control,depth=queue.popleft()
            if int(control.ProcessId)!=int(window['pid']):continue
            protected=bool(control.IsPassword)
            value={'control_id':self._identifier(window,control),'name':str(control.Name)[:512],
                'automation_id':str(control.AutomationId)[:256],'type':str(control.ControlTypeName),
                'enabled':bool(control.IsEnabled),'offscreen':bool(control.IsOffscreen),
                'protected':protected,'focused':bool(control.HasKeyboardFocus)}
            if not protected and value['type'] in {'EditControl','DocumentControl','ComboBoxControl','SpinnerControl'}:
                value['value']=self._value(auto,control)
            values.append((value,control))
            if depth<8:
                queue.extend((child,depth+1) for child in control.GetChildren()[:100])
        return values

    @staticmethod
    def _select(values,args,verb):
        identifier=str(args.get('control_id',''));name=str(args.get('name',''))
        automation=str(args.get('automation_id',''))
        if identifier:
            matches=[item for item in values if item[0]['control_id']==identifier]
        elif name or automation:
            matches=[item for item in values if (not name or item[0]['name'].casefold()==name.casefold())
                and (not automation or item[0]['automation_id']==automation)]
        elif verb in {'type','set_value'}:
            matches=[item for item in values if item[0].get('value') is not None and item[0]['enabled'] and not item[0]['offscreen']]
        else:raise ValueError('Inspect the app first and specify the accessible control name or ID.')
        if len(matches)!=1:raise ValueError('The control is missing, stale or ambiguous. Inspect the app again and choose one control.')
        value,control=matches[0]
        if value['protected']:raise PermissionError('Password and protected controls are not available to desktop automation.')
        if not value['enabled'] or value['offscreen']:raise ValueError('The selected control is disabled or offscreen.')
        if args.get('expected_name') is not None and value['name']!=args['expected_name']:
            raise ValueError('The observed control changed since it was selected. Inspect it again.')
        return value,control

    def _access(self,target,args,verb,operation=None,cancel=None):
        self._allowed()
        if not self.availability()[0]:raise RuntimeError(self.availability()[1])
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            window=self._window(target)
            root=auto.ControlFromHandle(int(window['handle']))
            if root is None or int(root.ProcessId)!=int(window['pid']):raise ValueError('The app window identity changed.')
            values=self._walk(auto,root,window,cancel)
            if verb=='inspect':
                return {'window':window,'controls':[v for v,_ in values],
                    'bounded':True,'maximum_controls':200,'maximum_depth':8}
            value,control=self._select(values,args,verb)
            if operation is not None:
                self._allowed()
                if cancel is not None:cancel.raise_if_cancelled()
                operation(auto,control,value)
            scroll=control.GetPattern(auto.PatternId.ScrollPattern) if verb=='scroll' else None
            # Return primitives only; COM controls never cross worker threads.
            return {'window':window,'control':{**value,'value':self._value(auto,control),
                'focused':bool(control.HasKeyboardFocus),
                **({'horizontal_scroll':float(scroll.HorizontalScrollPercent),
                    'vertical_scroll':float(scroll.VerticalScrollPercent)} if scroll else {})}}

    def observe(self,inputs,verb):
        args=dict(inputs.get('arguments',{}))
        expected=args.get('expected',{})
        if verb=='invoke' and expected:
            args={**args,**expected};args.pop('control_id',None)
        return self._access(inputs.get('target',''),args,verb)

    def execute(self,action,context):return self._execute(action,context,None)

    def execute_attempt(self,action,context,execution_context):
        return self._execute(action,context,execution_context.cancellation_token)

    def _execute(self,action,context,cancel):
        args=dict(action.arguments)
        def perform(auto,control,before):
            if action.verb in {'type','set_value'}:
                text=args.get('text')
                if not isinstance(text,str) or len(text)>4096 or any(ord(c)<32 and c not in '\n\t\r' for c in text):
                    raise ValueError('Text input must be bounded literal text, not key macros or control codes.')
                pattern=control.GetPattern(auto.PatternId.ValuePattern)
                if not pattern or pattern.IsReadOnly:raise ValueError('This control has no writable accessibility value pattern.')
                current=str(pattern.Value)
                if len(current)>4096:raise ValueError('The existing field exceeds this bounded text adapter.')
                pattern.SetValue(current+text if action.verb=='type' else text,waitTime=0)
            elif action.verb=='focus':control.SetFocus()
            elif action.verb=='invoke':
                expected=args.get('expected')
                if not isinstance(expected,dict) or not expected.get('name') or set(expected)-{'name','automation_id','value'}:
                    raise ValueError('Invoking a control needs an explicit observable postcondition: expected control name and optional value.')
                pattern=control.GetPattern(auto.PatternId.InvokePattern)
                if not pattern:raise ValueError('This control has no accessibility invoke pattern.')
                pattern.Invoke(waitTime=0)
            elif action.verb=='scroll':
                pattern=control.GetPattern(auto.PatternId.ScrollPattern)
                if not pattern:raise ValueError('This control has no accessibility scroll pattern.')
                direction=args.get('direction')
                amounts={'up':(2,1),'down':(2,4),'left':(1,2),'right':(4,2)}
                if direction not in amounts:raise ValueError('Choose up, down, left or right.')
                pattern.Scroll(*amounts[direction],waitTime=0)
            else:raise ValueError('Unsupported desktop action.')
        output=self._access(action.target,args,action.verb,None if action.verb=='inspect' else perform,cancel)
        return ControlResult(action.action_id,action.tool_id,True,False,
            'Accessibility operation executed; independent observation determines its result.',output=output,adapter_id=self.adapter_id)


def register_computer_actions(runtime,adapter):
    """Independent observations plug into the existing VerifiedActionRuntime."""
    from .action_runtime.contracts import ActionBinding,ActionMethod,Observation
    from .kernel import VerificationResult,VerificationStatus
    for verb in sorted(adapter.verbs):
        def desired(inputs,expected,v=verb):
            args=inputs.get('arguments',{})
            return {'inputs':inputs,'verb':v,'text':args.get('text',''),'expected':args.get('expected',{}),
                    'direction':args.get('direction','')}
        def observe(spec,context,result=None,before=None,v=verb):
            context.cancellation_token.raise_if_cancelled()
            return Observation(spec.action_id,'Windows UI Automation fresh readback',adapter.observe(spec.desired_state['inputs'],v))
        def verify(spec,observation,before,v=verb):
            state=observation.state;control=state.get('control',{})
            if v=='inspect':valid=bool(state.get('window')) and bool(state.get('controls'))
            elif v=='focus':valid=control.get('focused') is True
            elif v in {'type','set_value'}:
                previous=(before.state.get('control',{}).get('value') or '') if before else ''
                wanted=previous+spec.desired_state['text'] if v=='type' else spec.desired_state['text']
                valid=control.get('value')==wanted
            elif v=='invoke':
                wanted=spec.desired_state['expected']
                valid=bool(wanted) and all(control.get(k)==value for k,value in wanted.items())
            elif v=='scroll':
                direction=spec.desired_state['direction']
                key='horizontal_scroll' if direction in {'left','right'} else 'vertical_scroll'
                current=control.get(key)
                old=before.state.get('control',{}).get(key) if before else None
                boundary=0 if direction in {'left','up'} else 100
                valid=current is not None and current>=0 and (current==boundary or old is not None and
                    (current<old if direction in {'left','up'} else current>old))
            else:valid=False
            return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.INCONCLUSIVE,
                ('Fresh accessibility state matches the requested postcondition.',) if valid else (),
                '' if valid else 'The requested accessible state has not been independently observed.')
        runtime.register('computer.'+verb,ActionBinding(ActionMethod.ACCESSIBILITY,desired,observe,verify,
            idempotent=verb in {'focus','set_value'}))


def parse_computer_request(text):
    """Only explicit app-control requests; quoted source prose is not authority."""
    clean=str(text or '').strip()
    if len(clean)>8000:return None
    clean=re.sub(r'^(?:please|can you|could you)\s+','',clean,flags=re.I).strip(' .')
    match=re.fullmatch(r'(?:inspect|show|list)(?: the)? (?:controls|buttons|fields) (?:in|of|for) (.+)',clean,re.I)
    if not match:match=re.fullmatch(r'inspect (?:the )?(?:app|window) (.+)',clean,re.I)
    if match:return 'inspect',match[1].strip('"'),{}
    match=re.fullmatch(r'(?:type|enter|append) "([\s\S]{0,4096})" (?:into|in) (.+)',clean,re.I)
    if match:return 'type',match[2].strip('"'),{'text':match[1]}
    match=re.fullmatch(r'(?:set|replace) (?:the )?(?:field|control) "(.{1,256})" in (.+?) (?:to|with) "([\s\S]{0,4096})"',clean,re.I)
    if match:return 'set_value',match[2].strip('"'),{'name':match[1],'text':match[3]}
    match=re.fullmatch(r'(?:click|press|invoke) "(.{1,256})" in (.+?) (?:until|and check for) "(.{1,256})"(?: is visible)?',clean,re.I)
    if match:return 'invoke',match[2].strip('"'),{'name':match[1],'expected':{'name':match[3]}}
    match=re.fullmatch(r'focus (?:the )?(?:field|control) "(.{1,256})" in (.+)',clean,re.I)
    if match:return 'focus',match[2].strip('"'),{'name':match[1]}
    match=re.fullmatch(r'scroll "(.{1,256})" (up|down|left|right) in (.+)',clean,re.I)
    if match:return 'scroll',match[3].strip('"'),{'name':match[1],'direction':match[2].casefold()}
    return None


def requests_desktop_automation(text):
    lead=str(text or '').strip().split('\n',1)[0]
    if parse_computer_request(text):return True
    return bool(re.match(r'^(?:please\s+)?(?:take (?:control of|over) (?:my |the )?(?:pc|computer)|'
        r'(?:automate|operate|control) (?:my |the )?(?:pc|computer|desktop|app|browser)|'
        r'(?:click|double.click|drag|inspect the app)\b|(?:type|enter)\s+["“]|'
        r'press\s+(?:(?:the|a)\s+)?(?:key|button|control|shortcut|["“])|'
        r'(?:use|open|launch) .{1,100}? (?:to|and then|then|and) (?:click|type|fill|enter|draw|edit|save|upload|download|send)\b)',lead,re.I))
