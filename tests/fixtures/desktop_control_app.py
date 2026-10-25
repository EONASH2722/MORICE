"""Owned, disposable native UIA target; never opens or edits user documents."""
import json
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLineEdit,QPushButton,QLabel

app=QApplication([])
path=Path(sys.argv[1]);window=QWidget();window.setWindowTitle(sys.argv[2])
layout=QVBoxLayout(window)
field=QLineEdit();field.setAccessibleName('Fixture input');layout.addWidget(field)
button=QPushButton('Apply fixture');button.setAccessibleName('Apply fixture');layout.addWidget(button)
result=QLabel('Not applied');result.setAccessibleName('Fixture pending');layout.addWidget(result)
clicks=0
def record(*_):
    path.write_text(json.dumps({'text':field.text(),'clicks':clicks}),encoding='utf-8')
def apply():
    global clicks
    clicks+=1;result.setText('Applied');result.setAccessibleName('Applied fixture');record()
button.clicked.connect(apply);field.textChanged.connect(record)
window.resize(440,200);window.show();record()
QTimer.singleShot(120000,app.quit)
raise SystemExit(app.exec())
