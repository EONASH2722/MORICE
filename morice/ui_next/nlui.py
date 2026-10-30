"""Native first-party capability port, sharing the existing queued UI bridge."""
from __future__ import annotations

import math
import hashlib
import uuid
import weakref
import time
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QMessageBox

from ..nlui.contracts import ActiveContext
from .appearance_profile import AppearanceProfile


class WindowCapabilityPort:
    def __init__(self,window):
        self.window_id='morice-window-'+uuid.uuid4().hex
        self._window=weakref.ref(window)
        self.bridge=window.ui_bridge
        self._appearance_undo={}
        self._selections={}

    def context(self):
        window=self._owner()
        workspace=(getattr(window,'_voice_context_route','') if window.chat_mode=='voice' else '') or window.active_route
        last=window.history[-1] if window.history else {}
        turn_key=last.get('message_id') or (str(len(window.history))+':'+hashlib.sha256(str(last.get('content','')).encode()).hexdigest()[:16])
        selected=[row for row in self._selections.get(window._chat_id,()) if row.get('kind')!='security_finding' or row.get('turn_key')==turn_key]
        for row in reversed(window._message_rows):
            from ..pyside_app import ChatBubble
            bubble=row.findChild(ChatBubble);host=getattr(bubble,'_response_host',None) if bubble is not None else None
            if host is not None and not host.closed and host.plan.conversation_id==window._chat_id:
                selected.append({'kind':'response','id':host.plan.id});break
        view=window.routes.get('research')
        if workspace=='research' and view is not None:
            identifier=view.selected_id()
            if identifier:selected=[{'kind':'experiment','id':identifier}]
        return ActiveContext(window._chat_id,self.window_id,workspace,
            str(window.project_folder or ''),str(window._research_project_id or ''),tuple(selected),last_turn_key=turn_key)

    def remember_result(self,result):
        window=self._owner();selected=[]
        for execution in result.executions:
            if not execution.get('success'):continue
            output=execution.get('output') or {}
            for reference in output.get('source_refs',()):
                if reference.get('kind') in {'experiment','research_project','research_record','spatial_context'}:selected.append(dict(reference))
            if output.get('generation_id'):selected.append({'kind':'generation','id':output['generation_id']})
            if output.get('finding'):
                identifier=window.history[-1].setdefault('message_id',uuid.uuid4().hex) if window.history and window.history[-1].get('role')=='assistant' else ''
                selected.append({'kind':'security_finding','id':output['finding']['finding_id'],'turn_key':identifier})
            for item in output.get('media_items',()):
                if item.get('id'):selected.append({'kind':'generation','id':item['id']})
        if selected:
            self._selections[window._chat_id]=selected[-20:]
            if window._session_enabled:window.runtime.chat_history.put_ui_state(window._chat_id,'nlui_selection',{'selected':selected[-20:]})

    def restore_selection(self):
        window=self._owner();value=window.runtime.chat_history.get_ui_state(window._chat_id,'nlui_selection') or {}
        rows=value.get('selected',[])
        if isinstance(rows,list):self._selections[window._chat_id]=[r for r in rows[:20] if isinstance(r,dict)
            and r.get('kind') in {'experiment','research_project','research_record','generation','spatial_context','security_finding'} and isinstance(r.get('id'),str)]

    def _owner(self):
        window=self._window()
        if window is None or self.bridge._closed:raise RuntimeError('The requested MORICE window is closed.')
        return window

    def execute(self,capability,arguments,context):
        return self.bridge.invoke_on_ui(lambda:self._execute(capability,arguments,context.conversation_id),
            cancellation=context.cancellation_token,timeout=30 if capability in {'host.confirm','file.destination'} else 5)

    def _execute(self,capability,arguments,conversation_id=''):
        window=self._owner()
        if conversation_id and conversation_id!=window._chat_id:raise RuntimeError('The active conversation changed before this UI action. Resend it in the intended chat.')
        if capability=='file.destination':
            from PySide6.QtWidgets import QFileDialog
            from PySide6.QtCore import QTimer
            dialog=QFileDialog(window,'Export actual file');dialog.setOption(QFileDialog.DontUseNativeDialog,True)
            dialog.setAcceptMode(QFileDialog.AcceptSave);dialog.selectFile(arguments['name'])
            dialog.setDefaultSuffix(Path(arguments['name']).suffix.lstrip('.'))
            timer=QTimer(dialog);timer.setSingleShot(True);timer.timeout.connect(dialog.reject);timer.start(29000)
            return {'destination':dialog.selectedFiles()[0] if dialog.exec()==QFileDialog.Accepted and dialog.selectedFiles() else ''}
        if capability=='project.catalog':
            rows=list(window.workspace_state.recent_projects)
            if window.project_folder and Path(window.project_folder).is_dir() and not any(r['id']==str(Path(window.project_folder).resolve()) for r in rows):
                window.workspace_state.add_recent_project(window.project_folder);rows=list(window.workspace_state.recent_projects)
            return {'projects':rows}
        if capability=='project.build_catalog':
            owner=window.runtime.autonomous_builder.project_runtime
            with owner._lock:identifiers=list(owner._sessions)
            if window._last_project_build_id:identifiers.append(window._last_project_build_id)
            rows=[]
            for identifier in dict.fromkeys(identifiers):
                try:session=owner.load(identifier)
                except (OSError,ValueError):continue
                if window.project_folder and Path(session.project_root).resolve()!=Path(window.project_folder).resolve():continue
                rows.append({'id':session.session_id,'title':session.user_goal[:160],'updated':session.updated_at})
            return {'builds':rows,'active_id':window._project_build_id or window._last_project_build_id}
        if capability=='project.show_build':
            session=window.runtime.autonomous_builder.project_runtime.load(arguments['session_id'])
            if not window.project_folder or Path(session.project_root).resolve()!=Path(window.project_folder).resolve():
                raise ValueError('Select the saved build\'s project folder first.')
            window._last_project_build_id=session.session_id;window.changes_resume_btn.setEnabled(True)
            window.navigate('projects')
            if window.chat_mode!='voice':window._set_chat_mode('project')
            return {'session_id':session.session_id,'root':session.project_root}
        if capability=='project.select':
            window._select_existing_project_folder(arguments['root']);window.navigate('projects')
            if window.chat_mode!='voice':window._set_chat_mode('project')
            return {'root':window.project_folder}
        if capability=='project.prepare_proposal':
            if Path(window.project_folder).resolve()!=Path(arguments['root']).resolve():
                raise ValueError('The selected project folder changed. Resend the request for its current folder.')
            if window._project_build_id or window.pending_project_patch:
                return {'ready':False,'reason':'Finish, cancel or reject the existing project build or pending patch before preparing another.'}
            return {'ready':True,'model_id':window._configure_project_backend()}
        if capability=='project.review':
            import copy
            from ..unified_intelligence import PermissionState
            if Path(window.project_folder).resolve()!=Path(arguments['root']).resolve() or window._project_build_id or window.pending_project_patch:
                raise ValueError('The project or review state changed. Finish the current work before preparing a new patch.')
            session=window.runtime.autonomous_builder.project_runtime.load(arguments['session_id'])
            if Path(session.project_root).resolve()!=Path(arguments['root']).resolve() or not session.changes:
                raise ValueError('The actual Builder proposal does not match this project.')
            window.pending_project_patch={'root':session.project_root,'changes':copy.deepcopy(session.changes)}
            window._pending_build_session=session
            window.navigate('projects')
            if window.chat_mode!='voice':window._set_chat_mode('project')
            window._on_project_changes_ready('Proposed source changes; review before applying.',arguments['diff_html'])
            auto=(window.project_access=='full' and window.runtime.kernel.permissions.controller.state('file_write')
                not in {PermissionState.DENIED,PermissionState.UNSUPPORTED,PermissionState.OS_REQUIRED})
            if auto:window._apply_pending_project_patch()
            return {'session_id':session.session_id,'root':session.project_root,'auto_apply_started':auto}
        if capability in {'response.inspect','response.apply','response.capture','response.report_info','response.report_capture','response.source_owner'}:
            from ..pyside_app import ChatBubble
            from ..rich_response import Component
            host=None
            for row in reversed(window._message_rows):
                bubble=row.findChild(ChatBubble);candidate=getattr(bubble,'_response_host',None) if bubble is not None else None
                if candidate is not None and not candidate.closed and candidate.plan.conversation_id==window._chat_id:host=candidate;break
            if host is None:raise ValueError('Open the interactive result in this conversation first.')
            if capability=='response.report_info':return {'plan':host.plan.to_dict(),'owner':host.sources}
            if capability=='response.source_owner':
                if host.plan.id!=arguments['plan_id']:raise ValueError('The displayed source changed before export.')
                return host.sources
            if capability=='response.report_capture':
                from .rich_export import capture_report
                return capture_report(host,arguments['plan'],arguments['snapshots'])
            if capability=='response.inspect':
                components=[c for c in host.plan.components if c.kind in arguments['kinds']]
                if arguments.get('deduplicate_source'):
                    unique={}
                    for component in components:
                        if component.source:unique.setdefault((component.source.kind,component.source.id,component.source.revision),component)
                    components=list(unique.values())
                reference=arguments.get('reference','')
                if reference:components=[c for c in components if reference.casefold() in {c.id.casefold(),c.title.casefold()}]
                if not components:raise ValueError('The latest interactive result has no matching control. Open the intended result first.')
                if len(components)>1:return {'choices':[{'id':c.id,'label':c.title or c.kind} for c in components]}
                return {'plan_id':host.plan.id,'component':asdict(components[0])}
            if host.plan.id!=arguments['plan_id']:raise ValueError('The displayed result changed. Resend the control request for the current result.')
            component=Component.from_dict(arguments['component'])
            current=next((c for c in host.plan.components if c.id==component.id),None)
            if capability=='response.capture':
                if current!=component:raise ValueError('The chart changed before export. Try again with the current chart.')
                view=host.sections[component.id]['view']
                if component.kind!='chart' or view is None:raise ValueError('Expand the actual chart in this conversation before exporting it.')
                from .rich_response import capture_chart
                return capture_chart(view.context,view.canvas,arguments['format'])
            updated=Component.from_dict(arguments['updated'])
            if current!=component or updated.id!=component.id or updated.source!=component.source or updated.kind!=component.kind:
                raise ValueError('The component or its inputs changed before applying this display control. Try again.')
            state=host.sections[component.id];host.select_section(component.id);host.release(state,preserve_height=False)
            host.update_component(component.id,config=updated.config);state['error']=False;state['toggle'].setChecked(True)
            window.navigate('chats');window.scroll.ensureWidgetVisible(state['toggle']);host.schedule_visibility()
            return {'plan_id':host.plan.id,'conversation_id':window._chat_id,'component':asdict(updated)}
        if capability=='spatial.present':
            if window.settings.get('nlui_auto_open','true')=='true':window.navigate('spatial')
            if 'spatial' in window.routes:window.routes['spatial'].set_context(arguments['context'])
            return {'context':arguments['context']}
        if capability=='host.confirm':
            from PySide6.QtCore import QTimer
            title=str(arguments.get('title','Confirm requested action'))[:100]
            details=str(arguments['details'])[:6000]
            dialog=QMessageBox(window);dialog.setWindowTitle(title);dialog.setTextFormat(Qt.PlainText)
            dialog.setText(details);dialog.setStandardButtons(QMessageBox.Yes|QMessageBox.No);dialog.setDefaultButton(QMessageBox.No)
            timer=QTimer(dialog);timer.setSingleShot(True);timer.timeout.connect(dialog.reject);timer.start(29000)
            return {'confirmed':dialog.exec()==QMessageBox.Yes}
        if capability=='ui.preference':
            key=arguments['key'];value=arguments['value']
            flags={'precision','math_steps','auto_open','show_plan','automatic_model_selection','personal_memory_enabled','chat_memory_enabled','project_memory_enabled'}
            if key in flags and type(value) is not bool:raise ValueError('That preference needs true or false.')
            if key in {'preferred_name','form_of_address'} and (not isinstance(value,str) or not 1<=len(value)<=80 or any(ord(c)<32 for c in value)):
                raise ValueError('Use a name or form of address of 1–80 plain characters.')
            if key=='precision':window._set_precision_state(value)
            elif key=='math_steps':window.math_steps_mode=value
            elif key=='presentation':
                field=window.routes['settings'].control_settings.presentation;index=field.findData(value)
                if index<0:raise ValueError('Unknown response presentation.')
                field.setCurrentIndex(index)
            elif key in {'auto_open','show_plan'}:
                window.routes['settings'].control_settings.flags['nlui_'+key].setChecked(value)
            elif key=='automatic_model_selection':window.routes['settings'].fast_model_settings.automatic.setChecked(value)
            elif key in {'personal_memory_enabled','chat_memory_enabled','project_memory_enabled'}:
                window.routes['settings'].memory_settings.flags[key].setChecked(value)
            elif key in {'preferred_name','form_of_address'}:
                (window.name_input if key=='preferred_name' else window.title_input).setText(value);window.on_save_identity()
            else:raise ValueError('That preference is not exposed for natural-language mutation.')
            return {'message':f'Updated {key.replace("_"," ")}.','key':key,'value':value}
        if capability=='ui.undo_appearance':
            value=self._appearance_undo.get(conversation_id)
            if not value or value['expires']<=time.time():raise ValueError('No recent appearance change is available to undo in this chat.')
            if window.theme_engine.profile.to_dict()!=value['after']:
                raise ValueError('Appearance changed again since that request. I cannot safely restore an older profile over those changes.')
            window.theme_engine.apply_profile(AppearanceProfile.from_dict(value['before']))
            self._appearance_undo.pop(conversation_id,None)
            return {'message':'Restored the previous appearance.','changes':value['before']}
        if capability=='research.select':
            window.navigate('research')
            view=window.routes.get('research')
            if view is None:raise RuntimeError('The Research workspace could not open.')
            identifier=arguments['project_id'];index=view.projects.findData(identifier)
            if index<0:view.projects.addItem(arguments['objective'],identifier);index=view.projects.findData(identifier)
            view.projects.setCurrentIndex(index);view.project_id=identifier
            window._research_project_id=identifier
            view.refresh()
            return {'project_id':identifier}
        if capability=='history.open':
            previous_busy=window.is_busy;window.is_busy=False
            try:window._restore_history_chat(arguments['chat_id']);window.navigate('chats')
            finally:window.is_busy=previous_busy
            return {'chat_id':window._chat_id}
        if capability=='ui.navigate':
            route=arguments['route']
            window.navigate(route)
            return {'message':f'{route.title()} is selected for voice commands.' if window.chat_mode=='voice' and route!='voice' else f'Opened {"Core" if route=="home" else route.title()}.','route':route}
        if capability=='ui.settings':
            category=arguments['category'];settings=window.routes['settings']
            matches=[i for i in range(settings.list.count()) if settings.list.item(i).text().casefold()==category.casefold()]
            if len(matches)!=1:raise ValueError('That settings category is not available.')
            settings.search.clear();settings.list.setCurrentRow(matches[0]);window.navigate('settings')
            return {'message':f'Settings → {category} is selected for voice commands.' if window.chat_mode=='voice' else f'Opened Settings → {category}.','category':category}
        if capability=='ui.appearance':
            before=window.theme_engine.profile.to_dict()
            changes=dict(arguments.get('changes',{}));relative=dict(arguments.get('relative',{}))
            ranges={'glow':(0,1),'font_scale':(.8,1.8),'core_scale':(.5,1.5)}
            for key,delta in relative.items():
                if key not in ranges or key not in before:raise ValueError('That relative appearance control is not exposed by the current theme.')
                if type(delta) not in (int,float) or not math.isfinite(delta):raise ValueError('Relative appearance changes must be finite numbers.')
                low,high=ranges[key];changes[key]=max(low,min(high,before[key]+delta))
            if not changes:raise ValueError('Specify an appearance setting to change.')
            requested=AppearanceProfile.from_dict({**before,**changes})
            window.theme_engine.apply_profile(requested)
            self._appearance_undo[conversation_id]={'before':before,'after':requested.to_dict(),'expires':time.time()+900}
            if len(self._appearance_undo)>32:self._appearance_undo.pop(next(iter(self._appearance_undo)))
            return {'message':'Appearance updated: '+', '.join(k.replace('_',' ') for k in changes)+'.',
                'changes':{key:getattr(requested,key) for key in changes},'before':before}
        if capability=='ui.window':
            action=arguments['action']
            if action=='maximize':window.showMaximized()
            elif action=='minimize':window.showMinimized()
            elif action=='restore':window.showNormal()
            elif action=='focus_chat':window.navigate('chats');window.input.setFocus()
            elif action=='resize':
                width=arguments.get('width');height=arguments.get('height')
                if type(width) is not int or type(height) is not int:raise ValueError('Specify both window width and height in pixels.')
                if not 720<=width<=7680 or not 500<=height<=4320:raise ValueError('Requested window dimensions exceed the supported range.')
                window.showNormal();window.resize(width,height)
            elif action=='monitor':
                index=arguments.get('monitor');screens=QApplication.screens()
                if type(index) is not int or not 0<=index<len(screens):raise ValueError('That monitor is not connected.')
                window.windowHandle().setScreen(screens[index]);window.move(screens[index].availableGeometry().topLeft())
            else:raise ValueError('Unsupported window action.')
            return {'message':f'MORICE window: {action.replace("_"," ")}.','action':action}
        raise ValueError('Unknown first-party UI capability.')

    def verify(self,capability,arguments,output,context):
        return self.bridge.invoke_on_ui(lambda:self._verify(capability,arguments,output),cancellation=context.cancellation_token)

    def _verify(self,capability,arguments,output):
        window=self._owner()
        if capability=='response.apply':
            if window._chat_id!=output['conversation_id']:return False
            from ..rich_response import Component
            expected=Component.from_dict(output['component'])
            return any(not host.closed and host.plan.id==output['plan_id'] and expected in host.plan.components for host in window._rich_hosts)
        if capability=='project.select':
            return (window.active_route=='projects' and Path(window.project_folder).resolve()==Path(arguments['root']).resolve()
                and window.project_folder_input.text()==window.project_folder)
        if capability=='project.review':
            pending=window._pending_build_session
            identifier=output['session_id']
            return (Path(window.project_folder).resolve()==Path(output['root']).resolve()
                and (pending is not None and pending.session_id==identifier and bool(window.pending_project_patch)
                    or identifier in {window._project_build_id,window._last_project_build_id}))
        if capability=='project.show_build':
            return window._last_project_build_id==output['session_id'] and Path(window.project_folder).resolve()==Path(output['root']).resolve()
        if capability=='ui.preference':
            key=output['key'];value=output['value']
            actual={'precision':window.precision_mode,'math_steps':window.math_steps_mode,
                'presentation':window.settings.get('response_presentation','auto'),
                'auto_open':window.settings.get('nlui_auto_open','true')=='true',
                'show_plan':window.settings.get('nlui_show_plan','true')=='true',
                'automatic_model_selection':window.settings.get('automatic_model_selection','true')=='true',
                'preferred_name':window.preferred_name,'form_of_address':window.user_title}
            actual.update({k:window.settings.get(k,'false')=='true' for k in ('personal_memory_enabled','chat_memory_enabled','project_memory_enabled')})
            if actual.get(key)!=value:return False
            if window._session_enabled and key!='math_steps':
                from ..settings import load_settings
                setting={'precision':'precision_mode','presentation':'response_presentation','auto_open':'nlui_auto_open',
                    'show_plan':'nlui_show_plan','automatic_model_selection':'automatic_model_selection',
                    'preferred_name':'preferred_name','form_of_address':'user_title',
                    'personal_memory_enabled':'personal_memory_enabled','chat_memory_enabled':'chat_memory_enabled','project_memory_enabled':'project_memory_enabled'}[key]
                expected=str(value).lower() if type(value) is bool else value
                return load_settings().get(setting)==expected
            return True
        if capability=='research.select':
            view=window.routes.get('research')
            return (window.active_route=='research' and view is not None and view.project_id==arguments['project_id']
                and view.projects.currentData()==arguments['project_id'])
        if capability=='history.open':return window._chat_id==arguments['chat_id'] and window.active_route=='chats'
        if capability=='ui.navigate':
            route=arguments['route']
            return window.active_route==route and window.route_stack.currentWidget() is window.routes.get(route)
        if capability=='ui.settings':
            settings=window.routes['settings'];item=settings.list.currentItem()
            return (window.active_route=='settings' and item is not None and item.text().casefold()==arguments['category'].casefold()
                and settings.stack.currentWidget() is settings.categories.get(item.text()))
        if capability in {'ui.appearance','ui.undo_appearance'}:
            current=window.theme_engine.profile.to_dict();saved=window.theme_engine.store.load().to_dict()
            return all(current.get(k)==v==saved.get(k) for k,v in output['changes'].items())
        if capability=='ui.window':
            action=arguments['action']
            return (window.isMaximized() if action=='maximize' else window.isMinimized() if action=='minimize'
                else not window.isMaximized() and not window.isMinimized() if action=='restore'
                else window.active_route=='chats' and window.input.hasFocus() if action=='focus_chat'
                else window.width()==arguments['width'] and window.height()==arguments['height'] if action=='resize'
                else window.screen() is QApplication.screens()[arguments['monitor']] if action=='monitor' else False)
        return False
