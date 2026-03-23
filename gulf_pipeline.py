#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gulf of St. Lawrence Satellite Processing Pipeline.
Performs automated cropping, format conversion (JP2 to GeoTIFF), 
and metadata recalculation for Sentinel-2 Level-2A imagery.
"""

import os
import glob
import json
import logging
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.enums import Resampling
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape

# ==============================================================================
# CONFIGURATION
# ==============================================================================

INPUT_DIR = "/meridian/sat_download/sentinel-2/2025"
OUTPUT_DIR = "/meridian/sat_download/sentinel-2/2025_cropped"
MASK_PATH = "map.geojson"
LOG_FILE = "pipeline_processing.log"

# Resolution Mapping (S2-L2A Standard)
BANDS_CONFIG = {
    "10m": ["B02", "B03", "B04", "B08", "WVP", "AOT"],
    "20m": ["SCL"],
    "60m": ["B01", "B09"]
}

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# ==============================================================================
# PROCESSING FUNCTIONS
# ==============================================================================

def load_mask(mask_path):
    """Loads and prepares the vector mask for clipping."""
    gdf = gpd.read_file(mask_path)
    return gdf.geometry.values

def calculate_stats(data, nodata_val):
    """Recalculates cloud and nodata percentages for the cropped area."""
    valid_mask = data != nodata_val
    total_pixels = data.size
    
    # SCL (Scene Classification) specific cloud detection
    # Classes 8, 9, 10 represent clouds in S2-L2A
    cloud_pixels = np.sum((data == 8) | (data == 9) | (data == 10))
    nodata_pixels = np.sum(data == nodata_val)
    
    cloud_pct = (cloud_pixels / total_pixels) * 100
    nodata_pct = (nodata_pixels / total_pixels) * 100
    
    return cloud_pct, nodata_pct

def process_scene(scene_path, mask_geometry):
    """Processes a single .SAFE directory."""
    scene_name = os.path.basename(scene_path)
    scene_out_dir = os.path.join(OUTPUT_DIR, scene_name)
    os.makedirs(scene_out_dir, exist_ok=True)
    
    logging.info(f"Processing Scene: {scene_name}")
    
    results = {
        "scene": scene_name,
        "cloud_cover": 0,
        "nodata": 0,
        "status": "Success"
    }

    try:
        # 1. Locate Bands
        for res, bands in BANDS_CONFIG.items():
            for band in bands:
                # Search for JP2 files in the GRANULE subfolders
                search_pattern = os.path.join(scene_path, "GRANULE", "*", "IMG_DATA", res, f"*{band}_{res}.jp2")
                files = glob.glob(search_pattern)
                
                if not files:
                    continue
                
                src_path = files[0]
                dst_path = os.path.join(scene_out_dir, f"{scene_name}_{band}_{res}.tif")
                
                with rasterio.open(src_path) as src:
                    # Apply Clipping
                    out_image, out_transform = mask(src, mask_geometry, crop=True)
                    out_meta = src.meta.copy()
                    
                    # Update Metadata for GeoTIFF
                    out_meta.update({
                        "driver": "GTiff",
                        "height": out_image.shape[1],
                        "width": out_image.shape[2],
                        "transform": out_transform,
                        "compress": "deflate",
                        "predictor": 2
                    })
                    
                    # Recalculate stats using SCL band if available
                    if band == "SCL":
                        c_pct, n_pct = calculate_stats(out_image[0], out_meta['nodata'])
                        results["cloud_cover"] = round(c_pct, 4)
                        results["nodata"] = round(n_pct, 4)
                    
                    with rasterio.open(dst_path, "w", **out_meta) as dest:
                        dest.write(out_image)

        # 2. Copy Original Metadata
        mtd_path = glob.glob(os.path.join(scene_path, "MTD_MSIL2A.xml"))
        if mtd_path:
            import shutil
            shutil.copy(mtd_path[0], os.path.join(scene_out_dir, "MTD_MSIL2A.xml"))

    except Exception as e:
        logging.error(f"Error processing {scene_name}: {str(e)}")
        results["status"] = f"Error: {str(e)}"

    return results

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    logging.info("Starting Gulf Pipeline...")
    mask_geom = load_mask(MASK_PATH)
    scenes = [f.path for f in os.scandir(INPUT_DIR) if f.is_dir() and f.name.endswith(".SAFE")]
    
    inventory = []
    
    for scene in scenes:
        res = process_scene(scene, mask_geom)
        inventory.append(res)
    
    # Export Inventory
    df = pd.DataFrame(inventory)
    df.to_csv(os.path.join(OUTPUT_DIR, "processing_inventory.csv"), index=False)
    logging.info("Pipeline Execution Finished.")

if __name__ == "__main__":
    main()
