"""Opt-in Windows UI evidence probe, restricted to a caller-owned test profile.

Real model/STT/TTS components and real pixels; gestures are delivered to the
production controller by this driver, not claimed as human hardware input.
"""
def run(output):
    import io,json,math,os,sys,threading,time,traceback
    from pathlib import Path
    from dataclasses import replace
    from unittest.mock import patch
    if not os.getenv('MORICE_RUNTIME_DIR') or not os.getenv('APPDATA'):
        raise RuntimeError('Helper validation requires an isolated APPDATA and runtime.')
    from PySide6.QtCore import Qt,QTimer,QPoint
    from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel
    from . import settings
    from .config import TTSConfig
    from .local_speech_provider import WindowsSpeechProvider
    from .runtime_services import get_runtime_services
    from .pyside_app import create_application_window
    from .wake_runtime import set_app_session_active
    from .helper_selection import physical_monitors
    directory=Path(output);directory.mkdir(parents=True,exist_ok=True)
    whisper_model=os.getenv('MORICE_PROBE_WHISPER_MODEL','')
    spoken_prompt=os.getenv('MORICE_PROBE_PROMPT','What is the capital of France?')
    settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','tts_provider':'local',
        'stt_enabled':'true','stt_provider':'whisper' if whisper_model else 'vosk','stt_autocorrect':'true' if whisper_model else 'false',
        'stt_accuracy_model_path':whisper_model,'pet_enabled':'false',
        'stt_max_listen_seconds':'20'})
    if QApplication.instance() is None:QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    runtime=get_runtime_services();window=create_application_window(runtime,runtime.start())
    set_app_session_active(True)
    helper=window.background_helper;helper.update(enabled=True,circle_enabled=True,screen_capture=True,animation=True,auto_hide=False,pause_fullscreen=False)
    helper.preferences=replace(helper.preferences,wake_enabled=False)
    record={'scope':'Actual Windows UI, real captured pixels, existing vision/model inference. Driver-controlled gesture, not physical middle mouse. Synthesized speech PCM, not physical microphone.',
        'frozen':bool(getattr(sys,'frozen',False)),'pid':os.getpid(),'evidence':[],'failures':[]}
    def snap(widget,name):
        path=directory/(name+'.png');widget.grab().save(str(path));record['evidence'].append(str(path))
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:app.processEvents();time.sleep(.01)
    def wait(predicate,seconds=90):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            app.processEvents()
            if predicate():return True
            time.sleep(.02)
        return False
    target=QWidget();target.setWindowTitle('MORICE selection acceptance target')
    target.setWindowFlag(Qt.WindowStaysOnTopHint)
    target.setAttribute(Qt.WA_ShowWithoutActivating);window.setAttribute(Qt.WA_ShowWithoutActivating)
    target.setStyleSheet('background:#faf9ff;color:#151321;');target.resize(730,380)
    area=QApplication.primaryScreen().geometry();target.move(area.center().x()-365,area.top())
    layout=QVBoxLayout(target);layout.setContentsMargins(36,35,36,35)
    label=QLabel('A Python list has three items.\nValid indices are 0, 1 and 2.\n\nIndexError: list index out of range')
    label.setStyleSheet('font-family:Segoe UI;font-size:25px;');layout.addWidget(label)
    window.show();pump(1);snap(window,'01-main-window')
    try:
        window.close();pump(.3)
        assert not window.isVisible() and runtime.started and window.wake_signal_timer.isActive()
        record['hidden_resident']=helper.diagnostics();record['tray_visible']=helper.tray.isVisible()
        target.show();pump(.5)
        from .speech_runtime import SpeechInputConfig
        pcm=b''.join(WindowsSpeechProvider().stream_audio([spoken_prompt],TTSConfig(provider='local',output_format='pcm_16000'),threading.Event()))
        class Audio:
            def __init__(self,payload):self.payload=payload+b'\0'*48000;self.position=0;self.stopped=False
            def start(self):pass
            def read(self,timeout):
                if self.stopped:return None
                value=self.payload[self.position:self.position+4000];self.position+=len(value);time.sleep(.04)
                return value or b'\0'*1280
            def stop(self):self.stopped=True
            def abort(self):self.stopped=True
        supplied=[False]
        def audio_factory(config):
            payload=pcm if not supplied[0] else b'';supplied[0]=True;return Audio(payload)
        runtime.speech_input._audio_factory=audio_factory
        runtime.speech_input.configure(SpeechInputConfig(enabled=True,provider='whisper' if whisper_model else 'vosk',accuracy_model_path=whisper_model,autocorrect=bool(whisper_model),max_listen_seconds=20))
        transcripts=[]
        window.speech_transcript_ready.connect(lambda result:transcripts.append(result.text))
        helper.activate_voice('probe: existing wake handoff')
        pump(.08);snap(helper.popup,'02-top-slide');pump(.25);snap(helper.popup,'03-listening-orb')
        assert not window.isVisible() and helper.popup.y()==helper.popup._screen.geometry().top()
        record['voice_popup_at_top']=True
        assert wait(lambda:bool(helper.popup.answer.toPlainText()),120),'No actual answer reached the popup.'
        pump(.25);snap(helper.popup,'04-streaming-reply')
        assert wait(lambda:not window.is_busy and bool(helper.popup.answer.toPlainText()),120),'Voice answer did not finish.'
        record['stt_transcripts']=transcripts;record['spoken_fixture']=spoken_prompt;record['stt_model']=whisper_model or 'vosk'
        record['voice_answer']=helper.popup.answer.toPlainText();record['backdrop']=helper.popup.backdrop
        record['popup_geometry']={'top':helper.popup.y(),'monitor_top':helper.popup._screen.geometry().top(),'size':helper.popup.size().toTuple(),'orb':helper.popup.orb.size().toTuple()}
        snap(helper.popup,'05-voice-answer')
        composite=directory/'05-native-glass-composite.png'
        helper.popup._screen.grabWindow(0,helper.popup.x(),helper.popup.y(),helper.popup.width(),helper.popup.height()).save(str(composite))
        record['evidence'].append(str(composite))
        helper.cancel();pump(.3);assert not helper.popup.isVisible()
        record['upward_dismissal']='SLIDING_UP' in helper.popup.transitions
        # Draw around the real test text. Physical points derive from the actual
        # target geometry; the Windows hook itself remains installed and observed.
        helper.hook.allowed=True;helper._tick();pump(.2)
        logical=label.mapToGlobal(QPoint());screen=target.screen();native=next(bounds for name,bounds in physical_monitors() if name==screen.name())
        geo=screen.geometry();sx=(native[2]-native[0])/geo.width();sy=(native[3]-native[1])/geo.height()
        cx=native[0]+(logical.x()-geo.x()+label.width()/2)*sx
        cy=native[1]+(logical.y()-geo.y()+label.height()/2)*sy
        rx=(label.width()/2+10)*sx;ry=(label.height()/2+10)*sy
        points=[(round(cx+rx*math.cos(i*math.tau/120)),round(cy+ry*math.sin(i*math.tau/120))) for i in range(121)]
        helper._gesture('down',*points[0]);helper._gesture('start',*points[0])
        for point in points[1:]:helper._gesture('move',*point);app.processEvents();time.sleep(.005)
        snap(helper.overlay,'06-freehand-outline');record['outline_visible']=helper.overlay.isVisible()
        helper._gesture('up',*points[-1]);pump(.7)
        assert helper.selection is not None,'The real region was not captured.'
        assert helper.captures==1 and not helper.overlay.isVisible()
        from PIL import Image,ImageStat
        assert max(ImageStat.Stat(Image.open(io.BytesIO(helper.selection.jpeg))).mean)>100,'The acceptance target was occluded; this is not the requested fixture.'
        Image.open(io.BytesIO(helper.selection.jpeg)).save(directory/'07-actual-selected-region.png')
        record['evidence'].append(str(directory/'07-actual-selected-region.png'));snap(helper.popup,'08-selection-preview')
        record['selection_dimensions']=[helper.selection.width,helper.selection.height]
        first_frame=helper.selection.frame_id
        helper.submit('Explain this selected Python error in two short sentences.')
        assert wait(lambda:bool(helper.popup.answer.toPlainText()) and not window.is_busy,150),'Selection answer did not finish.'
        assert helper.last_vision_success,'Vision did not successfully interpret the actual selected fixture.'
        record['selection_answer']=helper.popup.answer.toPlainText();snap(helper.popup,'09-selection-answer')
        serial=helper.response_serial
        helper.submit('Which indices are valid for that list?')
        assert wait(lambda:helper.response_serial>serial and not window.is_busy,150),'Follow-up did not finish.'
        record['followup_answer']=helper.popup.answer.toPlainText();record['followup_same_frame']=helper.selection is not None and helper.selection.frame_id==first_frame and helper.captures==1
        snap(helper.popup,'10-followup-answer')
        # Existing voice runtime produces real local PCM and actual playback.
        runtime.voice.configure(TTSConfig(enabled=True,provider='local',output_format='pcm_24000'))
        spoken=window._speak_assistant_text('MORICE background helper validation is complete.')
        assert wait(lambda:spoken is not None and spoken.done,40),'Local speech playback did not finish.'
        record['tts_result']=str(spoken.wait(1))
        helper.cancel();pump(.3);helper.open_main();pump(.3);record['reopen_same_runtime']=window.isVisible() and window.runtime is runtime
        window.close();pump(.3)
        import psutil
        process=psutil.Process();process.cpu_percent(None);start=time.monotonic();pump(4)
        record['idle_cpu_percent']=process.cpu_percent(None);record['resident_rss_mb']=round(process.memory_info().rss/1024/1024,1)
        record['idle_capture_count_unchanged']=helper.captures==1
        record['helper']=helper.diagnostics();record['popup_transitions']=list(helper.popup.transitions)
        record['native_hook_installed']=helper.hook.running
    except Exception as exc:
        record['failures'].append(str(exc));record['traceback']=traceback.format_exc()
    finally:
        target.close();helper.quit();pump(.3);runtime.shutdown(clean=True);set_app_session_active(False)
        record['shutdown']=runtime.shutdown_report
        record['hook_released']=not helper.hook.running;record['tray_hidden']=not helper.tray.isVisible()
        (directory/'results.json').write_text(json.dumps(record,indent=2,default=str),encoding='utf-8')
    return 1 if record['failures'] else 0
