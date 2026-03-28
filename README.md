# Satellite Image Dataset: Gulf of St. Lawrence (Sentinel-2)

##  Overview
This dataset consists of multispectral images from the **Sentinel-2 (Level-2A)** satellite, processed specifically for the **Gulf of St. Lawrence, Canada** region. The purpose of this dataset is to provide high-quality data for climate prediction research and Machine Learning models.

Unlike raw ESA data, this dataset went through an optimization pipeline that performs spatial cropping and format conversion to maximize processing performance.

---

##  File Structure and Paths
Data is organized by Year and by individual `.SAFE` folders for each scene, maintaining the original naming convention for traceability.

**Base Path:** `/meridian/sat_download/sentinel-2/`

### Example Directory Structure:
```text
/sentinel-2/
│
├── inventario_cropped_teste_formatado.csv     # Full catalog (Cloud, NoData, Tiles)
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

##  Coverage Map (Processed Tiles)
Below are the Sentinel-2 Tiles that make up the coverage of this dataset over the Gulf of St. Lawrence:

| Zone | Available Tiles |
| :--- | :--- |
| **West** | T19TGM, T19TGN, T19UDP, T19UDQ, T19UEP, T19UEQ, T19UFP, T19UFQ, T19UFR |
| **Central** | T19UGP, T19UGQ, T19UGR, T20TLR, T20TLS, T20TLT, T20TMR, T20TMS, T20TMT, T20ULA, T20ULU, T20ULV |
| **East** | T20TNR, T20TNS, T20TNT, T20TPR, T20TPS, T20TPT, T20TQS, T20TQT, T20UMA, T20UMU, T20UMV, T20UNA |
| **Far East** | T20UNU, T20UNV, T20UPA, T20UPU, T20UPV, T20UQA, T20UQB, T20UQU, T20UQV, T21TUM |
| **North/East** | T21TUN, T21TVN, T21UUP, T21UUQ, T21UUR, T21UUS, T21UVP, T21UVQ, T21UVR, T21UVS, T21UVT |


## Tile Map
<img width="4200" height="2950" alt="mapa_cobertura_tiles" src="https://github.com/user-attachments/assets/f62d2025-ff29-4b03-8d13-3c8288b41f9c" />

## Real Photo

<img width="1246" height="946" alt="image" src="https://github.com/user-attachments/assets/36beb637-847b-48a7-b085-b1500505c16c" />

---

##  Current Dataset Statistics
*Fill in the information below after the final pipeline run:*

* **Number of Tiles:** `54`
* **Total Scenes:** `______`
* **Time Period:** `______` to `______`
* **Total Disk Space:** `______ GB`
* **Compression Configuration:** `GeoTIFF (Deflate, Predictor 2)`

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


## 1. Acquisition Pipeline (`satellite_downloader.py`)

This section describes the steps required to set up the environment and run the automated download script.

### 1.1 Prerequisites
The script uses the **Rich** library for the visual interface and **Aiohttp/Aiofiles** for high-performance asynchronous operations.

* **Python**: 3.10 or higher.
* **CDSE Account**: A registration at the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) is required.

### 1.2 Dependency Setup
```bash
# Install dependencies
pip install requests aiohttp aiofiles rich
```
### 1.3 Credentials and Variable Configuration
Before running, open the `satellite_downloader.py` file and adjust the following constants in the `CONFIGURATION` block:

* **`USERNAME` / `PASSWORD`**: Copernicus portal credentials.
* **`DATE_START` / `DATE_END`**: The desired time range for the search.
* **`DOWNLOAD_DIR`**: The absolute path where data will be saved (Ex: `/meridian/sat_download/sentinel-2/2025`).
* **`CONCURRENCY_LIMIT`**: Number of simultaneous downloads (default: 4).

### 1.4 Error Handling and Validation
* **Download Failures**: If persistent network errors or timeouts occur after the 20 configured retries, the script will generate a file named `FAILED_[TIMESTAMP].txt` inside the download directory containing the list of paths of the files that failed.
* **Integrity Validation**: The script automatically checks the file size (`Content-Length`) before finalizing the atomic download. If the downloaded size does not match the expected size, the `.part` file is discarded and the download is restarted.

---

## 2. Data Processing Pipeline (`gulf_pipeline.py`)

After image acquisition, `gulf_pipeline.py` performs the standardization and optimization of data for the Gulf of St. Lawrence.

### 2.1 Dependency Setup
The pipeline depends on specific geospatial libraries (`rasterio`, `geopandas`, `shapely`).
```bash
# Install pipeline dependencies
pip install rasterio geopandas shapely numpy pandas
```

### 2.2 Pipeline Configuration and Execution
In the `CONFIGURATION` block of the `gulf_pipeline.py` file, adjust the following parameters before starting:

* **`INPUT_DIR`**: Folder containing the original `.SAFE` products (downloaded by the previous script).
* **`OUTPUT_DIR`**: Location where the cropped and optimized images will be saved.
* **`MASK_PATH`**: Path to the `map.geojson` file.

### 2.3 Technical Processing Details

####  Spatial Cropping
The script uses a Gulf vector mask to perform a **geometric clip** on all bands (`map.geojson`). This removes unnecessary land areas and focuses processing exclusively on the water body and coastal zones of interest, drastically reducing data volume.

####  New Format: GeoTIFF with *Lossless* Compression
Original images are converted from JPEG2000 (.jp2) to **GeoTIFF (.tif)**:
* **Performance:** Pixel access is optimized for block-based reading (tiled), enabling fast loading.
* **Compatibility:** Standard format for the main computer vision libraries (PyTorch, TensorFlow) and GIS software.
* **Compression:** We use the `Deflate` algorithm with `Predictor 2`. This is a **lossless** compression that guarantees full radiometric integrity while saving disk space.

####  The New Metadata XML (`cropped_metadata.xml`)
Since the cropping changes the total image area, the original ESA metadata no longer accurately represents the statistical reality of the scene. Therefore, the pipeline generates a **new custom XML** for each processed scene:

* **Cloud Cover (Recalculated):** The cloud percentage is recalculated by analyzing the **SCL (Scene Classification)** band. Only pixels classified as clouds (classes 8, 9, and 10) that are **within the Gulf mask** are counted. This allows filtering scenes by actual quality over the target area, ignoring clouds that are only over land.
* **NoData Detection:** Identifies empty pixels or those outside the mask geometry. This is critical so that ML models ignore these regions and do not learn patterns from "empty space".
* **Real Bounding Box:** Updates the extreme geographic coordinates based strictly on the boundaries of the performed crop.

####  File Management
* **Original XML:** The original ESA `MTD_MSIL2A.xml` file is copied in its entirety to the output folder to maintain historical traceability and orbital parameters. It remains **100% unmodified**.
* **Final Structure:** The result is a "clean" dataset, where each `.SAFE` folder contains the bands in GeoTIFF format, the original ESA XML, and the new optimized metadata XML for Gulf research.
