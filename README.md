# Satellite Image Dataset: Gulf of St. Lawrence (Sentinel-2)

##  Overview
This dataset consists of multispectral images from the **Sentinel-2 (Level-2A)** satellite, processed specifically for the **Gulf of St. Lawrence, Canada** region. The purpose of this dataset is to provide high-quality data for climate prediction research and Machine Learning models.

Unlike raw ESA data, this dataset went through an optimization pipeline that performs spatial cropping and format conversion to maximize processing performance.

---

## Products
Dashboard - [Link](https://github.com/JoaoPedroRecalcatti/Dashboard_sat.git)

Wrapper - Link

Classification Model - [Link](https://github.com/igormichalski/gulf_ice)

---

##  Extracted Band Specifications
The following bands were selected for download:

| Band | Description | Original Resolution |
| :--- | :--- | :--- |
| **B01** | Coastal Aerosol | 60m |
| **B02, B03, B04**| Blue, Green, Red | 10m |
| **B08** | NIR | 10m |
| **B09** | Water Vapor | 60m |
| **WVP** | **Water Vapor** | **10m** |
| **AOT** | **Aerosol Optical Thickness** | **10m** |
| **SCL** | Scene Classification | 20m |



---


##  File Structure and Paths
Data is organized by Year and by individual `.SAFE` folders for each scene, maintaining the original naming convention for traceability.

**Base Path:** `/meridian/sat_download/sentinel-2/`

### Example Directory Structure:
```text
/sentinel-2/
│
├── gulf_catalog.csv     # Full catalog (Cloud, NoData, Tiles)
├── map.geojson                                # Area of interest polygon
│
└── [YEAR]/                                    # Ex: 2016, 2022
    └── [SCENE_NAME].SAFE/                     # Scene folder (Ex: S2A_MSIL2A_20160106...)
        ├── MTD_MSIL2A.xml                     # Original ESA metadata
        ├── cropped_metadata.xml               # Post-processing metadata (Recalculated)
        │
        # --- GEOTIFF IMAGES (GULF CROP) ---
        ├── [NAME]_B02_10m.tif                 # Blue Band (490nm)
        ├── [NAME]_B03_10m.tif                 # Green Band (560nm)
        ├── [NAME]_B04_10m.tif                 # Red Band (665nm)
        ├── [NAME]_B08_10m.tif                 # NIR (842nm)
        ├── [NAME]_WVP_10m.tif                 # Water Vapor
        ├── [NAME]_AOT_10m.tif                 # Aerosol Optical Thickness
        ├── [NAME]_SCL_20m.tif                 # Scene Classification Map
        ├── [NAME]_B01_60m.tif                 # Coastal Aerosol
        └── [NAME]_B09_60m.tif                 # Water Vapor
```
---

##  Coverage Map (Processed Tiles)
Below are the Sentinel-2 Tiles that make up the coverage of this dataset over the Gulf of St. Lawrence, grouped by basins and UTM zones:

| Region | Available Tiles |
| :--- | :--- |
| **Gaspé Peninsula & Estuary (West - Zone 19)** | T19TGM, T19TGN, T19UDP, T19UDQ, T19UEP, T19UEQ, T19UFP, T19UFQ, T19UFR, T19UGP, T19UGQ, T19UGR |
| **Southern Sector & Maritime Provinces (NB, PEI, NS)** | T20TLR, T20TLS, T20TLT, T20TMR, T20TMS, T20TMT, T20TNR, T20TNS, T20TNT, T20TPR, T20TPS, T20TPT, T20TQS, T20TQT |
| **Anticosti Island & Central Gulf Sector** | T20ULA, T20ULU, T20ULV, T20UMA, T20UMU, T20UMV, T20UNA, T20UNU, T20UNV, T20UPA, T20UPU, T20UPV, T20UQA, T20UQB, T20UQU, T20UQV |
| **Newfoundland & Strait of Belle Isle (East - Zone 21)** | T21TUM, T21TUN, T21TVN, T21UUP, T21UUQ, T21UUR, T21UUS, T21UVP, T21UVQ, T21UVR, T21UVS, T21UVT |

## Tile Map
<img width="4200" height="2950" alt="mapa_cobertura_tiles" src="https://github.com/user-attachments/assets/f62d2025-ff29-4b03-8d13-3c8288b41f9c" />

## Real Photo

<img width="1246" height="946" alt="image" src="https://github.com/user-attachments/assets/36beb637-847b-48a7-b085-b1500505c16c" />

---

##  Processing Pipeline
The dataset was generated through two main steps:

1.  **Automated Acquisition (`satellite_downloader.py`):** Performs the search and selective download of `S2MSI2A` products via the *Copernicus Data Space Ecosystem* API. The script ensures atomic downloads and integrity validation by file size.
2.  **Cropping and Standardization (`gulf_pipeline.py`):**
    * **Cropping:** Original images were cropped using a manually drawn vector mask closely following the water boundary (`map.geojson`).
    * **GeoTIFF Conversion:** The original JPEG2000 (.jp2) format is converted to **GeoTIFF (.tif)** using *Lossless Deflate* compression with predictor level 2, ensuring no radiometric information is lost.
    * **Metadata Recalculation:** Cloud cover and *NoData* percentages were recalculated based exclusively on the cropped area.
    * **Post-processing Metadata Generation (`cropped_metadata.xml`):** Recalculated and updated data is stored in the `cropped_metadata.xml` file to keep the original image metadata files intact.
---
##  Current Dataset Statistics
*Fill in the information below after the final pipeline run:*

* **Number of Tiles:** `54`
* **Total Scenes:** `______`
* **Time Period:** `______` to `______`
* **Total Disk Space:** `______ GB`
* **Compression Configuration:** `GeoTIFF (Deflate, Predictor 2)`

---
