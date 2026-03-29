#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
==============================================================================
1. Acquisition Pipeline
==============================================================================
This section describes the steps required to set up the environment and run 
the automated download script.

1.1 Prerequisites
-----------------
The script uses the Rich library for the visual interface and Aiohttp/Aiofiles 
for high-performance asynchronous operations.
- Python: 3.10 or higher.
- CDSE Account: A registration at the Copernicus Data Space Ecosystem is required.

1.2 Dependency Setup
--------------------
# Install dependencies
pip install requests aiohttp aiofiles rich

1.3 Credentials and Variable Configuration
-----------------------------------------
Before running, open the satellite_downloader.py file and adjust the following 
constants in the CONFIGURATION block:
- USERNAME / PASSWORD: Copernicus portal credentials.
- DATE_START / DATE_END: The desired time range for the search.
- DOWNLOAD_DIR: The absolute path where data will be saved 
  (Ex: /meridian/sat_download/sentinel-2/2025).
- CONCURRENCY_LIMIT: Number of simultaneous downloads (default: 4).

1.4 Error Handling and Validation
---------------------------------
- Download Failures: If persistent network errors or timeouts occur after the 
  20 configured retries, the script will generate a file named 
  FAILED_[TIMESTAMP].txt inside the download directory containing the list 
  of paths of the files that failed.
- Integrity Validation: The script automatically checks the file size 
  (Content-Length) before finalizing the atomic download. If the downloaded 
  size does not match the expected size, the .part file is discarded and 
  the download is restarted.

==============================================================================
Satellite Imagery Downloader for Copernicus Data Space Ecosystem (CDSE).
Optimized for high-concurrency downloads with robust error handling and 
real-time progress monitoring.
==============================================================================
"""

import os
import sys
import requests
import aiohttp
import asyncio
import time
import random
import aiofiles
import re
import warnings
from urllib.parse import quote
from datetime import datetime

# ==============================================================================
# UI COMPONENTS (RICH)
# ==============================================================================
try:
    from rich.console import Console
    from rich.progress import (
        Progress, BarColumn, TextColumn, TimeRemainingColumn,
        TransferSpeedColumn, DownloadColumn, SpinnerColumn
    )
    from rich.live import Live
    from rich.table import Table
    from rich.layout import Layout
    from rich.panel import Panel
    from rich import box
except ImportError:
    print("Error: 'rich' library not installed.")
    print("Install it using: pip install rich")
    sys.exit(1)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Credentials (Should be managed via environment variables in production)
USERNAME = ""
PASSWORD = ""

# Area of Interest (AOI Polygon)
AOI_POLYGON = [
    [50.818847, -64.407882], [50.845657, -62.391585], [51.072921, -60.056926],
    [51.826831, -58.167974], [50.832254, -57.000644], [49.857090, -56.979419],
    [48.243699, -57.255334], [47.201458, -59.101837], [46.358490, -59.887132],
    [45.304774, -61.700508], [45.409172, -63.759254], [46.149270, -65.372291],
    [47.370536, -66.497173], [48.126869, -67.240019], [48.413843, -68.900514],
    [48.365273, -69.900102], [49.502347, -68.973655], [50.763957, -67.337898],
    [50.818847, -64.407882],
]

# Date Range
DATE_START = "2025-01-01"
DATE_END   = "2025-12-31"

# Filters
IMPORTANT_TILES = []
MAX_CLOUD_COVER = 100
MAX_SCENES_LIMIT = 100000

# Directory Setup
DOWNLOAD_DIR = "/meridian/sat_download/sentinel-2/2025"

# Performance Settings
CONCURRENCY_LIMIT = 4            
MAP_CONCURRENCY = 12             
NODE_RETRIES = 20                
DOWNLOAD_RETRIES = 20            
CHUNK_SIZE = 64 * 1024

# Timeouts
NODE_TIMEOUT = aiohttp.ClientTimeout(total=120, connect=30, sock_read=60)
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=None, connect=30, sock_read=120)

# Targeted Sentinel-2 Files
WANTED_FILES = [
    "B02", "B03", "B04", "B08",  # 10m bands
    "B01", "B09",                # Atmospheric bands
    "WVP", "AOT", "SCL",         # Physical maps
    "MTD_MSIL2A.xml"             # Metadata
]

# CDSE Endpoints
AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
DOWNLOAD_URL  = "https://download.dataspace.copernicus.eu/odata/v1"

# Environment Check (Tty detection)
TEXT_MODE = not sys.stdout.isatty()
console = Console(force_terminal=not TEXT_MODE, no_color=TEXT_MODE, width=120)

def log_msg(msg: str):
    print(msg, flush=True)

# ==============================================================================
# CORE CLASSES
# ==============================================================================

class TokenManager:
    """Handles OAuth2 token lifecycle and refresh logic."""
    def __init__(self, user, password):
        self.user = user
        self.password = password
        self.token = None
        self.expires_at = 0
        self.last_refresh_time = 0
        self._lock = asyncio.Lock()

    async def get_token(self, session, force_refresh: bool = False):
        async with self._lock:
            now = time.time()
            if not force_refresh and self.token and now < self.expires_at - 60:
                return self.token

            if force_refresh and (now - self.last_refresh_time < 5) and self.token:
                return self.token

            payload = {
                "grant_type": "password",
                "username": self.user,
                "password": self.password,
                "client_id": "cdse-public",
            }
            async with session.post(AUTH_URL, data=payload, timeout=NODE_TIMEOUT) as resp:
                if resp.status != 200:
                    txt = await resp.text()
                    raise RuntimeError(f"Auth Error ({resp.status}): {txt[:500]}")
                js = await resp.json()
                self.token = js["access_token"]
                self.expires_at = time.time() + js.get("expires_in", 600)
                self.last_refresh_time = time.time()
                return self.token

# ==============================================================================
# UTILITIES & SEARCH
# ==============================================================================

def polygon_to_wkt(points):
    """Converts AOI list to WKT Polygon string."""
    clean_points = []
    for p in points:
        if p[0] > 0 and p[1] < 0: # Handle potential lat/lon swap
            clean_points.append([p[1], p[0]])
        else:
            clean_points.append(p)

    if clean_points[0] != clean_points[-1]:
        clean_points.append(clean_points[0])

    coords_str = ",".join([f"{p[0]} {p[1]}" for p in clean_points])
    return f"SRID=4326;POLYGON(({coords_str}))"

def extract_tile_name(name):
    match = re.search(r"_T(\d{2}[A-Z]{3})_", name)
    return "T" + match.group(1) if match else None

def search_products(token):
    """Queries the CDSE OData catalogue for matching scenes."""
    wkt = polygon_to_wkt(AOI_POLYGON)
    filters = [
        "Collection/Name eq 'SENTINEL-2'",
        f"OData.CSC.Intersects(area=geography'{wkt}')",
        f"ContentDate/Start gt {DATE_START}T00:00:00.000Z",
        f"ContentDate/Start lt {DATE_END}T23:59:59.999Z",
        "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'S2MSI2A')",
        f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/Value lt {MAX_CLOUD_COVER})",
    ]

    if IMPORTANT_TILES:
        tile_filters = [f"contains(Name, '{tile}')" for tile in IMPORTANT_TILES]
        filters.append(f"({' or '.join(tile_filters)})")

    query_url = f"{CATALOGUE_URL}/Products?$filter={' and '.join(filters)}&$orderby=ContentDate/Start desc"
    headers = {"Authorization": f"Bearer {token}"}

    all_products = []
    next_url = f"{query_url}&$top=1000"

    if TEXT_MODE:
        log_msg("CATALOGUE | Searching for scenes...")
    else:
        console.print("[bold green]Searching for scenes in catalogue...[/bold green]")

    while next_url and len(all_products) < MAX_SCENES_LIMIT:
        resp = requests.get(next_url, headers=headers, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError(f"Search failed: {resp.status_code} {resp.text[:500]}")
        data = resp.json()
        batch = data.get("value", []) or []
        for p in batch:
            if IMPORTANT_TILES:
                tile = extract_tile_name(p.get("Name", ""))
                if tile and tile in IMPORTANT_TILES:
                    all_products.append(p)
            else:
                all_products.append(p)
        next_url = data.get("@odata.nextLink")

    return all_products

# ==============================================================================
# ASYNC NODE RESOLUTION
# ==============================================================================

def _get_backoff(attempt: int) -> float:
    s = min(60.0, 1.0 * (2 ** attempt))
    return s * (0.7 + random.random() * 0.6)

async def _fetch_json_retry(session, tm: TokenManager, url: str, label: str):
    for attempt in range(NODE_RETRIES):
        try:
            token = await tm.get_token(session)
            headers = {"Authorization": f"Bearer {token}"}
            async with session.get(url, headers=headers, timeout=NODE_TIMEOUT) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status == 401:
                    await tm.get_token(session, force_refresh=True)
                    continue
                if resp.status in (429, 500, 502, 503, 504):
                    await asyncio.sleep(_get_backoff(attempt))
                    continue
                raise RuntimeError(f"{label} HTTP {resp.status}")
        except Exception:
            await asyncio.sleep(_get_backoff(attempt))
    raise RuntimeError(f"{label} failed after retries.")

async def list_nodes(session, tm: TokenManager, url: str, label: str):
    js = await _fetch_json_retry(session, tm, url, label)
    return js.get("value", []) or js.get("result", []) or []

async def resolve_file_urls(session, tm: TokenManager, product):
    """Maps internal product nodes to direct download URLs."""
    pid = product["Id"]
    pname = product.get("Name", "UNKNOWN")
    if not product.get("Online", False):
        return []

    base_url = f"{DOWNLOAD_URL}/Products({pid})"
    
    def val_url(*parts):
        path = "".join([f"/Nodes({quote(p)})" for p in parts])
        return f"{base_url}{path}/$value"

    def node_url(*parts):
        path = "".join([f"/Nodes({quote(p)})" for p in parts])
        return f"{base_url}{path}/Nodes"

    root_nodes = await list_nodes(session, tm, f"{base_url}/Nodes", f"Root:{pname}")
    safe_node = next((n for n in root_nodes if ".SAFE" in n.get("Name", "").upper()), None)
    if not safe_node: return []

    safe_name = safe_node["Name"]
    safe_children = await list_nodes(session, tm, node_url(safe_name), f"SAFE:{pname}")
    jobs = []

    # Metadata
    mtd = next((n for n in safe_children if "MTD_MSIL2A.xml" in n.get("Name", "")), None)
    if mtd:
        jobs.append((val_url(safe_name, mtd["Name"]), "MTD_MSIL2A.xml", mtd.get("ContentLength", 0)))

    # Granules & Images
    gran_folder = next((n for n in safe_children if "GRANULE" in n.get("Name", "")), None)
    if not gran_folder: return jobs

    granules = await list_nodes(session, tm, node_url(safe_name, gran_folder["Name"]), f"Granule:{pname}")
    if not granules: return jobs
    target_granule = granules[0]["Name"]

    img_data_nodes = await list_nodes(session, tm, node_url(safe_name, gran_folder["Name"], target_granule), f"ImgData:{pname}")
    img_folder = next((n for n in img_data_nodes if "IMG_DATA" in n.get("Name", "")), None)
    if not img_folder: return jobs

    res_nodes = await list_nodes(session, tm, node_url(safe_name, gran_folder["Name"], target_granule, img_folder["Name"]), f"Res:{pname}")

    res_mapping = {
        "R10m": ["B02", "B03", "B04", "B08", "WVP", "AOT"],
        "R20m": ["SCL"],
        "R60m": ["B01", "B09"],
    }

    for res_name, codes in res_mapping.items():
        active_codes = [c for c in codes if c in WANTED_FILES]
        if not active_codes: continue
        
        target_res = next((n for n in res_nodes if res_name in n.get("Name", "")), None)
        if not target_res: continue

        files = await list_nodes(session, tm, node_url(safe_name, gran_folder["Name"], target_granule, img_folder["Name"], target_res["Name"]), f"Files:{pname}")
        for code in active_codes:
            fnode = next((n for n in files if f"_{code}_" in n.get("Name", "")), None)
            if fnode:
                jobs.append((
                    val_url(safe_name, gran_folder["Name"], target_granule, img_folder["Name"], target_res["Name"], fnode["Name"]),
                    fnode["Name"],
                    fnode.get("ContentLength", 0)
                ))
    return jobs

# ==============================================================================
# DOWNLOAD WORKER
# ==============================================================================

async def download_worker(wid, queue, session, tm, progress, task_id, status_dict, counter, failed_list, failed_lock):
    """Asynchronous worker to process download queue."""
    while True:
        try:
            url, path, size = await queue.get()
        except asyncio.CancelledError:
            break

        fname = os.path.basename(path)
        display_name = (fname[:15] + "..." + fname[-10:]) if len(fname) > 28 else fname
        
        try:
            # Skip if exists and matches size
            if os.path.exists(path) and size and os.path.getsize(path) == size:
                if progress: progress.advance(task_id, advance=size)
                status_dict[wid] = f"[dim green]Exists:[/dim green] {display_name}"
                counter["done"] += 1
                queue.task_done()
                continue

            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_path = path + ".part"
            success = False

            for attempt in range(DOWNLOAD_RETRIES):
                try:
                    token = await tm.get_token(session)
                    headers = {"Authorization": f"Bearer {token}"}
                    status_dict[wid] = f"[bold blue]⬇ Downloading:[/bold blue] {display_name}"

                    async with session.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(tmp_path, "wb") as f:
                                async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                                    await f.write(chunk)
                                    if progress: progress.advance(task_id, advance=len(chunk))
                            
                            if size and os.path.getsize(tmp_path) != size:
                                raise RuntimeError("Size Mismatch")
                            
                            os.replace(tmp_path, path)
                            status_dict[wid] = f"[bold green]Success:[/bold green] {display_name}"
                            success = True
                            break
                        
                        if resp.status == 401:
                            await tm.get_token(session, force_refresh=True)
                            continue
                        
                        await asyncio.sleep(_get_backoff(attempt))
                except Exception:
                    if os.path.exists(tmp_path): os.remove(tmp_path)
                    await asyncio.sleep(_get_backoff(attempt))

            if not success:
                status_dict[wid] = f"[bold red]FAILED:[/bold red] {display_name}"
                async with failed_lock: failed_list.append(path)

            counter["done"] += 1
            queue.task_done()
            await asyncio.sleep(0.1)
        except Exception as e:
            status_dict[wid] = f"[red]CRASH: {str(e)[:30]}[/red]"
            queue.task_done()

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    if not TEXT_MODE:
        console.print(Panel.fit(f"[bold blue]Satellite Downloader[/bold blue]\n[dim]{DATE_START} to {DATE_END} | Threads: {CONCURRENCY_LIMIT}[/dim]"))

    tm = TokenManager(USERNAME, PASSWORD)
    
    # Initial Auth & Search
    try:
        init_session = requests.Session()
        auth_resp = init_session.post(AUTH_URL, data={"grant_type": "password", "username": USERNAME, "password": PASSWORD, "client_id": "cdse-public"})
        auth_resp.raise_for_status()
        initial_token = auth_resp.json()["access_token"]
        products = search_products(initial_token)
        if not products: return
    except Exception as e:
        console.print(f"[bold red]Initialization failed: {e}[/bold red]")
        return

    # Map product files
    queue = asyncio.Queue()
    connector = aiohttp.TCPConnector(limit=64)
    tm.token = initial_token

    async with aiohttp.ClientSession(connector=connector) as session:
        sem = asyncio.Semaphore(MAP_CONCURRENCY)
        
        async def resolve_wrapper(p):
            async with sem:
                try:
                    jobs = await resolve_file_urls(session, tm, p)
                    return (p.get("Name", "UNK"), jobs)
                except Exception:
                    return (p.get("Name", "UNK"), [])

        if TEXT_MODE:
            log_msg("MAPPING | Resolving file links...")
            results = await asyncio.gather(*(resolve_wrapper(p) for p in products))
        else:
            with Progress(SpinnerColumn(), TextColumn("[cyan]Mapping links..."), BarColumn(), expand=True) as pbar:
                task = pbar.add_task("Mapping", total=len(products))
                results = []
                for res in asyncio.as_completed([resolve_wrapper(p) for p in products]):
                    results.append(await res)
                    pbar.advance(task)

        # Build Queue
        total_bytes, total_files = 0, 0
        for pname, jobs in results:
            if not jobs: continue
            p_dir = os.path.join(DOWNLOAD_DIR, pname)
            for url, fname, size in jobs:
                total_bytes += int(size) if size else 0
                queue.put_nowait((url, os.path.join(p_dir, fname), int(size) if size else 0))
                total_files += 1

        # Execution
        status_dict = {i: "..." for i in range(CONCURRENCY_LIMIT)}
        counter, failed_list, failed_lock = {"done": 0}, [], asyncio.Lock()
        
        prog = None
        if not TEXT_MODE:
            prog = Progress(SpinnerColumn(), TextColumn("[blue]{task.description}"), BarColumn(), DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn(), expand=True)
            overall_task = prog.add_task("Downloading", total=total_bytes if total_bytes else 1)

        workers = [asyncio.create_task(download_worker(i, queue, session, tm, prog, (overall_task if not TEXT_MODE else None), status_dict, counter, failed_list, failed_lock)) for i in range(CONCURRENCY_LIMIT)]

        if TEXT_MODE:
            while not queue.empty() or counter["done"] < total_files:
                log_msg(f"STATUS | Progress: {counter['done']}/{total_files} | Failed: {len(failed_list)}")
                await asyncio.sleep(10)
        else:
            layout = Layout()
            layout.split_column(Layout(name="header", size=3), Layout(name="body"))
            with Live(layout, refresh_per_second=4, console=console):
                while counter["done"] < total_files:
                    layout["header"].update(prog)
                    t = Table(box=box.SIMPLE, expand=True)
                    t.add_column("Worker", justify="center")
                    t.add_column("Activity")
                    for i in range(CONCURRENCY_LIMIT): t.add_row(f"#{i+1}", status_dict[i])
                    layout["body"].update(Panel(t, title="Thread Monitor"))
                    await asyncio.sleep(0.5)

        for w in workers: w.cancel()
        
    if failed_list:
        log_msg(f"COMPLETED | Failures encountered: {len(failed_list)}")

if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
