"""Live independent globe color preview; cancellation restores the saved channel."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog,QDialog


def choose_globe_color(theme,key,parent):
    if key not in {'globe_color','globe_glow_color'}:raise ValueError('Unknown globe color channel.')
    before=getattr(theme.profile,key)
    dialog=QColorDialog(QColor(before),parent)
    dialog.setWindowTitle('Globe Color' if key=='globe_color' else 'Globe Glow Color')
    dialog.currentColorChanged.connect(lambda value:theme.update(persist=False,**{key:value.name()}))
    if dialog.exec()==QDialog.Accepted:theme.update(**{key:dialog.currentColor().name()})
    else:theme.update(**{key:before})
