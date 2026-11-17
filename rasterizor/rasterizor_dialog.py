"""Qt Designer dialog for the FLO-2D Rasterizor QGIS plugin.

The dialog defines the user interface. Raster processing and signal handling
are implemented in ``rasterizor.py``.
"""

from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog


UI_FILE = Path(__file__).resolve().parent / "rasterizor_dialog_base.ui"
FORM_CLASS, _ = uic.loadUiType(str(UI_FILE))


class RasterizorDialog(QDialog, FORM_CLASS):
    """Load the Rasterizor interface and initialize its style choices."""

    RASTER_STYLES = ("Depth", "Velocity", "Elevation", "Time", "Flow")

    def __init__(self, parent=None):
        """Initialize the dialog and populate the raster style selector."""
        super().__init__(parent)
        self.setupUi(self)
        self._populate_style_options()

    def _populate_style_options(self):
        """Populate styles in the order expected by the raster renderer."""
        self.style_cbo.clear()
        self.style_cbo.addItems(self.RASTER_STYLES)
