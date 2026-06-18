from __future__ import annotations
import sys
import logging
from typing import Optional, Any
import pandas as pd

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDateTime, QObject, QAbstractTableModel
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QLineEdit, QDoubleSpinBox,
    QSpinBox, QCheckBox, QPushButton, QFileDialog,
    QTableView, QHeaderView, QProgressBar,
    QStatusBar, QTabWidget, QDateTimeEdit, QTextEdit, QMessageBox,
    QSplitter,
)

from .config import AppConfig, load_config
from .query import query_availability, batch_query_from_csv

logger = logging.getLogger(__name__)


class PandasModel(QAbstractTableModel):
    """
    Qt Model mapping underlying DataFrame attributes directly to lazy layouts.
    """

    def __init__(self, data: pd.DataFrame):
        super().__init__()
        self._data = data

    def rowCount(self, parent: Any = None) -> int:
        """Returns the number of rows populated within the current frame."""
        return self._data.shape[0]

    def columnCount(self, parent: Any = None) -> int:
        """Returns the structural boundary width of the dataset."""
        return self._data.shape[1]

    def data(self, index: Any, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> Optional[str]:
        """Provides direct content casting for the view target interface."""
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> Optional[str]:
        """Resolves visual labels corresponding to axis indexes."""
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Orientation.Vertical:
                return str(self._data.index[section])
        return None


class LogEmitter(QObject):
    """
    Subclass facilitating pure signal passing decoupled from primary visual loops.
    """
    log_signal = pyqtSignal(str)


class QLogHandler(logging.Handler):
    """
    Subclass of logging.Handler guaranteeing thread-safe GUI updates.
    """

    def __init__(self):
        super().__init__()
        self.emitter = LogEmitter()
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        """Redirects generated record string payloads across Qt connections."""
        msg = self.format(record)
        self.emitter.log_signal.emit(msg)


class QueryWorker(QThread):
    """
    Threaded execution subclass allocating network operations securely behind interfaces.
    """
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, mode: str, params: dict, config: AppConfig):
        super().__init__()
        self.mode = mode
        self.params = params
        self.config = config

    def run(self) -> None:
        """Executes designated target functions monitoring exception bubbles."""
        try:
            if self.mode == "single":
                df = query_availability(**self.params, config=self.config)
            else:
                df = batch_query_from_csv(**self.params, config=self.config)
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(str(e))


class SingleQueryTab(QWidget):
    """
    Dedicated view component requesting singular coordinate spatial inputs.
    """

    def __init__(self, config: AppConfig):
        super().__init__()
        self.cfg = config
        self._build_ui()

    def _build_ui(self) -> None:
        """Builds standardized input widgets using precompiled constraints."""
        layout = QVBoxLayout(self)
        params_group = QGroupBox("Query Parameters")
        form = QFormLayout()

        g = self.cfg.geometry
        ui = self.cfg.gui_defaults

        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(g.min_lat, g.max_lat)
        self.lat_spin.setDecimals(4)
        self.lat_spin.setValue(ui.default_lat)
        form.addRow("Latitude:", self.lat_spin)

        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(g.min_lon, g.max_lon)
        self.lon_spin.setDecimals(4)
        self.lon_spin.setValue(ui.default_lon)
        form.addRow("Longitude:", self.lon_spin)

        self.dt_edit = QDateTimeEdit()
        self.dt_edit.setDateTime(QDateTime.currentDateTime())
        self.dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt_edit.setCalendarPopup(True)
        form.addRow("Target Date:", self.dt_edit)

        self.cloud_spin = QDoubleSpinBox()
        self.cloud_spin.setRange(0.0, 100.0)
        self.cloud_spin.setValue(self.cfg.query_defaults.max_cloud_cover_pct)
        self.cloud_spin.setSuffix(" %")
        form.addRow("Max Cloud Cover:", self.cloud_spin)

        self.buffer_days_spin = QSpinBox()
        self.buffer_days_spin.setRange(0, ui.max_buffer_days)
        self.buffer_days_spin.setValue(
            self.cfg.query_defaults.temporal_buffer_days)
        form.addRow("Temporal Buffer (days):", self.buffer_days_spin)

        self.buffer_km_spin = QDoubleSpinBox()
        self.buffer_km_spin.setRange(0.0, ui.max_buffer_km)
        self.buffer_km_spin.setValue(self.cfg.query_defaults.spatial_buffer_km)
        self.buffer_km_spin.setSuffix(" km")
        form.addRow("Spatial Buffer:", self.buffer_km_spin)

        collections_layout = QHBoxLayout()
        self.collection_checks = {}
        for name in self.cfg.collections:
            cb = QCheckBox(name)
            cb.setChecked(name in ("sentinel-2", "sentinel-1"))
            self.collection_checks[name] = cb
            collections_layout.addWidget(cb)
        form.addRow("Collections:", collections_layout)

        params_group.setLayout(form)
        layout.addWidget(params_group)

    def get_params(self) -> dict:
        """Extracts values populating unified data query dictionaries."""
        qdt = self.dt_edit.dateTime().toPyDateTime()
        collections = [
            n for n, cb in self.collection_checks.items() if cb.isChecked()]
        return {
            "lat": self.lat_spin.value(),
            "lon": self.lon_spin.value(),
            "target_date": qdt,
            "collections": collections or ["sentinel-2"],
            "temporal_buffer_days": self.buffer_days_spin.value(),
            "spatial_buffer_km": self.buffer_km_spin.value(),
            "max_cloud_cover": self.cloud_spin.value(),
        }


class BatchQueryTab(QWidget):
    """
    Dedicated view component parsing multiple spatial instructions from flat files.
    """

    def __init__(self, config: AppConfig):
        super().__init__()
        self.cfg = config
        self._build_ui()

    def _build_ui(self) -> None:
        """Initializes components rendering file dialogue constraints."""
        layout = QVBoxLayout(self)
        file_group = QGroupBox("Input CSV")
        file_layout = QHBoxLayout()
        self.csv_path_edit = QLineEdit()
        self.csv_path_edit.setPlaceholderText("Select CSV file...")
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_csv)
        file_layout.addWidget(self.csv_path_edit)
        file_layout.addWidget(browse_btn)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        params_group = QGroupBox("Batch Parameters")
        form = QFormLayout()

        ui = self.cfg.gui_defaults

        self.cloud_spin = QDoubleSpinBox()
        self.cloud_spin.setRange(0.0, 100.0)
        self.cloud_spin.setValue(self.cfg.query_defaults.max_cloud_cover_pct)
        self.cloud_spin.setSuffix(" %")
        form.addRow("Max Cloud Cover:", self.cloud_spin)

        self.buffer_days_spin = QSpinBox()
        self.buffer_days_spin.setRange(0, ui.max_buffer_days)
        self.buffer_days_spin.setValue(
            self.cfg.query_defaults.temporal_buffer_days)
        form.addRow("Temporal Buffer (days):", self.buffer_days_spin)

        self.buffer_km_spin = QDoubleSpinBox()
        self.buffer_km_spin.setRange(0.0, ui.max_buffer_km)
        self.buffer_km_spin.setValue(self.cfg.query_defaults.spatial_buffer_km)
        self.buffer_km_spin.setSuffix(" km")
        form.addRow("Spatial Buffer:", self.buffer_km_spin)

        collections_layout = QHBoxLayout()
        self.collection_checks = {}
        for name in self.cfg.collections:
            cb = QCheckBox(name)
            cb.setChecked(name in ("sentinel-2", "sentinel-1"))
            self.collection_checks[name] = cb
            collections_layout.addWidget(cb)
        form.addRow("Collections:", collections_layout)

        params_group.setLayout(form)
        layout.addWidget(params_group)
        layout.addStretch()

    def _browse_csv(self) -> None:
        """Triggers local filesystem access targeting valid data sets."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV", "", "CSV Files (*.csv)")
        if path:
            self.csv_path_edit.setText(path)

    def get_params(self) -> Optional[dict]:
        """Provides parsed parameters dictating batch file execution bounds."""
        csv_path = self.csv_path_edit.text().strip()
        if not csv_path:
            return None
        collections = [
            n for n, cb in self.collection_checks.items() if cb.isChecked()]
        return {
            "csv_path": csv_path,
            "collections": collections or ["sentinel-2"],
            "temporal_buffer_days": self.buffer_days_spin.value(),
            "spatial_buffer_km": self.buffer_km_spin.value(),
            "max_cloud_cover": self.cloud_spin.value(),
        }


class AuthGroup(QGroupBox):
    """
    Modular widget exposing fallback credentials mapping directly to connection pools.
    """

    def __init__(self, config: AppConfig):
        super().__init__("Credentials (optional)")
        form = QFormLayout(self)
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("CDSE username")
        if config.credentials.username:
            self.user_edit.setText(config.credentials.username)
        form.addRow("Username:", self.user_edit)

        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setPlaceholderText("CDSE password")
        form.addRow("Password:", self.pass_edit)

    def get_credentials(self) -> dict:
        """Packages localized credential pairs omitting vacant entries."""
        u = self.user_edit.text().strip() or None
        p = self.pass_edit.text().strip() or None
        return {"username": u, "password": p}


class MainWindow(QMainWindow):
    """
    Primary orchestration window containing composite modules scaling visual applications.
    """

    def __init__(self, config: AppConfig):
        super().__init__()
        self.cfg = config
        self.worker: Optional[QueryWorker] = None
        self.result_df: Optional[pd.DataFrame] = None
        self.setWindowTitle("EO Connect - Satellite Query")
        ui = self.cfg.gui_defaults
        self.setMinimumSize(ui.min_window_width, ui.min_window_height)
        self._build_ui()

    def _build_ui(self) -> None:
        """Assembles interactive component layouts connecting sub-routines statically."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Vertical)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.single_tab = SingleQueryTab(self.cfg)
        self.batch_tab = BatchQueryTab(self.cfg)
        self.tabs.addTab(self.single_tab, "Single Query")
        self.tabs.addTab(self.batch_tab, "Batch Query")
        top_layout.addWidget(self.tabs)

        self.auth_group = AuthGroup(self.cfg)
        top_layout.addWidget(self.auth_group)

        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run Query")
        self.run_btn.clicked.connect(self._run_query)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self._export_csv)
        self.export_btn.setEnabled(False)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addStretch()
        top_layout.addLayout(btn_layout)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        top_layout.addWidget(self.progress)

        splitter.addWidget(top)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        bottom_layout.addWidget(self.table_view)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        bottom_layout.addWidget(self.log_text)

        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self.log_handler = QLogHandler()
        self.log_handler.emitter.log_signal.connect(self.log_text.append)
        logging.getLogger().addHandler(self.log_handler)

    def _run_query(self) -> None:
        """Determines logic paths issuing target thread routines appropriately."""
        idx = self.tabs.currentIndex()
        creds = self.auth_group.get_credentials()

        if idx == 0:
            params = self.single_tab.get_params()
            params.update(creds)
            mode = "single"
        else:
            params = self.batch_tab.get_params()
            if params is None:
                QMessageBox.warning(
                    self, "Missing Input", "Select a CSV file first.")
                return
            params.update(creds)
            mode = "batch"

        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_bar.showMessage("Querying...")

        self.worker = QueryWorker(mode, params, self.cfg)
        self.worker.finished.connect(self._on_query_finished)
        self.worker.error.connect(self._on_query_error)
        self.worker.start()

    def _on_query_finished(self, df: pd.DataFrame) -> None:
        """Resets structural elements reflecting accurately received query output."""
        self.result_df = df
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.export_btn.setEnabled(not df.empty)
        self._populate_table(df)
        self.status_bar.showMessage(f"Found {len(df)} scenes")

    def _on_query_error(self, msg: str) -> None:
        """Flags user issues interrupting thread continuation sequences."""
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.status_bar.showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Query Error", msg)

    def _populate_table(self, df: pd.DataFrame) -> None:
        """Initializes internal structural updates referencing underlying tabular data."""
        model = PandasModel(df)
        self.table_view.setModel(model)

    def _export_csv(self) -> None:
        """Bridges data frames safely to external storage media requests."""
        if self.result_df is None or self.result_df.empty:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "satellite_results.csv", "CSV (*.csv)")
        if path:
            self.result_df.to_csv(path, index=False)
            self.status_bar.showMessage(f"Exported to {path}")


def main() -> None:
    """
    Application execution anchor dictating main window routines.
    """
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = load_config()
    app = QApplication(sys.argv)
    window = MainWindow(cfg)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()