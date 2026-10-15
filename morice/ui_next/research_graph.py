"""Actual ResearchStore relationships rendered as a bounded evidence graph."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QFont
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem


class EvidenceGraph(QGraphicsView):
    def __init__(self, theme, parent=None):
        super().__init__(parent); self.theme = theme; self.snapshot = None; self._key = None
        self.setScene(QGraphicsScene(self)); self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setAccessibleName('Research evidence graph. Nodes and edges come from stored records and relationships.')
        self.theme.changed.connect(self.rebuild); self._zoom = 1.

    def set_snapshot(self, snapshot):
        key = (tuple((row['id'],row['revision'],row['stale']) for row in snapshot['records']),
            tuple((edge['source'],edge['target'],edge['relation']) for edge in snapshot['edges']))
        self.snapshot = snapshot
        if key != self._key: self._key = key; self.rebuild()

    def rebuild(self, *_):
        if not self.snapshot: return
        self.scene().clear(); records = self.snapshot['records'][:200]; positions = {}
        for index, record in enumerate(records): positions[record['id']] = (index % 4 * 260,index // 4 * 130)
        pen = QPen(QColor(self.theme.tokens['border']),1.5)
        for edge in self.snapshot['edges']:
            if edge['source'] not in positions or edge['target'] not in positions: continue
            first = positions[edge['source']]; second = positions[edge['target']]
            line = self.scene().addLine(first[0]+115,first[1]+48,second[0]+115,second[1]+48,pen)
            line.setToolTip(edge['source']+' → '+edge['target']+' · '+edge['relation'])
        for record in records:
            x,y = positions[record['id']]
            node = self.scene().addRect(QRectF(x,y,230,96),QPen(QColor(self.theme.tokens['warning'] if record['stale'] else self.theme.tokens['border'])),QColor(self.theme.tokens['surface']))
            node.setFlag(QGraphicsItem.ItemIsSelectable); node.setData(0,record['id']); node.setToolTip(record['kind']+' · '+record['provenance']+'\n'+record['title'])
            text = self.scene().addText(record['kind']+' · '+record['provenance']+'\n'+record['title'][:100],QFont(self.theme.profile.font_family,10))
            text.setDefaultTextColor(QColor(self.theme.tokens['text_primary'])); text.setTextWidth(210); text.setPos(x+10,y+8)
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-20,-20,20,20)); self.resetTransform(); self._zoom=1
        self.fitInView(self.sceneRect(),Qt.KeepAspectRatio)

    def wheelEvent(self,event):
        factor = 1.15 if event.angleDelta().y()>0 else 1/1.15
        if .2 <= self._zoom*factor <= 10: self.scale(factor,factor); self._zoom*=factor
        event.accept()
