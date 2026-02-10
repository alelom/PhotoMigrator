"""
Pydantic request/response models for the web API.
API uses snake_case; runner maps to ARGS keys (kebab-case).
"""
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Google Takeout ---
class GoogleTakeoutRequest(BaseModel):
    takeout_folder: str = Field(..., description="Path to Google Takeout folder")
    output_folder: Optional[str] = Field(None, description="Output folder (default: <takeout>_processed_<timestamp>)")
    google_output_folder_suffix: str = Field("processed", description="Suffix for output folder")
    google_albums_folders_structure: str = Field("flatten", description="albums: flatten | year | year/month | year-month")
    google_no_albums_folders_structure: str = Field("year/month", description="no-albums folder structure")
    google_ignore_check_structure: bool = False
    google_no_symbolic_albums: bool = False
    google_remove_duplicates_files: bool = False
    google_rename_albums_folders: bool = False
    google_skip_extras_files: bool = False
    google_skip_move_albums: bool = False
    google_skip_gpth_tool: bool = False
    google_skip_preprocess: bool = False
    google_skip_postprocess: bool = False
    google_keep_takeout_folder: bool = False
    show_gpth_info: bool = True
    show_gpth_errors: bool = True


# --- Automatic Migration ---
class AutomaticMigrationRequest(BaseModel):
    source: str = Field(..., description="Source: path or immich-1, synology-2, etc.")
    target: str = Field(..., description="Target: path or immich-1, synology-2, etc.")
    move_assets: bool = False
    dashboard: bool = True
    parallel_migration: bool = True
    show_gpth_info: bool = True


# --- Upload/Download (cloud) ---
class UploadAlbumsRequest(BaseModel):
    albums_folder: str = Field(..., description="Path to folder containing album subfolders")
    client: str = Field("synology", description="synology | immich")
    account_id: int = Field(1, ge=1, le=3)


class DownloadAlbumsRequest(BaseModel):
    output_folder: str = Field(..., description="Where to download")
    albums: list[str] = Field(..., description="Album names or ['ALL']")
    client: str = Field("synology", description="synology | immich")
    account_id: int = Field(1, ge=1, le=3)


def api_to_args(mode: str, body: dict[str, Any]) -> dict[str, Any]:
    """
    Map API request body (snake_case) to ARGS-style dict (kebab-case keys).
    Only includes keys present in body; runner will merge with defaults.
    """
    # Generic: snake_case -> kebab-case
    def to_kebab(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            key = k.replace("_", "-")
            out[key] = v
        return out

    return to_kebab(body)
