"""Plain-language inputs for the existing bounded experiment compiler."""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QLabel, QSpinBox, QStackedWidget, QPlainTextEdit, QPushButton,
    QScrollArea, QFrame)


MODEL_NAMES = {
    'linear_oscillator': 'Driven oscillator',
    'thermal_expansion': 'Thermal expansion',
    'ideal_mixture_density': 'Ideal mixture density',
    'vacuum_particle': 'Particle in vacuum',
}


class ExperimentForm(QWidget):
    prepare_requested = Signal(object)

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.inputs = {}
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        self.entry_mode = QComboBox()
        self.entry_mode.addItem('Describe an experiment', 'describe')
        self.entry_mode.addItem('Choose a model and enter values', 'form')
        self.entry_mode.setAccessibleName('How to create an experiment')
        root.addWidget(self.entry_mode)
        self.pages = QStackedWidget(); root.addWidget(self.pages, 1)
        describe = QWidget(); layout = QVBoxLayout(describe); layout.setContentsMargins(0, 0, 0, 0)
        self.prompt = QPlainTextEdit()
        self.prompt.setAccessibleName('Experiment request')
        self.prompt.setPlaceholderText('Describe an oscillator, thermal expansion, mixture density, or vacuum particle experiment. Include values and units. You can also paste an experiment JSON specification.')
        layout.addWidget(self.prompt, 1)
        example = QPushButton('Use an oscillator example')
        example.setProperty('morice_icon', 'research')
        example.clicked.connect(lambda: self.prompt.setPlainText(
            'Simulate an oscillator; mass=1 kg; stiffness=100 N/m; damping=0.5 N*s/m; '
            'force=1 N; frequency=1 Hz; sweep frequency from 0 to 5 Hz; 21 points'))
        layout.addWidget(example)
        note = QLabel('These are computational models. Unsupported domains or missing inputs are explained here; no experiment is invented.')
        note.setWordWrap(True); note.setProperty('role', 'secondary'); layout.addWidget(note)
        self.pages.addWidget(describe)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget(); self.form = QFormLayout(body); self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.title = QLineEdit(); self.title.setPlaceholderText('What are you testing?')
        self.title.setAccessibleName('Experiment objective'); self.form.addRow('Objective', self.title)
        self.model = QComboBox()
        for identifier in registry.tools:
            self.model.addItem(MODEL_NAMES.get(identifier, identifier.replace('_', ' ')), identifier)
        self.model.setAccessibleName('Computational model'); self.form.addRow('Model', self.model)
        self.parameters = QWidget(); self.parameter_layout = QFormLayout(self.parameters)
        self.parameter_layout.setContentsMargins(0, 0, 0, 0); self.form.addRow(self.parameters)
        self.kind = QComboBox(); self.kind.addItem('One run', 'SINGLE'); self.kind.addItem('Parameter sweep', 'PARAMETER_SWEEP')
        self.kind.setAccessibleName('Experiment type'); self.form.addRow('Run type', self.kind)
        self.sweep = QWidget(); sweep = QFormLayout(self.sweep); sweep.setContentsMargins(0, 0, 0, 0)
        self.axis = QComboBox(); self.axis.setAccessibleName('Parameter to vary'); sweep.addRow('Vary', self.axis)
        self.low = QLineEdit(); self.low.setAccessibleName('Range minimum'); sweep.addRow('From', self.low)
        self.high = QLineEdit(); self.high.setAccessibleName('Range maximum'); sweep.addRow('To', self.high)
        self.points = QSpinBox(); self.points.setRange(2, 10000); self.points.setValue(21)
        self.points.setAccessibleName('Number of runs'); sweep.addRow('Runs', self.points)
        self.form.addRow(self.sweep); self.sweep.hide()
        self.limitations = QLabel(); self.limitations.setWordWrap(True); self.limitations.setProperty('role', 'secondary')
        self.form.addRow(self.limitations); scroll.setWidget(body); self.pages.addWidget(scroll)
        self.error = QLabel(); self.error.setWordWrap(True); self.error.hide(); root.addWidget(self.error)
        self.prepare_button = QPushButton('Review experiment'); self.prepare_button.setProperty('role', 'primary')
        self.prepare_button.setProperty('morice_icon', 'research'); self.prepare_button.clicked.connect(self.submit)
        root.addWidget(self.prepare_button)
        self.entry_mode.currentIndexChanged.connect(self.pages.setCurrentIndex)
        self.model.currentIndexChanged.connect(self._model_changed)
        self.kind.currentIndexChanged.connect(lambda: self.sweep.setVisible(self.kind.currentData() != 'SINGLE'))
        self._model_changed()

    def _model_changed(self, *_):
        while self.parameter_layout.rowCount(): self.parameter_layout.removeRow(0)
        self.inputs = {}; self.axis.clear()
        tool = self.registry.get(self.model.currentData())
        for name, unit in tool.required_units.items():
            field = QLineEdit(); field.setPlaceholderText('Required value')
            field.setAccessibleName(name.replace('_', ' ') + (' in ' + unit if unit else ''))
            self.inputs[name] = field
            label = name.replace('_', ' ').capitalize() + (f' ({unit})' if unit else ' (0–1)')
            self.parameter_layout.addRow(label, field); self.axis.addItem(label, name)
        self.limitations.setText(tool.limitations)

    def request(self):
        if self.entry_mode.currentData() == 'describe':
            text = self.prompt.toPlainText().strip()
            if not text: raise ValueError('Describe what you want to test, or choose a model and enter its values.')
            if text.startswith('{'):
                import json
                return json.loads(text)
            return text
        objective = self.title.text().strip()
        if not objective: raise ValueError('Enter an objective for this experiment.')
        tool = self.registry.get(self.model.currentData())
        parameters = {}
        for name, field in self.inputs.items():
            try: value = float(field.text().strip())
            except ValueError: raise ValueError('Enter a numeric value for ' + name.replace('_', ' ') + '.') from None
            parameters[name] = {'value': value, 'unit': tool.required_units[name]}
        spec = {'title': objective[:100], 'objective': objective, 'simulation_engine': tool.tool_id,
            'parameters': parameters, 'experiment_type': self.kind.currentData()}
        if self.kind.currentData() == 'PARAMETER_SWEEP':
            try: low, high = float(self.low.text()), float(self.high.text())
            except ValueError: raise ValueError('Enter numeric From and To values for the sweep.') from None
            name = self.axis.currentData()
            spec['parameter_ranges'] = {name: {'min': low, 'max': high,
                'unit': tool.required_units[name], 'points': self.points.value()}}
        return spec

    def submit(self):
        try: request = self.request()
        except ValueError as exc:
            self.error.setText(str(exc)); self.error.show(); return
        self.error.hide(); self.prepare_requested.emit(request)
