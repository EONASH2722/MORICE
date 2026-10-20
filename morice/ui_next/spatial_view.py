"""Software-projected interactive geographic globe/map; domain owns all math."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QComboBox, QSplitter, QCheckBox, QMenu, QDialog, QFormLayout, QDoubleSpinBox, QDialogButtonBox, QInputDialog

from ..spatial.contracts import Coordinate
from .responsive import FlowLayout


class GlobeCanvas(QWidget):
    coordinate_selected = Signal(object)
    marker_selected = Signal(str)
    cursor_location = Signal(str)

    def __init__(self, theme, policy, clock, parent=None):
        super().__init__(parent)
        self.theme = theme; self.policy = policy; self.clock = clock
        self.setObjectName('SpatialGlobe'); self.setMinimumSize(220, 220); self.setMouseTracking(True)
        self.setAccessibleName('Interactive Earth. Drag to rotate; wheel to zoom; click to measure a geographic point.')
        self.latitude = 15.; self.longitude = 40.; self.zoom = 1.; self.viewport = 'globe'
        self.context = {'markers': [], 'result': None}; self._drag = None; self._moved = False; self._scene_dirty = False
        self.autorotate = False; self.show_grid = True; self.show_land = True; self._cache = None; self._cache_key = None
        self._pair_key = None; self._cursor_at = 0.
        source = Path(__file__).resolve().parents[1] / 'assets/spatial/earth-land.json'
        self.rings = []
        if source.exists() and source.stat().st_size <= 2 * 1024 * 1024:
            value = json.loads(source.read_text()); self.rings = value['rings']
            if value.get('schema') != 1 or sum(map(len, self.rings)) > 50000: raise ValueError('Invalid offline globe geometry.')
        clock.subscribe(self, self.tick)
        theme.changed.connect(self.invalidate); policy.changed.connect(self.invalidate)

    def invalidate(self, *_):
        self._cache = None; self._cache_key = None; self._scene_dirty = True; self.clock.request()

    def set_context(self, context):
        self.context = context; self.viewport = context.get('viewport', 'globe')
        pair = tuple((context.get(key) or {}).get('identifier') for key in ('origin', 'destination'))
        if all(pair) and pair != self._pair_key:
            coordinates = [context[key]['coordinate'] for key in ('origin', 'destination')]
            vectors = [(math.cos(math.radians(c['latitude'])) * math.cos(math.radians(c['longitude'])),
                math.cos(math.radians(c['latitude'])) * math.sin(math.radians(c['longitude'])),
                math.sin(math.radians(c['latitude']))) for c in coordinates]
            x, y, z = (sum(v[i] for v in vectors) for i in range(3))
            if math.sqrt(x*x + y*y + z*z) > 1e-8:
                self.latitude = math.degrees(math.atan2(z, math.hypot(x, y)))
                self.longitude = math.degrees(math.atan2(y, x)); self.invalidate()
            self._pair_key = pair
        self.update()

    def bounds(self):
        radius = min(self.width(), self.height()) * .39 * self.zoom
        return self.width() / 2, self.height() / 2, radius

    def project(self, latitude, longitude):
        x0, y0, radius = self.bounds()
        if self.viewport == 'map':
            return QPointF((longitude + 180) / 360 * self.width(), (90 - latitude) / 180 * self.height()), 1.
        lat, delta = math.radians(latitude), math.radians(longitude - self.longitude)
        center = math.radians(self.latitude)
        x = math.cos(lat) * math.sin(delta)
        y = math.cos(center) * math.sin(lat) - math.sin(center) * math.cos(lat) * math.cos(delta)
        z = math.sin(center) * math.sin(lat) + math.cos(center) * math.cos(lat) * math.cos(delta)
        return QPointF(x0 + radius * x, y0 - radius * y), z

    def unproject(self, point):
        if self.viewport == 'map':
            return Coordinate(max(-90, min(90, 90 - point.y() / max(1, self.height()) * 180)), point.x() / max(1, self.width()) * 360 - 180).to_dict()
        x0, y0, radius = self.bounds(); x, y = (point.x() - x0) / radius, (y0 - point.y()) / radius
        rho = math.hypot(x, y)
        if rho > 1: return None
        if rho < 1e-9: return Coordinate(self.latitude, self.longitude).to_dict()
        angle = math.asin(rho); center = math.radians(self.latitude)
        lat = math.asin(max(-1, min(1, math.cos(angle) * math.sin(center) + y * math.sin(angle) * math.cos(center) / rho)))
        lon = math.radians(self.longitude) + math.atan2(x * math.sin(angle), rho * math.cos(center) * math.cos(angle) - y * math.sin(center) * math.sin(angle))
        return Coordinate(math.degrees(lat), math.degrees(lon)).to_dict()

    def focus(self, coordinate):
        self.latitude = coordinate['latitude']; self.longitude = coordinate['longitude']; self.invalidate()

    def tick(self, delta):
        if self._scene_dirty:
            self._scene_dirty = False; self.update()
        if self.autorotate and self.policy.budget.decorative_motion and self.viewport == 'globe':
            self.longitude = (self.longitude + delta * 2) % 360; self.invalidate(); return True
        return False

    def _polyline(self, painter, coordinates, pen):
        painter.setPen(pen); painter.setBrush(Qt.NoBrush); path = QPainterPath(); prior = None
        for latitude, longitude in coordinates:
            point, visible = self.project(latitude, longitude)
            if visible < 0:
                prior = None; continue
            if prior is None or (self.viewport == 'map' and abs(point.x() - prior.x()) > self.width() / 2): path.moveTo(point)
            else: path.lineTo(point)
            prior = point
        painter.drawPath(path)

    def _base(self):
        t = self.theme.tokens
        key = (self.width(), self.height(), round(self.latitude, 2), round(self.longitude, 2), self.zoom, self.viewport, id(t), self.show_grid, self.show_land, self.policy.budget.atmosphere)
        if key == self._cache_key and self._cache is not None: return self._cache
        ratio = min(2, self.devicePixelRatioF()); pixmap = QPixmap(round(self.width() * ratio), round(self.height() * ratio)); pixmap.setDevicePixelRatio(ratio); pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing)
        x, y, radius = self.bounds(); circle = QPainterPath(); circle.addEllipse(QPointF(x, y), radius, radius)
        if self.viewport == 'globe':
            ocean = QRadialGradient(QPointF(x - radius * .3, y - radius * .35), radius * 1.4)
            ocean.setColorAt(0, QColor(t['surface_elevated'])); ocean.setColorAt(1, QColor(t['background']))
            painter.setBrush(ocean); painter.setPen(QPen(QColor(t['border']), 1)); painter.drawEllipse(QPointF(x, y), radius, radius)
            if self.policy.budget.atmosphere:
                painter.setBrush(Qt.NoBrush)
                for width, alpha in ((8, 12), (3, 25)):
                    rim = QColor(t['spatial']); rim.setAlpha(alpha); painter.setPen(QPen(rim, width)); painter.drawEllipse(QPointF(x, y), radius, radius)
            painter.setClipPath(circle)
        else: painter.fillRect(self.rect(), QColor(t['background']))
        if self.show_land:
            for ring in self.rings:
                vertices = [self.project(lat, lon) for lon, lat in ring]
                if self.viewport == 'map' or all(z >= 0 for _, z in vertices):
                    path = QPainterPath()
                    for index, (point, _) in enumerate(vertices): path.moveTo(point) if index == 0 else path.lineTo(point)
                    path.closeSubpath(); land = QColor(t['spatial']); land.setAlpha(20)
                    painter.fillPath(path, land)
                self._polyline(painter, [(lat, lon) for lon, lat in ring], QPen(QColor(t['border']), 1))
        if self.show_grid:
            grid = QColor(t['border']); grid.setAlpha(60)
            for lat in range(-60, 61, 30): self._polyline(painter, [(lat, lon) for lon in range(-180, 181, 3)], QPen(grid, 1))
            for lon in range(-180, 180, 30): self._polyline(painter, [(lat, lon) for lat in range(-90, 91, 3)], QPen(grid, 1))
        painter.end(); self._cache = pixmap; self._cache_key = key
        return pixmap

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.drawPixmap(0, 0, self._base())
        t = self.theme.tokens; result = self.context.get('result') or {}
        path = result.get('path', [])
        if path and result.get('mode') == 'CHORD':
            # A chord passes through Earth's interior. Surface clipping would
            # incorrectly hide it whenever one endpoint lies behind the globe.
            points = [self.project(p['latitude'], p['longitude'])[0] for p in path]
            painter.setPen(QPen(QColor(t['accent_secondary']), 2.5, Qt.DashLine))
            for first, second in zip(points, points[1:]): painter.drawLine(first, second)
        elif path: self._polyline(painter, [(p['latitude'], p['longitude']) for p in path], QPen(QColor(t['accent_primary']), 2.5))
        for marker in self.context.get('markers', [])[:128]:
            point, visible = self.project(marker['coordinate']['latitude'], marker['coordinate']['longitude'])
            if visible < 0: continue
            painter.setPen(QPen(QColor(t['accent_primary']), 1)); painter.setBrush(QColor(t['surface'])); painter.drawEllipse(point, 5, 5)
            painter.setPen(QColor(t['text_primary'])); painter.drawText(QRectF(point.x() + 10, point.y() - 16, 200, 30), Qt.AlignLeft | Qt.AlignVCenter, marker['label'][:32])
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.position(); self._moved = False; self.autorotate = False

    def mouseMoveEvent(self, event):
        now = time.monotonic()
        if now - self._cursor_at >= 1 / self.policy.budget.fps:
            self._cursor_at = now; point = self.unproject(event.position())
            self.cursor_location.emit(f"{point['latitude']:.3f}°, {point['longitude']:.3f}°" if point else 'Outside Earth')
        if self._drag is not None and event.buttons() & Qt.LeftButton and self.viewport == 'globe':
            delta = event.position() - self._drag
            if abs(delta.x()) + abs(delta.y()) > 2: self._moved = True
            self.longitude -= delta.x() * .35; self.latitude = max(-89.9, min(89.9, self.latitude + delta.y() * .35)); self._drag = event.position(); self.invalidate()

    def mouseReleaseEvent(self, event):
        if self._drag is not None and not self._moved:
            for marker in self.context.get('markers', [])[:128]:
                point, z = self.project(marker['coordinate']['latitude'], marker['coordinate']['longitude'])
                if z >= 0 and (point - event.position()).manhattanLength() <= 16:
                    self.marker_selected.emit(marker['identifier']); self._drag = None; return
            value = self.unproject(event.position())
            if value is not None: self.coordinate_selected.emit(value)
        self._drag = None

    def wheelEvent(self, event):
        self.zoom = max(.7, min(2, self.zoom + event.angleDelta().y() / 1200)); self.invalidate(); event.accept()

    def resizeEvent(self, event):
        self.invalidate(); super().resizeEvent(event)


class SpatialView(QWidget):
    def __init__(self, runtime, bridge, theme, policy, clock, parent=None):
        super().__init__(parent)
        self.runtime = runtime; self.bridge = bridge; self._measurement = []; self._busy = False
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 20, 24, 20)
        title = QLabel('Spatial Lab'); title.setProperty('role', 'title'); layout.addWidget(title)
        description = QLabel('Find cities, states and countries online. Measure verified WGS84 distances.'); description.setProperty('role', 'secondary'); layout.addWidget(description)
        controls = QHBoxLayout(); self.query = QLineEdit(); self.query.setPlaceholderText('Show Chennai and Los Angeles · How far? · In miles')
        self.query.setPlaceholderText('Show Mumbai and Gujarat how far? · Mumbai to Karachi · Find Pakistan')
        self.query.setAccessibleName('Spatial location or follow-up command'); self.query.returnPressed.connect(self.send)
        self.run = QPushButton('Explore'); self.run.setProperty('role', 'primary'); self.run.clicked.connect(self.send)
        self.viewport = QComboBox(); self.viewport.addItems(['3D globe', '2D map']); self.viewport.currentIndexChanged.connect(self.change_view)
        controls.addWidget(self.query, 1); controls.addWidget(self.run); controls.addWidget(self.viewport); layout.addLayout(controls)
        options = FlowLayout()
        self.lookup = QComboBox(); self.lookup.addItem('Internet + offline fallback', True); self.lookup.addItem('Offline cities', False)
        self.lookup.setAccessibleName('Location lookup source')
        self.lookup.currentIndexChanged.connect(lambda: setattr(self.runtime.spatial, 'online_enabled', self.lookup.currentData()))
        options.addWidget(self.lookup)
        self.mode = QComboBox(); self.mode.addItem('Surface · WGS84', 'GEODESIC'); self.mode.addItem('Straight 3D · chord', 'CHORD'); self.mode.addItem('Routing provider unavailable', 'ROUTE')
        self.mode.activated.connect(lambda index: self.command({'GEODESIC': 'as the crow flies', 'CHORD': 'straight line distance', 'ROUTE': 'driving distance'}[self.mode.itemData(index)]))
        self.unit = QComboBox(); self.unit.addItems(['m', 'km', 'miles', 'nautical miles']); self.unit.activated.connect(lambda index: self.command('in ' + self.unit.itemText(index)))
        options.addWidget(self.mode); options.addWidget(self.unit); layout.addLayout(options)
        advanced = QPushButton('Measure / markers'); options.addWidget(advanced)
        menu = QMenu(advanced)
        for label, callback in (('Add supplied coordinate', self.add_coordinate), ('Radius around selected marker', lambda: self.measure_selection('radius')),
            ('Path through selected markers', lambda: self.measure_selection('path')), ('Area of selected polygon', lambda: self.measure_selection('area')),
            ('Remove selected marker', self.remove_marker)):
            menu.addAction(label, callback)
        advanced.setMenu(menu)
        split = QSplitter(); self.canvas = GlobeCanvas(theme, policy, clock); split.addWidget(self.canvas)
        panel = QWidget(); detail = QVBoxLayout(panel); panel.setMinimumWidth(250); panel.setMaximumWidth(390)
        self.status = QLabel('Choose two named locations, or click Earth to measure.'); self.status.setWordWrap(True); detail.addWidget(self.status)
        self.result = QLabel(''); self.result.setWordWrap(True); self.result.setProperty('role', 'title'); detail.addWidget(self.result)
        self.candidates = QListWidget(); self.candidates.itemActivated.connect(self.choose); detail.addWidget(self.candidates)
        self.use_place = QPushButton('Use selected place'); self.use_place.setProperty('morice_icon', 'check')
        self.use_place.clicked.connect(lambda: self.choose(self.candidates.currentItem()) if self.candidates.currentItem() else None)
        self.candidates.currentItemChanged.connect(lambda current, previous: self.use_place.setEnabled(current is not None))
        self.use_place.setEnabled(False); self.use_place.hide(); detail.addWidget(self.use_place)
        self.markers = QListWidget(); self.markers.setSelectionMode(QListWidget.ExtendedSelection); self.markers.itemActivated.connect(self.focus_marker); detail.addWidget(self.markers)
        self.cursor = QLabel(); detail.addWidget(self.cursor)
        self.source = QLabel('Online places: Photon / OpenStreetMap contributors (ODbL). Offline cities: GeoNames (CC BY 4.0). Land: Natural Earth.'); self.source.setWordWrap(True); self.source.setProperty('role', 'secondary'); detail.addWidget(self.source)
        split.addWidget(panel); split.setStretchFactor(0, 1); layout.addWidget(split, 1)
        self.canvas.cursor_location.connect(self.cursor.setText); self.canvas.coordinate_selected.connect(self.measure_point); self.canvas.marker_selected.connect(self.focus_id)
        for name, label, initial in (('show_grid', 'Grid', True), ('show_land', 'Land', True), ('autorotate', 'Auto-rotate', False)):
            field = QCheckBox(label); field.setChecked(initial)
            field.toggled.connect(lambda value, key=name: (setattr(self.canvas, key, value), self.canvas.invalidate()))
            options.addWidget(field)
            if name == 'autorotate':
                self.autorotate = field
                policy.changed.connect(lambda *_: self.autorotate.setEnabled(policy.budget.decorative_motion))
                field.setEnabled(policy.budget.decorative_motion)

    def send(self):
        text = self.query.text().strip()
        if text and not self.runtime.spatial.is_context_command(text):
            import re
            text = 'show ' + text if re.fullmatch(r'.+?\s+to\s+.+', text, re.I) else 'find place ' + re.sub(r'^(?:show|find|locate)\s+', '', text, flags=re.I)
        if text: self.command(text)

    def command(self, text):
        if self._busy: return
        self.set_busy(True); self.candidates.clear(); self.result.clear(); self.status.setText('Looking up places / calculating…')
        try: self.bridge.submit('spatial-command', lambda: self.runtime.spatial.handle_text(text), self.completed)
        except (RuntimeError, ValueError) as exc:
            self.set_busy(False); self.status.setText(str(exc))

    def set_busy(self, busy):
        self._busy = busy
        for control in (self.run, self.query, self.lookup, self.mode, self.unit, self.candidates): control.setEnabled(not busy)

    def completed(self, envelope):
        self.set_busy(False)
        if not envelope['ok']:
            self.status.setText(envelope['error']); return
        value = envelope['value']
        if value is None:
            self.status.setText('Use a location command, a distance follow-up, or click Earth to measure.'); return
        self.status.setText(value['message']); self.set_context(value['context'])

    def set_context(self, context):
        self.canvas.set_context(context); self.candidates.clear(); self.markers.clear()
        origins = {('Online Photon / OpenStreetMap' if v['source'].startswith('https://www.openstreetmap.org/') else 'Offline GeoNames' if v['source'].startswith('https://www.geonames.org/') else 'Supplied coordinates') for v in context.get('markers', [])}
        prefix = 'Current coordinates: ' + ', '.join(sorted(origins)) + '. ' if origins else ''
        self.source.setText(prefix + 'Online: OpenStreetMap contributors (ODbL), Photon. Offline: GeoNames (CC BY 4.0). Land: Natural Earth.')
        for pending in context.get('pending', []):
            for candidate in pending['candidates']:
                item = QListWidgetItem(f"{pending['slot'].title()} · {candidate['label']} · {candidate.get('kind', 'city')} · {candidate['country']}/{candidate['region']}")
                item.setData(Qt.UserRole, (pending['slot'], candidate['identifier'])); self.candidates.addItem(item)
        self.candidates.setVisible(bool(context.get('pending')))
        self.use_place.setVisible(bool(context.get('pending')))
        if context.get('pending'): self.status.setText('Select the place and country you mean, then choose Use selected place.')
        for marker in context.get('markers', []):
            coordinate = marker['coordinate']; item = QListWidgetItem(f"{marker['label']} · {marker.get('kind', 'city')} · {marker.get('country', '')}\n{coordinate['latitude']:.4f}°, {coordinate['longitude']:.4f}°")
            item.setToolTip(marker['source'])
            item.setData(Qt.UserRole, marker['identifier']); self.markers.addItem(item)
        result = context.get('result') or {}
        if 'distance' in result:
            self.result.setText(f"{result['distance']:,.2f} {result['unit']}\n{'Surface geodesic · WGS84' if result['mode']=='GEODESIC' else 'Straight 3D / chord · WGS84'}")
            self.result.setToolTip(result['earth_model'] + '\n' + result['altitude_note'])
            if any(v.get('kind') in {'country','state','county','district'} for v in result.get('locations', [])):
                self.result.setText(self.result.text() + '\nRepresentative points, not borders or road routes.')
        elif 'radius_metres' in result: self.result.setText(f"{result['radius_metres']/1000:,.2f} km geodesic radius")
        elif 'square_metres' in result: self.result.setText(f"{result['square_metres']/1e6:,.2f} km²\nGeodesic polygon · WGS84")
        else: self.result.clear()
        self.viewport.blockSignals(True); self.viewport.setCurrentIndex(1 if context.get('viewport') == 'map' else 0); self.viewport.blockSignals(False)
        self.mode.setCurrentIndex(max(0, self.mode.findData(context.get('mode'))))
        self.unit.setCurrentText(context.get('unit', 'km'))

    def choose(self, item):
        slot, identifier = item.data(Qt.UserRole)
        def done(envelope):
            if not envelope['ok']: self.status.setText(envelope['error']); return
            context = envelope['value']; self.set_context(context)
            if not context.get('pending'): self.status.setText('Distance calculated using selected places.' if context.get('result') else 'Location selected.')
        self.bridge.submit('spatial-candidate', lambda: self.runtime.spatial.choose_candidate(slot, identifier), done)

    def focus_id(self, identifier):
        def focus(envelope):
            if envelope['ok'] and envelope['value'].success: self.canvas.focus(envelope['value'].output['coordinate'])
        self.bridge.submit('spatial-focus', lambda: self.runtime.kernel.dispatch('spatial.viewport.focus', {'marker_id': identifier}), focus)

    def focus_marker(self, item):
        self.focus_id(item.data(Qt.UserRole))

    def change_view(self, index):
        capability = 'spatial.map.show' if index else 'spatial.globe.show'
        self.bridge.submit('spatial-viewport', lambda: (self.runtime.kernel.dispatch(capability, {}), self.runtime.spatial.snapshot())[1],
            lambda envelope: self.set_context(envelope['value']) if envelope['ok'] else self.status.setText(envelope['error']))

    def measure_point(self, coordinate):
        def done(envelope):
            if envelope['ok']:
                self.set_context(envelope['value'])
                self.status.setText('Point A selected. Click a second point to calculate.' if envelope['value']['destination'] is None else 'Supplied coordinates and distance verified.')
            else: self.status.setText(envelope.get('error', 'Geographic calculation could not be verified.'))
        self.bridge.submit('spatial-click-measure', lambda: self.runtime.spatial.select_measurement_point(coordinate), done)

    def add_coordinate(self):
        dialog = QDialog(self); dialog.setWindowTitle('Supplied WGS84 coordinate'); form = QFormLayout(dialog)
        label = QLineEdit('Supplied point'); form.addRow('Label',label)
        latitude = QDoubleSpinBox(); latitude.setRange(-90,90); latitude.setDecimals(6); form.addRow('Latitude (degrees)',latitude)
        longitude = QDoubleSpinBox(); longitude.setRange(-180,180); longitude.setDecimals(6); form.addRow('Longitude (degrees)',longitude)
        altitude = QLineEdit(); altitude.setPlaceholderText('Optional metres above WGS84 ellipsoid'); form.addRow('Altitude',altitude)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted: return
        try: coordinate = Coordinate(latitude.value(),longitude.value(),float(altitude.text()) if altitude.text().strip() else None).to_dict()
        except ValueError as exc: self.status.setText(str(exc)); return
        inputs = {'coordinate':coordinate,'label':label.text()}
        def add():
            result = self.runtime.kernel.dispatch('spatial.marker.add',inputs)
            if not result.success: raise ValueError('Supplied coordinate could not be verified.')
            return self.runtime.spatial.snapshot()
        self.bridge.submit('spatial-add-supplied-marker',add,lambda value:self.set_context(value['value']) if value['ok'] else self.status.setText(value['error']))

    def measure_selection(self, kind):
        identifiers = [item.data(Qt.UserRole) for item in self.markers.selectedItems()]
        metres = None
        if kind == 'radius':
            metres, accepted = QInputDialog.getDouble(self,'Geodesic radius','Radius in metres',1000,1,10000000,2)
            if not accepted: return
        def done(value):
            if value['ok']:
                self.set_context(value['value']); self.status.setText('Computed using selected markers in displayed order. No terrain or routing data is inferred.')
            else: self.status.setText(value['error'])
        self.bridge.submit('spatial-'+kind+'-selection',lambda:self.runtime.spatial.measure_selection(kind,identifiers,metres=metres),done)

    def remove_marker(self):
        selected = self.markers.currentItem()
        if selected is None: self.status.setText('Select a marker first.'); return
        identifier = selected.data(Qt.UserRole)
        self.bridge.submit('spatial-remove-marker', lambda:(self.runtime.kernel.dispatch('spatial.marker.remove',{'marker_id':identifier}),self.runtime.spatial.snapshot())[1],
            lambda value:self.set_context(value['value']) if value['ok'] else self.status.setText(value['error']))
