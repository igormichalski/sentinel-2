#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
==============================================================================
2. Data Processing Pipeline (gulf_pipeline.py)
==============================================================================
After image acquisition, gulf_pipeline.py performs the standardization and 
optimization of data for the Gulf of St. Lawrence.

2.1 Dependency Setup
--------------------
The pipeline depends on specific geospatial libraries (rasterio, geopandas, shapely).

# Install pipeline dependencies
pip install rasterio geopandas shapely numpy pandas

2.2 Pipeline Configuration and Execution
---------------------------------------
In the CONFIGURATION block of the gulf_pipeline.py file, adjust the following 
parameters before starting:
- INPUT_DIR: Folder containing the original .SAFE products (downloaded by the 
  previous script).
- OUTPUT_DIR: Location where the cropped and optimized images will be saved.
- MASK_PATH: Path to the map.geojson file.

2.3 Technical Processing Details
--------------------------------
Spatial Cropping:
The script uses a Gulf vector mask to perform a geometric clip on all bands 
(map.geojson). This removes unnecessary land areas and focuses processing 
exclusively on the water body and coastal zones of interest, drastically 
reducing data volume.

New Format: GeoTIFF with Lossless Compression:
Original images are converted from JPEG2000 (.jp2) to GeoTIFF (.tif):
- Performance: Pixel access is optimized for block-based reading (tiled), 
  enabling fast loading.
- Compatibility: Standard format for the main computer vision libraries 
  (PyTorch, TensorFlow) and GIS software.
- Compression: We use the Deflate algorithm with Predictor 2. This is a lossless 
  compression that guarantees full radiometric integrity while saving disk space.

The New Metadata XML (cropped_metadata.xml):
Since the cropping changes the total image area, the original ESA metadata no 
longer accurately represents the statistical reality of the scene. Therefore, 
the pipeline generates a new custom XML for each processed scene:
- Cloud Cover (Recalculated): The cloud percentage is recalculated by analyzing 
  the SCL (Scene Classification) band. Only pixels classified as clouds 
  (classes 8, 9, and 10) that are within the Gulf mask are counted.
- NoData Detection: Identifies empty pixels or those outside the mask geometry. 
- Real Bounding Box: Updates the extreme geographic coordinates based strictly 
  on the boundaries of the performed crop.

File Management:
- Original XML: The original ESA MTD_MSIL2A.xml file is copied in its entirety 
  to the output folder to maintain historical traceability and orbital 
  parameters. It remains 100% unmodified.
- Final Structure: The result is a "clean" dataset, where each .SAFE folder 
  contains the bands in GeoTIFF format, the original ESA XML, and the new 
  optimized metadata XML for Gulf research.

==============================================================================
Gulf of St. Lawrence Satellite Processing Pipeline.
Performs automated cropping, format conversion (JP2 to GeoTIFF), 
and metadata recalculation for Sentinel-2 Level-2A imagery.
==============================================================================
"""

import os
import glob
import shutil
import time
import resource
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon
from concurrent.futures import ProcessPoolExecutor, as_completed

# ==============================================================================
# 1. CONFIGURATION & GLOBAL VARIABLES
# ==============================================================================
INPUT_DIR  = "/meridian/sat_download/sentinel-2/2019"
OUTPUT_DIR = "/meridian/sat_download/sentinel-2/2019_GTIFF"
MASK_PATH  = "/home/igor/compress/map.geojson"

# ==============================================================================
# RESOURCE LIMITS — Shared Server Optimization
# ==============================================================================
MAX_WORKERS   = 4      # Maximum parallel processes
NICE_LEVEL    = 0      # Process priority (0=normal, 19=minimum)
SLEEP_BETWEEN = 0      # Pause between task submissions (seconds)
MAX_RAM_GB    = 16     # RAM limit per process (GB)

def set_low_priority():
    """Sets process priority and limits RAM usage."""
    # Reduce process priority (nice)
    os.nice(NICE_LEVEL)
    # Limit maximum RAM per process
    max_bytes = MAX_RAM_GB * 1024 ** 3
    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))

# ==============================================================================
# 2. HELPER FUNCTIONS
# ==============================================================================
def parse_ext_pos_list(coords_text):
    """Converts ESA coordinate string to Shapely Polygon."""
    coords = list(map(float, coords_text.split()))
    points = [(coords[i+1], coords[i]) for i in range(0, len(coords), 2)]
    return Polygon(points)

def format_ext_pos_list(polygon):
    """Converts Shapely Polygon back to ESA coordinate string format."""
    points = list(polygon.convex_hull.exterior.coords)
    text = " ".join([f"{lat} {lon}" for lon, lat in points])
    return text

# ==============================================================================
# 3. MAIN PROCESSING FUNCTION (1 folder per worker)
# ==============================================================================
def process_folder(source_folder, gulf_polygon, mask_crs, mask_json_path):
    folder_name = os.path.basename(source_folder)
    output_folder = os.path.join(OUTPUT_DIR, folder_name)
    new_xml = os.path.join(output_folder, "cropped_metadata.xml")
    original_xml = os.path.join(source_folder, "MTD_MSIL2A.xml")

    # -------------------------------------------------
    # 0. CHECKPOINT (Skip if already processed)
    # -------------------------------------------------
    if os.path.exists(output_folder):
        if os.path.exists(new_xml):
            try:
                tree_new = ET.parse(new_xml)
                root_new = tree_new.getroot()
                if root_new.find('.//MATRIX_DIMENSION') is not None:
                    return f"[SKIPPED] {folder_name:<65} | Already processed"
            except Exception:
                pass
        shutil.rmtree(output_folder)

    # -------------------------------------------------
    # 1. NORMAL PROCESSING
    # -------------------------------------------------
    if not os.path.exists(original_xml):
        return f"[ERROR]   {folder_name:<65} | Original XML not found"

    tree_orig = ET.parse(original_xml)
    root_orig = tree_orig.getroot()
    ext_elem = root_orig.find('.//EXT_POS_LIST')

    cloud_elem = root_orig.find('.//Cloud_Coverage_Assessment')
    original_cloud_pct = float(cloud_elem.text) if cloud_elem is not None else 0.0

    nodata_elem = root_orig.find('.//NODATA_PIXEL_PERCENTAGE')
    original_nodata_pct = float(nodata_elem.text) if nodata_elem is not None else 0.0

    orig_polygon = None
    fully_inside = False

    if ext_elem is not None:
        orig_polygon = parse_ext_pos_list(ext_elem.text)

        if not gulf_polygon.intersects(orig_polygon):
            return f"[IGNORED] {folder_name:<65} | 100% OUTSIDE the Gulf"

        if gulf_polygon.contains(orig_polygon):
            fully_inside = True

    os.makedirs(output_folder)

    jp2_files = glob.glob(os.path.join(source_folder, "*.jp2"))
    was_altered = not fully_inside

    if was_altered:
        gdf_mask = gpd.read_file(mask_json_path)
        gdf_mask.set_crs(epsg=4326, allow_override=True, inplace=True)

    # -------------------------------------------------
    # 2. CONVERT TO TIFF OR CROP TO TIFF (Lossless GTiff)
    # -------------------------------------------------
    for jp2 in jp2_files:
        tif_name = os.path.basename(jp2).replace(".jp2", ".tif")
        tif_out_path = os.path.join(output_folder, tif_name)

        if fully_inside:
            with rasterio.open(jp2) as src:
                out_image = src.read()
                out_meta = src.meta.copy()
                out_meta.update({
                    "driver": "GTiff",
                    "compress": "deflate",
                    "predictor": 2
                })
                with rasterio.open(tif_out_path, "w", **out_meta) as dest:
                    dest.write(out_image)
        else:
            with rasterio.open(jp2) as src:
                mask_proj = gdf_mask.to_crs(src.crs)
                mask_geometry = [mask_proj.geometry.union_all()]

                try:
                    out_image, out_transform = mask(src, mask_geometry, crop=False, filled=True, nodata=0)
                except ValueError:
                    out_image = np.zeros((src.count, src.height, src.width), dtype=src.dtypes[0])
                    out_transform = src.transform

                out_meta = src.meta.copy()
                out_meta.update({
                    "driver": "GTiff",
                    "height": src.height,
                    "width": src.width,
                    "transform": out_transform,
                    "compress": "deflate",
                    "predictor": 2
                })
                with rasterio.open(tif_out_path, "w", **out_meta) as dest:
                    dest.write(out_image)

    # -------------------------------------------------
    # 3. RECALCULATE CLOUDS, NODATA, AND GENERATE XML
    # -------------------------------------------------
    new_cloud_pct  = original_cloud_pct
    new_nodata_pct = original_nodata_pct

    if was_altered:
        scl_files = glob.glob(os.path.join(output_folder, "*SCL_20m.tif"))
        if scl_files:
            with rasterio.open(scl_files[0]) as scl_src:
                scl_data = scl_src.read(1)
                valid_pixels = np.count_nonzero(scl_data > 0)
                cloud_pixels = np.count_nonzero(np.isin(scl_data, [8, 9, 10]))
                if valid_pixels > 0:
                    new_cloud_pct = round((cloud_pixels / valid_pixels) * 100, 4)
                new_nodata_pct = round((np.count_nonzero(scl_data == 0) / scl_data.size) * 100, 4)

    shutil.copy2(original_xml, os.path.join(output_folder, os.path.basename(original_xml)))

    sat_elem  = root_orig.find('.//SPACECRAFT_NAME')
    sat_name  = sat_elem.text if sat_elem is not None else "Sentinel-2"
    time_elem = root_orig.find('.//PRODUCT_START_TIME')
    timestamp = time_elem.text if time_elem is not None else "Unknown"

    new_coords_text = "MISSING"
    if ext_elem is not None and was_altered and orig_polygon:
        intersection_poly = orig_polygon.intersection(gulf_polygon)
        if not intersection_poly.is_empty:
            new_coords_text = format_ext_pos_list(intersection_poly)
    elif ext_elem is not None:
        new_coords_text = ext_elem.text.strip()

    file_status = "ALTERED" if was_altered else "ORIGINAL"

    with open(new_xml, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<GULF_ST_LAWRENCE_METADATA>\n')
        f.write(f'    <SPACECRAFT_NAME>{sat_name}</SPACECRAFT_NAME>\n')
        f.write(f'    <PRODUCT_START_TIME>{timestamp}</PRODUCT_START_TIME>\n')
        f.write(f'    <FILE_STATUS>{file_status}</FILE_STATUS>\n')
        f.write(f'    <MATRIX_DIMENSION>STANDARD_SQUARE_GTIFF</MATRIX_DIMENSION>\n')
        f.write(f'    <Cloud_Coverage_Assessment>{new_cloud_pct}</Cloud_Coverage_Assessment>\n')
        f.write(f'    <NODATA_PIXEL_PERCENTAGE>{new_nodata_pct}</NODATA_PIXEL_PERCENTAGE>\n')
        f.write(f'    <EXT_POS_LIST>{new_coords_text}</EXT_POS_LIST>\n')
        f.write('</GULF_ST_LAWRENCE_METADATA>\n')

    return f"[SUCCESS] {folder_name:<65} | Status: {file_status:<8} | Clouds: {new_cloud_pct:05.2f}% | NoData: {new_nodata_pct:05.2f}%"


# ==============================================================================
# 4. MULTIPROCESSING ENGINE
# ==============================================================================
if __name__ == '__main__':
    print("🚀 Starting Gulf of St. Lawrence GTiff Pipeline...")
    print(f"   Workers limited to {MAX_WORKERS} (shared server optimization)")

    if not os.path.exists(MASK_PATH):
        raise FileNotFoundError(f"[X] Mask not found at: {MASK_PATH}")

    gdf_mask     = gpd.read_file(MASK_PATH)
    gdf_mask.set_crs(epsg=4326, allow_override=True, inplace=True)
    mask_crs     = gdf_mask.crs
    gulf_polygon = gdf_mask.geometry.union_all()

    safe_folders = sorted(glob.glob(os.path.join(INPUT_DIR, "*.SAFE")))

    print(f"📦 Found {len(safe_folders)} folders to process.\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("-" * 125)
    print(f"{'LOG TYPE':<10} {'FOLDER NAME':<65} | {'DETAILS'}")
    print("-" * 125)

    with ProcessPoolExecutor(max_workers=MAX_WORKERS,
                               initializer=set_low_priority) as executor:
        futures = []
        for folder in safe_folders:
            futures.append(executor.submit(
                process_folder, folder, gulf_polygon, mask_crs, MASK_PATH
            ))
            time.sleep(SLEEP_BETWEEN)  # Submission throttle

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            print(f"[{i:04d}/{len(safe_folders):04d}] {result}", flush=True)

    print("-" * 125)
    print("🎉 Processing finished!")
