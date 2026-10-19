"""MORICE's original, hand-drawn UI pictograms. No icon font or stock pack.

Each mark uses a shared 24-unit grid, rounded 1.65-unit strokes and a
two-unit optical margin. The product logo is deliberately outside this set.
"""
from __future__ import annotations

import re
import weakref
from functools import lru_cache

from PySide6.QtCore import QObject, QEvent, QRectF, QSize, Qt, Slot, QFileInfo
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QAction, QPalette
from PySide6.QtWidgets import QApplication, QAbstractButton, QCheckBox, QRadioButton, QTabWidget, QStyle, QProxyStyle, QStyleFactory, QFileDialog, QFileIconProvider, QComboBox, QWidget, QDialog, QMenu


# Authored coordinates; no third-party artwork, downloaded assets or fonts.
MARKS = {
    'core': ('M4 8 Q12 2 20 8 Q23 14 12 17 Q1 14 4 8', 'M9 3 Q19 10 15 21 Q6 20 9 3', 'C12 12 1.2'),
    'home': ('M3 11 L12 3 L21 11', 'M5 10 L5 21 L10 21 L10 15 L14 15 L14 21 L19 21 L19 10'),
    'chats': ('R3 4 18 13 4', 'M7 17 L6 21 L12 17', 'M7 9 L17 9', 'M7 13 L13 13'),
    'projects': ('M3 8 L10 8 L12 5 L21 5 L21 20 L3 20 Z', 'M3 8 L3 5 L9 5'),
    'research': ('M8 3 L16 3', 'M10 3 L10 10 L4 19 Q3 21 6 21 L18 21 Q21 21 20 19 L14 10 L14 3', 'M8 15 L16 15', 'C11 18 0.65'),
    'spatial': ('C12 12 9', 'M3 12 L21 12', 'M12 3 Q4 12 12 21 Q20 12 12 3', 'M5 7 Q12 10 19 7', 'M5 17 Q12 14 19 17'),
    'devices': ('R3 4 13 10 2', 'M7 18 L12 18', 'M9.5 14 L9.5 18', 'R17 10 5 11 1.5', 'M19 18 L20 18'),
    'media': ('R3 4 18 16 3', 'C8 9 1.5', 'M4 18 L10 12 L14 16 L17 13 L21 17'),
    'automations': ('M4 9 Q6 3 12 3 Q19 3 21 10', 'M17 7 L21 10 L21 5', 'M20 15 Q18 21 12 21 Q5 21 3 14', 'M7 17 L3 14 L3 19', 'M12 7 L9 13 L13 13 L11 17'),
    'connectors': ('M9 7 L7 5 Q4 2 2 5 Q0 8 3 11 L6 14', 'M15 17 L17 19 Q20 22 22 19 Q24 16 21 13 L18 10', 'M8 16 L16 8'),
    'security': ('M12 3 L20 6 L20 12 Q20 18 12 22 Q4 18 4 12 L4 6 Z', 'M8 12 L11 15 L16 9'),
    'history': ('M4 9 Q6 3 12 3 Q21 3 21 12 Q21 21 12 21 Q6 21 4 16', 'M4 4 L4 9 L9 9', 'M12 7 L12 12 L16 14'),
    'activity': ('M3 13 L7 13 L10 5 L14 20 L17 10 L19 13 L22 13',),
    'tools': ('M14 4 Q17 2 20 4 L16 8 L18 10 L22 6 Q23 12 17 13 L8 22 L3 17 L12 8 Q11 5 14 4',),
    'voice': ('R9 3 6 12 3', 'M5 10 L5 12 Q5 19 12 19 Q19 19 19 12 L19 10', 'M12 19 L12 22', 'M8 22 L16 22'),
    'artifacts': ('M4 3 L15 3 L20 8 L20 21 L4 21 Z', 'M15 3 L15 8 L20 8', 'M8 12 L16 12', 'M8 16 L14 16'),
    'plugins': ('M4 5 L9 5 L9 3 Q12 0 15 3 L15 5 L20 5 L20 11 L18 11 Q15 14 18 17 L20 17 L20 21 L4 21 L4 15 L6 15 Q9 12 6 9 L4 9 Z',),
    'settings': ('M9 3 L15 3 L16 6 L19 7 L22 11 L20 14 L20 18 L16 21 L12 20 L8 21 L4 18 L4 14 L2 11 L5 7 L8 6 Z', 'C12 12 3.5'),
    'search': ('C10 10 6.5', 'M15 15 L21 21'),
    'menu': ('M4 6 L20 6', 'M4 12 L16 12', 'M4 18 L20 18'),
    'more': ('C5 12 1', 'C12 12 1', 'C19 12 1'),
    'close': ('M6 6 L18 18', 'M18 6 L6 18'),
    'minimize': ('M5 16 L19 16',),
    'maximize': ('R4 4 16 16 2',),
    'restore': ('R3 8 13 13 2', 'M8 8 L8 3 L21 3 L21 16 L16 16'),
    'attach': ('M8 15 L16 7 Q19 4 21 7 Q23 10 20 13 L11 22 Q7 25 3 21 Q0 17 3 14 L13 4 Q15 2 17 4 Q19 6 17 8 L7 18',),
    'send': ('M3 4 L22 12 L3 20 L6 12 Z', 'M6 12 L15 12'),
    'model': ('R6 6 12 12 3', 'M9 2 L9 6', 'M15 2 L15 6', 'M9 18 L9 22', 'M15 18 L15 22', 'M2 9 L6 9', 'M2 15 L6 15', 'M18 9 L22 9', 'M18 15 L22 15', 'M10 10 L14 10 L14 14 L10 14 Z'),
    'context': ('R3 4 18 16 3', 'M8 4 L8 20', 'M12 9 L17 9', 'M12 14 L16 14'),
    'add': ('M12 4 L12 20', 'M4 12 L20 12'),
    'remove': ('M4 12 L20 12',),
    'check': ('M4 12 L9 17 L20 6',),
    'chevron_down': ('M5 9 L12 16 L19 9',),
    'chevron_up': ('M5 15 L12 8 L19 15',),
    'chevron_left': ('M15 5 L8 12 L15 19',),
    'chevron_right': ('M9 5 L16 12 L9 19',),
    'play': ('M7 4 L20 12 L7 20 Z',),
    'pause': ('M8 5 L8 19', 'M16 5 L16 19'),
    'stop': ('R5 5 14 14 2',),
    'save': ('M4 3 L17 3 L21 7 L21 21 L3 21 L3 3 Z', 'M8 3 L8 9 L16 9 L16 3', 'R7 14 10 7 1'),
    'export': ('M4 13 L4 21 L20 21 L20 13', 'M12 16 L12 3', 'M7 8 L12 3 L17 8'),
    'import': ('M4 13 L4 21 L20 21 L20 13', 'M12 3 L12 16', 'M7 11 L12 16 L17 11'),
    'refresh': ('M20 9 Q18 3 12 3 Q3 3 3 12 Q3 21 12 21 Q18 21 20 16', 'M15 9 L20 9 L20 4'),
    'delete': ('M3 6 L21 6', 'M8 6 L8 3 L16 3 L16 6', 'M5 6 L6 21 L18 21 L19 6', 'M10 10 L10 17', 'M14 10 L14 17'),
    'edit': ('M4 20 L5 15 L17 3 L21 7 L9 19 Z', 'M14 6 L18 10'),
    'copy': ('R8 8 13 13 2', 'M16 8 L16 3 L3 3 L3 16 L8 16'),
    'reaction': ('M12 3 L14.5 9.5 L21 12 L14.5 14.5 L12 21 L9.5 14.5 L3 12 L9.5 9.5 Z',),
    'helpful': ('M4 11 L8 11 L12 3 Q16 3 14 10 L20 10 Q22 10 21 14 L19 21 L8 21 L8 11', 'M4 11 L4 21 L8 21'),
    'unhelpful': ('M4 13 L8 13 L12 21 Q16 21 14 14 L20 14 Q22 14 21 10 L19 3 L8 3 L8 13', 'M4 13 L4 3 L8 3'),
    'folder': ('M3 7 L10 7 L12 10 L21 10 L21 21 L3 21 Z', 'M3 7 L3 4 L10 4 L12 7 L18 7 L18 10'),
    'file': ('M5 3 L14 3 L20 9 L20 21 L5 21 Z', 'M14 3 L14 9 L20 9'),
    'appearance': ('M12 3 Q21 3 21 12 Q21 16 17 16 L15 16 Q12 16 14 19 Q15 21 12 21 Q3 21 3 12 Q3 3 12 3', 'C8 8 1', 'C14 7 1', 'C17 11 1', 'C7 14 1'),
    'pointer': ('M5 3 L20 13 L13 14 L10 21 Z', 'M13 14 L17 21'),
    'layers': ('M12 3 L22 8 L12 13 L2 8 Z', 'M3 13 L12 18 L21 13', 'M3 17 L12 22 L21 17'),
    'info': ('C12 12 9', 'M12 11 L12 17', 'C12 7 0.6'),
    'warning': ('M12 3 L22 21 L2 21 Z', 'M12 9 L12 14', 'C12 18 0.6'),
    'lock': ('R5 10 14 11 2', 'M8 10 L8 7 Q8 2 12 2 Q16 2 16 7 L16 10', 'M12 14 L12 17'),
    'unlock': ('R5 10 14 11 2', 'M8 10 L8 7 Q8 2 12 2 Q16 2 16 7', 'M12 14 L12 17'),
    'camera': ('M3 7 L8 7 L10 4 L15 4 L17 7 L21 7 L21 20 L3 20 Z', 'C12 13 4'),
    'volume': ('M3 9 L7 9 L13 4 L13 20 L7 15 L3 15 Z', 'M16 8 Q20 12 16 16', 'M19 5 Q25 12 19 19'),
    'pin': ('M12 22 L6 13 Q1 3 12 3 Q23 3 18 13 Z', 'C12 9 2.5'),
    'grid': ('R3 3 18 18 2', 'M9 3 L9 21', 'M15 3 L15 21', 'M3 9 L21 9', 'M3 15 L21 15'),
    'graph': ('M4 3 L4 20 L22 20', 'M7 15 L11 10 L15 13 L21 5'),
    'pair': ('R3 4 7 16 2', 'R14 4 7 16 2', 'M8 12 L16 12', 'M13 9 L16 12 L13 15'),
    'action': ('M12 3 L21 8 L21 16 L12 21 L3 16 L3 8 Z', 'M8 12 L16 12', 'M13 9 L16 12 L13 15'),
}


def draw_mark(painter, name, rect, ink):
    painter.save(); painter.setRenderHint(QPainter.Antialiasing)
    side = min(rect.width(), rect.height()); painter.translate(rect.center().x()-side/2, rect.center().y()-side/2); painter.scale(side/24, side/24)
    painter.setPen(QPen(QColor(ink), 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); painter.setBrush(Qt.NoBrush)
    for instruction in MARKS[name]:
        parts = re.findall(r'[MLQCZR]|-?\d+(?:\.\d+)?', instruction); path = QPainterPath(); index = 0
        while index < len(parts):
            op = parts[index]; index += 1
            count = {'M': 2, 'L': 2, 'Q': 4, 'C': 3, 'R': 5, 'Z': 0}[op]
            values = [float(v) for v in parts[index:index+count]]; index += count
            if op == 'M': path.moveTo(*values)
            elif op == 'L': path.lineTo(*values)
            elif op == 'Q': path.quadTo(*values)
            elif op == 'Z': path.closeSubpath()
            elif op == 'C': path.addEllipse(QRectF(values[0]-values[2], values[1]-values[2], values[2]*2, values[2]*2))
            elif op == 'R': path.addRoundedRect(QRectF(*values[:4]), values[4], values[4])
        painter.drawPath(path)
    painter.restore()


@lru_cache(maxsize=128)
def _native_icon(name, colors):
    """Render authored vectors once; Qt owns subsequent button paint callbacks.

    A Python QIconEngine reenters Python from native style painting while Qt
    temporarily releases the GIL. Keep that lifetime out of worker cyclic GC.
    The bounded cache contains native value objects, not widgets or workers.
    Multiple backing resolutions retain crisp 19/24-unit controls at 100–300%.
    """
    result = QIcon()
    for ink in dict.fromkeys(colors):
        for scale in (1., 1.25, 1.5, 1.75, 2., 2.5, 3.):
            pixels = round(24*scale)
            pixmap = QPixmap(pixels, pixels)
            pixmap.setDevicePixelRatio(scale); pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            try: draw_mark(painter, name, QRectF(0, 0, 24, 24), ink)
            finally: painter.end()
            for mode in (QIcon.Normal, QIcon.Disabled, QIcon.Active, QIcon.Selected):
                for state in (QIcon.Off, QIcon.On):
                    index = 1 if mode == QIcon.Disabled else 2 if state == QIcon.On else 0
                    if colors[index] == ink: result.addPixmap(pixmap, mode, state)
    return result


def icon(name, theme=None, *, primary=False, color=None):
    if name not in MARKS: raise ValueError('Unknown authored UI icon: '+name)
    colors = (color, color, color) if color else (theme.tokens['accent_text'] if primary else theme.tokens['text_primary'], theme.tokens['text_muted'], theme.tokens['text_primary']) if theme else ('#cdd9e8', '#708095', '#eff6fc')
    # Give callers an implicitly shared copy so mutation cannot alter the cache.
    return QIcon(_native_icon(name, tuple(colors)))


def semantic_icon(text):
    text = text.casefold()
    if text in MARKS: return text
    for words, name in ((('queue', 'resources', 'models'), 'model'), (('evidence', 'specification', 'result'), 'artifacts'), (('experiment', 'laboratory'), 'research'), (('simulation',), 'play')):
        if any(word in text for word in words): return name
    for keys, name in (
        (('delete', 'remove', 'clear'), 'delete'), (('cancel', 'abort', 'stop'), 'stop'),
        (('close', 'dismiss'), 'close'), (('copy',), 'copy'), (('save',), 'save'),
        (('export', 'png', 'svg', 'pdf', 'json'), 'export'), (('import', 'install', 'download', 'load'), 'import'),
        (('pause',), 'pause'), (('resume', 'run', 'start', 'play', 'generate', 'render'), 'play'),
        (('refresh', 'reset', 'retry', 'discover'), 'refresh'), (('search', 'inspect', 'find'), 'search'),
        (('new', 'add', 'create'), 'add'), (('edit', 'rename'), 'edit'), (('verify', 'approve', 'apply', 'confirm'), 'check'),
        (('pair', 'connect', 'transfer'), 'pair'), (('folder', 'project'), 'folder'),
        (('font', 'theme', 'color', 'appearance'), 'appearance'), (('voice', 'listen', 'speech', 'microphone'), 'voice'),
        (('camera',), 'camera'), (('graph', 'plot'), 'graph'), (('file', 'attach'), 'file'),
        (('settings', 'preferences'), 'settings'), (('back', 'previous'), 'chevron_left'),
        (('next', 'forward'), 'chevron_right'), (('more',), 'more'), (('expand', 'large'), 'maximize')):
        if any(key in text for key in keys): return name
    return 'action'


class AuthoredControlStyle(QProxyStyle):
    """Supply authored glyphs whenever retained Qt widgets request stock icons."""
    def __init__(self): super().__init__(QStyleFactory.create('Fusion'))
    def standardIcon(self, standard, option=None, widget=None):
        key = standard.name.casefold()
        special = {'sp_titlebarminbutton': 'minimize', 'sp_titlebarmaxbutton': 'maximize', 'sp_titlebarnormalbutton': 'restore', 'sp_dirdialogicon': 'folder', 'sp_computericon': 'devices', 'sp_mediavolume': 'volume', 'sp_dialogopenbutton': 'folder'}
        name = special.get(key) or ('warning' if 'warning' in key else 'info' if 'messagebox' in key else 'folder' if 'dir' in key else 'file' if 'fileicon' in key else semantic_icon(key))
        return icon(name, color=widget.palette().color(widget.foregroundRole()).name() if widget else '#cdd9e8')
    def standardPixmap(self, standard, option=None, widget=None):
        return self.standardIcon(standard, option, widget).pixmap(QSize(24, 24))
    def drawPrimitive(self, element, option, painter, widget=None):
        arrows = {QStyle.PE_IndicatorArrowDown: 'chevron_down', QStyle.PE_IndicatorArrowUp: 'chevron_up', QStyle.PE_IndicatorArrowLeft: 'chevron_left', QStyle.PE_IndicatorArrowRight: 'chevron_right'}
        if element in arrows:
            draw_mark(painter, arrows[element], QRectF(option.rect).adjusted(2, 2, -2, -2), option.palette.color(QPalette.ButtonText).name()); return
        if element in (QStyle.PE_IndicatorCheckBox, QStyle.PE_IndicatorRadioButton):
            painter.save(); painter.setRenderHint(QPainter.Antialiasing); rect = QRectF(option.rect).adjusted(2, 2, -2, -2)
            ink = option.palette.color(QPalette.Text); ink.setAlpha(175 if option.state & QStyle.State_Enabled else 75)
            painter.setPen(QPen(ink, 1.4)); painter.setBrush(option.palette.color(QPalette.Base))
            if element == QStyle.PE_IndicatorRadioButton: painter.drawEllipse(rect)
            else: painter.drawRoundedRect(rect, 4, 4)
            if option.state & (QStyle.State_On | QStyle.State_NoChange):
                if element == QStyle.PE_IndicatorRadioButton:
                    painter.setBrush(ink); painter.setPen(Qt.NoPen); painter.drawEllipse(rect.adjusted(4, 4, -4, -4))
                else: draw_mark(painter, 'remove' if option.state & QStyle.State_NoChange else 'check', rect.adjusted(1, 1, -1, -1), ink)
            painter.restore(); return
        if element == QStyle.PE_IndicatorBranch and option.state & QStyle.State_Children:
            draw_mark(painter, 'chevron_down' if option.state & QStyle.State_Open else 'chevron_right', QRectF(option.rect).adjusted(2, 2, -2, -2), option.palette.color(QPalette.Text)); return
        return super().drawPrimitive(element, option, painter, widget)


class AuthoredFileIcons(QFileIconProvider):
    def __init__(self, theme): super().__init__(); self.theme = theme
    def icon(self, info):
        name = 'folder' if isinstance(info, QFileInfo) and info.isDir() or info == QFileIconProvider.Folder else 'devices' if info in (QFileIconProvider.Computer, QFileIconProvider.Drive, QFileIconProvider.Network) else 'file'
        return icon(name, self.theme)


class ComboChevron(QWidget):
    """QSS can suppress native arrows; keep the authored affordance explicit."""
    def __init__(self, parent, theme):
        super().__init__(parent); self.theme = theme; self.setObjectName('MoriceComboChevron')
        self.setAttribute(Qt.WA_TransparentForMouseEvents); self.setFixedSize(16, 16)
        parent.installEventFilter(self); theme.changed.connect(self.refresh); self.place()
    def place(self):
        parent = self.parentWidget(); self.move(max(0, parent.width()-24), max(0, (parent.height()-16)//2)); self.raise_()
    def eventFilter(self, source, event):
        if event.type() in (QEvent.Resize, QEvent.Show): self.place()
        return False
    def refresh(self, *_): self.update()
    def paintEvent(self, event):
        painter = QPainter(self); draw_mark(painter, 'chevron_down', QRectF(self.rect()), self.theme.tokens['text_primary']); painter.end()


class UiIconBinder(QObject):
    """Apply to the owned presentation, including lazily opened native dialogs."""
    def __init__(self, owner, theme):
        super().__init__(owner); self.owner = owner; self.theme = theme; self._closed = False; self._bound = weakref.WeakSet()
        app = QApplication.instance()
        # Keep file-picking semantics but use an owned, themeable Qt dialog.
        # OS shell icon providers would otherwise inject stock artwork here.
        app.setAttribute(Qt.AA_DontUseNativeDialogs, True)
        if not app.property('morice_authored_control_style'):
            # Retain the Python virtual-method owner as long as the application.
            app._morice_authored_control_style = AuthoredControlStyle()
            app.setStyle(app._morice_authored_control_style); app.setProperty('morice_authored_control_style', True)
        app.installEventFilter(self); theme.changed.connect(self.refresh)
        self.refresh()
    def _owned(self, widget):
        from shiboken6 import isValid
        current = widget
        # Polish/show can arrive while Qt is retiring layout items. Only live
        # QObject parents can belong to this window's control hierarchy.
        while isinstance(current, QObject) and isValid(current):
            if current is self.owner: return True
            current = current.parent()
        return False
    def _bind(self, widget):
        if isinstance(widget, QFileDialog):
            if not hasattr(widget, '_morice_icon_provider'):
                widget._morice_icon_provider = AuthoredFileIcons(self.theme); widget.setIconProvider(widget._morice_icon_provider)
        elif isinstance(widget, QComboBox):
            if not hasattr(widget, '_morice_combo_chevron'): widget._morice_combo_chevron = ComboChevron(widget, self.theme)
        elif isinstance(widget, QAbstractButton) and not isinstance(widget, (QCheckBox, QRadioButton)):
            if widget.property('morice_icon_in_content'): return
            name = widget.property('morice_icon') or semantic_icon(widget.accessibleName() or widget.toolTip() or widget.text())
            if name not in MARKS: name = semantic_icon(str(name))
            widget.setIcon(icon(name, self.theme, primary=widget.property('role') == 'primary')); widget.setIconSize(QSize(19, 19))
            icon_only = not bool(widget.text().strip())
            if widget.property('icon_only') != icon_only:
                widget.setProperty('icon_only', icon_only); widget.style().unpolish(widget); widget.style().polish(widget)
            widget.setMouseTracking(True); widget.setCursor(Qt.PointingHandCursor); self._bound.add(widget)
        elif isinstance(widget, QTabWidget):
            for index in range(widget.count()): widget.setTabIcon(index, icon(semantic_icon(widget.tabText(index)), self.theme))
            self._bound.add(widget)
        elif isinstance(widget, QAction) and not widget.isSeparator():
            name = widget.property('morice_icon') or semantic_icon(widget.text())
            widget.setIcon(icon(name if name in MARKS else semantic_icon(str(name)), self.theme)); self._bound.add(widget)
    def eventFilter(self, source, event):
        # Retained model controls keep their original callbacks, while their
        # obsolete galaxy decoration must neither paint nor keep a timer alive.
        if not self._closed and type(source).__name__=='LiquidGalaxyFrame' and self._owned(source):
            source._timer.stop()
            if event.type()==QEvent.Paint:
                painter=QPainter(source);painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(QPen(QColor(self.theme.tokens['border']),1))
                painter.setBrush(QColor(self.theme.tokens['surface_glass']))
                painter.drawRoundedRect(QRectF(source.rect()).adjusted(.5,.5,-.5,-.5),self.theme.tokens.radius_medium,self.theme.tokens.radius_medium)
                painter.end();return True
        if not self._closed and event.type() in (QEvent.Show, QEvent.Polish, QEvent.ActionAdded) and self._owned(source):
            if event.type() == QEvent.Show and isinstance(source, (QDialog, QMenu)): self._theme_surface(source)
            self._bind(source)
            if event.type() == QEvent.ActionAdded: self._bind(event.action())
        return False
    @Slot()
    def refresh(self, *_):
        for widget in self.owner.findChildren(QWidget):
            if isinstance(widget, (QDialog, QMenu)) and widget.isVisible(): self._theme_surface(widget)
        # Hidden workspaces bind on Show/Polish. Recreating all their icons on
        # every appearance change needlessly stalls the active workspace.
        for kind in (QAbstractButton,QTabWidget,QComboBox):
            for widget in self.owner.findChildren(kind):
                if widget.isVisible(): self._bind(widget)
        for action in self.owner.findChildren(QAction): self._bind(action)
    def _theme_surface(self, widget):
        from .themes import stylesheet
        style = stylesheet(self.theme.tokens)
        if widget.styleSheet() != style: widget.setStyleSheet(style)
    def close(self):
        self._closed = True; app = QApplication.instance()
        if app is not None: app.removeEventFilter(self)
        self._bound.clear()
