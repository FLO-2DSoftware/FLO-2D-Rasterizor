# FLO-2D Rasterizor

![FLO-2D logo](https://github.com/FLO-2DKaren/FLO-2D-Rasterizor/assets/39889306/05a2477e-3cca-4240-bb32-0cd4e721596c)

**FLO-2D Rasterizor** is a QGIS plugin for quickly converting FLO-2D grid output files into georeferenced GeoTIFF rasters. It can also calculate the difference between two raster layers.

## Features

### Create rasters from FLO-2D output

Convert supported FLO-2D output files into rasters and apply a predefined color style for depth, velocity, elevation, time, or flow.

![Raster creation interface](https://github.com/FLO-2DKaren/FLO-2D-Rasterizor/assets/39889306/21fca9e7-8b6c-44f1-91a1-76aad1b868d6)

### Compare rasters

Calculate the difference between two raster layers and display the resulting difference raster in QGIS.

![Raster comparison interface](https://github.com/FLO-2DKaren/FLO-2D-Rasterizor/assets/39889306/e9310aa5-cc14-4222-ac2f-7f9fc1bc0a6c)

## Supported input format

Raster creation expects a text file containing four whitespace-separated columns:

| Column | Description |
| --- | --- |
| `GE` | FLO-2D grid element number |
| `X` | Grid cell center X coordinate |
| `Y` | Grid cell center Y coordinate |
| `Value` | Output value to map (for example, depth, velocity, water surface elevation, or time) |

Examples of FLO-2D output files that may use this format include:

- `DEPFP.OUT`
- `DEPTH.OUT`
- `VELFP.OUT`
- `TIMEONEFT.OUT`
- `MAXWSELEV.OUT`

**Note:** Check the columns in your specific output file before importing it. Not every FLO-2D output file uses this format.

## Installation

Install **FLO-2D Rasterizor** through the QGIS Plugin Manager when it is available in your configured plugin repository.

For development or manual installation, download the repository and place the plugin files in the appropriate QGIS Python plugins directory. Restart QGIS or reload the plugin to pick up changes.

## Basic usage

### Raster creation

1. Open FLO-2D Rasterizor in QGIS.
2. Select a supported FLO-2D output text file.
3. Set the output folder and raster layer name.
4. Confirm the coordinate reference system and select a raster style.
5. Run the conversion. The GeoTIFF is added to the QGIS project.

### Raster comparison

1. Load the two rasters you want to compare into QGIS.
2. Select both rasters in the comparison tab.
3. Choose an output folder and layer name.
4. Run the comparison to create a difference raster.

For meaningful comparisons, the input rasters should use compatible coordinate systems, cell sizes, and grid alignment.

## Documentation and releases

- [Repository](https://github.com/FLO-2DSoftware/FLO-2D-Rasterizor)
- [Releases](https://github.com/FLO-2DSoftware/FLO-2D-Rasterizor/releases)
- [Wiki](https://github.com/FLO-2DSoftware/FLO-2D-Rasterizor/wiki)

See the FLO-2D Data Input Manual for descriptions of the available output files and their formats.

## Report an issue

Found a bug or have a suggestion? [Open an issue](https://github.com/FLO-2DSoftware/FLO-2D-Rasterizor/issues).

## License

See [LICENSE.md](LICENSE.md) for license information.
