"""Render the actual Core painter into an explicitly labelled motion sample."""
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage,QPainter,QFont,QColor
from PySide6.QtWidgets import QApplication
from morice.ui_next.core_state import CoreSnapshot
from morice.ui_next.core_view import draw_core
from morice.ui_next.themes import ThemeEngine

app=QApplication([])
output=ROOT/'build/phase10-orbital-motion';output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='morice-orbit-preview-') as directory:
    theme=ThemeEngine(Path(directory));profile=theme.profile;frames=[]
    for index in range(120):
        canvas=QImage(640,480,QImage.Format_RGBA8888);canvas.fill(QColor(theme.tokens['background']))
        painter=QPainter(canvas);painter.setRenderHint(QPainter.Antialiasing)
        draw_core(painter,QRectF(50,25,540,410),CoreSnapshot(),theme.tokens,index/15,
            profile.orbital_complexity,.95,True,profile.motion_strength)
        painter.setPen(QColor(theme.tokens['text_secondary']));painter.setFont(QFont('Segoe UI',10))
        painter.drawText(QRectF(16,440,608,28),0x84,'MORICE · actual orbital renderer · motion preview')
        painter.end()
        frames.append(Image.frombytes('RGBA',(640,480),bytes(canvas.bits())).convert('RGB'))
    frames[0].save(output/'core-motion.gif',save_all=True,append_images=frames[1:],duration=67,loop=0,optimize=False)
    print(str(output/'core-motion.gif'))
