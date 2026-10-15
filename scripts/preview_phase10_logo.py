"""Render the unchanged logo at the eight requested sizes using native Qt."""
import hashlib
import os
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='morice-logo-preview-') as directory:
    profile=Path(directory)
    os.environ.update(QT_QPA_PLATFORM='windows',APPDATA=str(profile/'roaming'),LOCALAPPDATA=str(profile/'local'))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage,QPainter,QPixmap,QFont,QColor,QFontInfo
    from PySide6.QtCore import QRect
    app=QApplication([]);source=ROOT/'morice/assets/morice-logo-rgb.png';logo=QPixmap(str(source))
    image=QImage(1180,840,QImage.Format_RGB32);image.fill(QColor('#101723'))
    painter=QPainter(image);painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setPen(QColor('#f5f8fc'));font=QFont('Segoe UI',12);painter.setFont(font)
    painter.drawText(20,30,'Original MORICE logo: native smooth scaling, identity unchanged')
    x=20
    for size in (16,24,32,48,64,128,256):
        painter.drawText(x,65,f'{size}px');painter.drawPixmap(QRect(x,82,size,size),logo);x+=size+35
    painter.drawText(20,275,'512px');painter.drawPixmap(QRect(20,300,512,512),logo)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    painter.drawText(565,390,'Source SHA256:');painter.drawText(565,420,digest[:32]);painter.drawText(565,445,digest[32:])
    painter.end();assert image.save(str(ROOT/'build/phase10-logo-sizes-native.png'))
    print({'platform':app.platformName(),'font':QFontInfo(font).family(),'logo_sha256':digest})
