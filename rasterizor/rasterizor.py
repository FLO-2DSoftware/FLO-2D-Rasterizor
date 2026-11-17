# -*- coding: utf-8 -*-
"""FLO-2D Rasterizor QGIS plugin.

Convert FLO-2D grid output tables to GeoTIFF rasters and calculate the
cell-by-cell difference between two raster layers.

Copyright (C) 2023-2026 FLO-2D Software, Inc.
Original author: Karen O'Brien, Robson Pachaly
License: GPL-2.0-or-later (see LICENSE.md).
"""

import os
from pathlib import Path

import numpy as np
from osgeo import gdal

from qgis.PyQt.QtCore import QCoreApplication, QSettings, Qt, QTranslator
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsMapLayerProxyModel,
    QgsMessageLog,
    QgsProcessingUtils,
    QgsProject,
    QgsRasterBandStats,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
)
from qgis.gui import QgsProjectionSelectionWidget

import processing

from .rasterizor_dialog import RasterizorDialog


PLUGIN_NAME = "FLO-2D Rasterizor"
LOG_TAG = "FLO-2D Rasterizor"
NODATA_VALUE = -9999.0

# Three-stop color ramps for the five FLO-2D output categories.
STYLE_COLORS = {
    0: ("#ffffff", "#add8e6", "#0000ff"),  # Depth
    1: ("#ffffff", "#98fb98", "#008000"),  # Velocity
    2: ("#000000", "#808080", "#ffffff"),  # Elevation
    3: ("#008000", "#ffff00", "#ff0000"),  # Time
    4: ("#ffffff", "#add8e6", "#0000ff"),  # Flow
}


class Rasterizor:
    """Manage Rasterizor's QGIS integration, dialog, and raster operations."""

    def __init__(self, iface):
        """Initialize the plugin using the QGIS interface supplied by QGIS."""
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self.menu = self.tr("&FLO-2D Rasterizor")
        self.actions = []
        self.cellSize = 30.0  # Retained for compatibility with existing code.
        self.crs = QgsProject.instance().crs()
        self.translator = None
        self._install_translation()

        self.dlg = RasterizorDialog()
        self.dlg.setWindowFlags(
            self.dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.projectionSelector = QgsProjectionSelectionWidget()
        self._connect_dialog()

    @staticmethod
    def tr(message):
        """Translate a plugin interface string using Qt's translation system."""
        return QCoreApplication.translate("FLO-2DRasterizor", message)

    def _install_translation(self):
        """Load a matching translation catalog if the plugin provides one."""
        locale = str(QSettings().value("locale/userLocale", "en"))[:2]
        catalog = self.plugin_dir / "i18n" / f"FLO-2DRasterizor_{locale}.qm"
        if catalog.is_file():
            translator = QTranslator()
            if translator.load(str(catalog)):
                QCoreApplication.installTranslator(translator)
                self.translator = translator

    def _connect_dialog(self):
        """Connect the existing Qt Designer widgets to their handlers."""
        self.dlg.runButton.clicked.connect(self.run)
        self.dlg.runButton_2.clicked.connect(self.run_comparison)
        self.dlg.cancelButton.clicked.connect(self.closeDialog)
        self.dlg.cancelButton_2.clicked.connect(self.closeDialog)
        raster_filter = QgsMapLayerProxyModel.RasterLayer
        self.dlg.readFile_1.setFilters(raster_filter)
        self.dlg.readFile_2.setFilters(raster_filter)

    def initGui(self):
        """Add Rasterizor to the QGIS Plugins menu and toolbar."""
        action = QAction(
            QIcon(str(self.plugin_dir / "icon.png")),
            self.tr(PLUGIN_NAME),
            self.iface.mainWindow(),
        )
        action.triggered.connect(self.open)
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)

    def unload(self):
        """Remove plugin actions and translation resources when unloaded."""
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()
        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def closeDialog(self):
        """Close the Rasterizor dialog."""
        self.dlg.close()

    def open(self):
        """Open the dialog, requiring a projected project CRS.

        A projected CRS is necessary because the output cell dimensions are
        expressed in the CRS's map units, not angular degrees.
        """
        self.crs = QgsProject.instance().crs()
        if not self.crs.isValid() or self.crs.isGeographic():
            QMessageBox.warning(
                self.dlg,
                "Projected CRS required",
                "Set the QGIS project to a valid projected coordinate "
                "reference system before using Rasterizor.",
            )
            return

        self.dlg.crsselector.setCrs(self.crs)
        self.dlg.crsselector_2.setCrs(self.crs)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    @staticmethod
    def _output_path(directory, layer_name):
        """Return an output GeoTIFF path after validating the layer name."""
        name = layer_name.strip()
        if not name or name in {".", ".."} or any(
            char in name for char in '<>:"/\\|?*'
        ):
            raise ValueError("Enter a valid output layer name without path characters.")
        folder = Path(directory) if directory else Path(QgsProcessingUtils.tempFolder())
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder / f"{name}.tif")

    @staticmethod
    def _remove_existing_layer(layer_name):
        """Remove project layers with a matching name before replacing output."""
        project = QgsProject.instance()
        for layer in list(project.mapLayersByName(layer_name)):
            project.removeMapLayer(layer.id())


    @staticmethod
    def _read_grid_values(input_file):
        """Read FLO-2D grid output records.

        Expected format:
            cell_id  x_coordinate  y_coordinate  value

        Blank lines and nonnumeric headers are ignored.

        Args:
            input_file (str): Path to the FLO-2D output file.

        Returns:
            list[tuple]: List of (x, y, value) records.

        Raises:
            ValueError: If a record is malformed or no valid records exist.
        """
        points = []

        with open(input_file, "r", encoding="utf-8-sig") as stream:
            for line_number, line in enumerate(stream, start=1):
                fields = line.split()

                # Skip blank lines and headers.
                if not fields or not fields[0].isdigit():
                    continue

                if len(fields) < 4:
                    raise ValueError(
                        f"Line {line_number}: expected cell ID, X, Y, value."
                    )

                try:
                    x, y, value = map(float, fields[1:4])
                except ValueError as exc:
                    raise ValueError(
                        f"Line {line_number}: invalid numeric value."
                    ) from exc

                if not np.isfinite([x, y, value]).all():
                    raise ValueError(
                        f"Line {line_number}: non-finite coordinate or value."
                    )

                points.append((x, y, value))

        if not points:
            raise ValueError("No valid FLO-2D grid records were found.")

        return points


    @staticmethod
    def _infer_cell_size(points):
        """Estimate square cell spacing from distinct X and Y coordinates.

        Uses the smallest positive coordinate separation. The input is assumed
        to represent a regular, axis-aligned FLO-2D grid.
        """
        x_values = np.unique([point[0] for point in points])
        y_values = np.unique([point[1] for point in points])
        gaps = []
        for coordinates in (x_values, y_values):
            if len(coordinates) > 1:
                positive = np.diff(coordinates)
                gaps.extend(positive[positive > 0].tolist())
        if not gaps:
            raise ValueError("At least two distinct grid coordinates are needed.")
        return min(gaps)

    def grid_output_to_raster(self, input_file, raster_file, nodata_value=NODATA_VALUE):
        """Convert FLO-2D grid output records to a georeferenced GeoTIFF.

        FLO-2D Output file format:  ge_num, xcoord, ycoord, var

        Reads grid cell coordinates and associated output values, constructs
        a raster using the grid cell spacing, and assigns the project CRS.

        Grid coordinates represent cell centers. Missing cells are assigned
        the specified NoData value.

        Args:
            input_file (str): Path to the FLO-2D output file.
            raster_file (str): Destination GeoTIFF file path.
            nodata_value (float): Value assigned to cells without data.
        """
        self.dlg.plainTextEdit.appendPlainText("Reading data...")
        points = self._read_grid_values(input_file)
        cell_size = self._infer_cell_size(points)
        self.cellSize = cell_size

        x_coords = np.array([point[0] for point in points])
        y_coords = np.array([point[1] for point in points])
        min_x, max_x = float(x_coords.min()), float(x_coords.max())
        min_y, max_y = float(y_coords.min()), float(y_coords.max())
        columns = int(round((max_x - min_x) / cell_size)) + 1
        rows = int(round((max_y - min_y) / cell_size)) + 1
        data = np.full((rows, columns), nodata_value, dtype=np.float32)

        for x, y, value in points:
            column = int(round((x - min_x) / cell_size))
            row = int(round((max_y - y) / cell_size))
            data[row, column] = value

        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(raster_file, columns, rows, 1, gdal.GDT_Float32)
        if dataset is None:
            raise RuntimeError(f"GDAL could not create {raster_file}")
        try:
            dataset.SetGeoTransform(
                (min_x - cell_size / 2, cell_size, 0, max_y + cell_size / 2, 0, -cell_size)
            )
            dataset.SetProjection(self.crs.toWkt())
            band = dataset.GetRasterBand(1)
            band.SetNoDataValue(float(nodata_value))
            band.WriteArray(data)
            band.FlushCache()
            dataset.FlushCache()
        finally:
            dataset = None  # Close the GDAL dataset and release the file.

    def run(self):
        """Rasterize the selected FLO-2D output file and display its result."""
        input_file = self.dlg.readfile.filePath().strip()
        layer_name = self.dlg.lineEdit_layerName.text().strip()
        try:
            if not input_file or not os.path.isfile(input_file):
                raise ValueError("Select an existing FLO-2D output file.")
            output_file = self._output_path(
                self.dlg.outputFile.filePath(), layer_name
            )
            self._remove_existing_layer(layer_name)
            self.grid_output_to_raster(input_file, output_file)
            layer = self.iface.addRasterLayer(output_file, layer_name)
            if layer is None or not layer.isValid():
                raise RuntimeError("The generated GeoTIFF could not be loaded.")
            self.setStyle(layer, self.dlg.style_cbo.currentIndex())
            self.dlg.plainTextEdit.appendPlainText("Process complete!")
        except (OSError, ValueError, RuntimeError) as exc:
            self._report_error(str(exc))

    def run_comparison(self):
        """Subtract raster 2 from raster 1 and style the resulting layer."""
        first = self.dlg.readFile_1.currentLayer()
        second = self.dlg.readFile_2.currentLayer()
        layer_name = self.dlg.lineEdit_layerName_2.text().strip()
        try:
            if first is None or second is None or not first.isValid() or not second.isValid():
                raise ValueError("Select two valid raster layers.")
            output_file = self._output_path(
                self.dlg.outputFile_2.filePath(), layer_name
            )
            self._remove_existing_layer(layer_name)
            difference = self.raster_comparison(first, second, output_file, layer_name)
            if not difference.isValid():
                raise RuntimeError("The difference raster could not be loaded.")
            QgsProject.instance().addMapLayer(difference)
            self.setStyle(difference, 5)
            self.dlg.plainTextEdit_2.appendPlainText("Process complete!")
        except (OSError, ValueError, RuntimeError) as exc:
            self._report_error(str(exc))

    def raster_comparison(self, raster_1, raster_2, raster_file, layer_name):
        """Calculate ``raster_1 - raster_2`` with the QGIS raster calculator.

        Both raster layers are included in the processing inputs so that the
        calculator can resolve their band references.
        """
        expression = f'"{raster_1.name()}@1" - "{raster_2.name()}@1"'
        QgsMessageLog.logMessage(expression, LOG_TAG, Qgis.Info)
        result = processing.run(
            "qgis:rastercalculator",
            {
                "EXPRESSION": expression,
                "LAYERS": [raster_1, raster_2],
                "CELLSIZE": 0,
                "EXTENT": None,
                "CRS": raster_1.crs(),
                "OUTPUT": raster_file,
            },
        )
        return QgsRasterLayer(result["OUTPUT"], layer_name)

    def setStyle(self, layer, style):
        """Apply the selected FLO-2D color ramp to the first raster band."""
        if layer is None or not layer.isValid():
            raise ValueError("Cannot style an invalid raster layer.")
        provider = layer.dataProvider()
        stats = provider.bandStatistics(1, QgsRasterBandStats.All, layer.extent(), 0)
        minimum = float(stats.minimumValue)
        maximum = float(stats.maximumValue)

        if style == 5:
            ramp = self._difference_ramp(minimum, maximum)
        else:
            if style not in STYLE_COLORS:
                raise ValueError(f"Unknown raster style index: {style}")
            # Match the original display threshold for non-difference maps.
            minimum = max(minimum, 0.01)
            ramp = QgsGradientColorRamp(
                QColor(STYLE_COLORS[style][0]),
                QColor(STYLE_COLORS[style][2]),
                False,
                [QgsGradientStop(0.5, QColor(STYLE_COLORS[style][1]))],
            )

        # A constant raster needs a nonzero classification range.
        if maximum <= minimum:
            maximum = minimum + max(abs(minimum) * 0.001, 0.001)

        shader = QgsRasterShader()
        renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
        renderer.setClassificationMin(minimum)
        renderer.setClassificationMax(maximum)
        renderer.createShader(ramp, clip=(style != 5))
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    @staticmethod
    def _difference_ramp(minimum, maximum):
        """Build the blue-to-red difference ramp with a transparent center."""
        span = maximum - minimum
        if span <= 0:
            # Avoid division by zero for constant-value difference rasters.
            return QgsGradientColorRamp(QColor("#08306b"), QColor("#ff0000"))

        stops = [
            (-0.1, QColor(158, 202, 225)),
            (-0.05, QColor(158, 202, 225, 0)),
            (0.0, QColor(65, 171, 93, 0)),
            (0.05, QColor(255, 127, 0, 0)),
            (0.1, QColor(255, 127, 0)),
        ]
        # QGIS gradient stops must lie within the ramp's [0, 1] interval.
        gradient_stops = [
            QgsGradientStop((value - minimum) / span, color)
            for value, color in stops
            if minimum < value < maximum
        ]
        return QgsGradientColorRamp(
            QColor("#08306b"), QColor("#ff0000"), False, gradient_stops
        )

    def _report_error(self, message):
        """Report a processing failure to both QGIS and the user."""
        QgsMessageLog.logMessage(message, LOG_TAG, Qgis.Critical)
        QMessageBox.critical(self.dlg, PLUGIN_NAME, message)
