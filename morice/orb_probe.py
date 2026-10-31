"""Native packaged Orb acceptance on an explicitly isolated packaging profile."""
def probe(app):
    import time
    from PySide6.QtTest import QTest
    from .desktop_pet import AssetLoader
    from .orb_pet import OrbPetWindow
    orb=OrbPetWindow(AssetLoader().load('orb'),click_action='nothing',size='large')
    errors=[];orb.canvas.rendering_failed.connect(errors.append)
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:app.processEvents();QTest.qWait(10)
    try:
        orb.start();pump(.65)
        assert not errors and orb.canvas.diagnostics()['gpu'],errors
        first=list(orb.canvas._orbit_phases);pump(.15);assert first!=orb.canvas._orbit_phases
        image=orb.canvas.grabFramebuffer();assert image.hasAlphaChannel()
        transparent=0;inside=0
        for x in range(0,image.width(),max(1,image.width()//40)):
            for y in range(0,image.height(),max(1,image.height()//40)):
                if (x-image.width()/2)**2+(y-image.height()/2)**2<(image.height()*.26)**2:
                    inside+=1;transparent+=image.pixelColor(x,y).alpha()<5
        assert inside and transparent/inside>.15,(transparent,inside)
        orb.model.present({'state':'SPEAKING','level':.8});pump(.2);assert orb.canvas._audio_envelope>.3
        orb.model.present({'state':'SPEAKING','level':0});pump(.3);assert orb.canvas._audio_envelope<.1
        orb.theme.update(globe_color='#55ddff',globe_glow_color='#2488aa');orb.reload_style()
        assert orb.theme.profile.globe_color=='#55ddff' and orb.theme.profile.globe_glow_color=='#2488aa'
        assert not orb.cursor().pixmap().isNull()
        return {'production_globe_renderer':True,'gpu':True,'transparent_interior_fraction':transparent/inside,
            'idle_rotation':True,'color_persist_reload':True,'controlled_audio_envelope':True,'outlined_native_pointer':True,'microphone_opened':False,'weights_loaded':False}
    finally:orb.shutdown();app.processEvents()

def run(output):
    import os,json
    from pathlib import Path
    from PySide6.QtWidgets import QApplication
    if not os.getenv('MORICE_RUNTIME_DIR') or not os.getenv('APPDATA'):raise RuntimeError('An isolated packaging profile is required.')
    app=QApplication([]);result=probe(app);Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8');return 0
