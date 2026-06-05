from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse
import logging
import re
import zipfile

import requests

from app.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class SourceDocument:
    """A downloaded source file plus metadata about where it came from."""

    path: Path
    metadata: Dict[str, str]


class SourceConnector:
    """Fetch public source links into temporary local files for ingestion."""

    def estimate_size_mb(self, source_url: str) -> float | None:
        """Best-effort source size estimate before download."""
        parsed = urlparse(source_url)
        host = parsed.netloc.lower()

        if "github.com" in host:
            owner, repo = self._parse_github_repo(source_url)
            repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
            repo_response = requests.get(repo_api_url, timeout=20)
            repo_response.raise_for_status()
            size_kb = repo_response.json().get("size")
            if size_kb is None:
                return None
            return float(size_kb) / 1024

        return None

    def requires_auth_for_anonymous(self, source_url: str, limit_mb: int) -> tuple[bool, float | None]:
        size_mb = self.estimate_size_mb(source_url)
        if size_mb is None:
            return False, None
        return size_mb > limit_mb, size_mb

    def fetch(self, source_url: str, workspace_dir: Path) -> List[SourceDocument]:
        parsed = urlparse(source_url)
        host = parsed.netloc.lower()

        if "github.com" in host:
            return self._fetch_github_repo(source_url, workspace_dir)

        if "drive.google.com" in host:
            folder_id = self._parse_google_drive_folder_id(source_url)
            if folder_id:
                return self._fetch_google_drive_folder(source_url, folder_id, workspace_dir)

            return [self._fetch_google_drive_file(source_url, workspace_dir)]

        raise ValueError("Supported demo sources are public GitHub repository URLs and public Google Drive file links.")

    def _fetch_github_repo(self, source_url: str, workspace_dir: Path) -> List[SourceDocument]:
        owner, repo = self._parse_github_repo(source_url)
        repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"

        repo_response = requests.get(repo_api_url, timeout=20)
        repo_response.raise_for_status()
        default_branch = repo_response.json().get("default_branch", "main")

        zip_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{default_branch}"
        zip_path = workspace_dir / f"{owner}_{repo}.zip"

        self._download_file(zip_url, zip_path)

        extract_dir = workspace_dir / f"{owner}_{repo}"
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)

        supported_files = [
            path
            for path in extract_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in settings.SUPPORTED_FILE_TYPES
        ]

        documents = []
        for path in supported_files:
            relative_path = self._repo_relative_path(path, owner, repo, default_branch)
            source_file_url = f"https://github.com/{owner}/{repo}/blob/{default_branch}/{relative_path}"
            documents.append(
                SourceDocument(
                    path=path,
                    metadata={
                        "source_type": "github",
                        "source_url": source_file_url,
                        "source_root": source_url,
                        "source_path": relative_path,
                        "document_id": f"github:{owner}/{repo}:{default_branch}:{relative_path}",
                    },
                )
            )

        logger.info("Fetched %s supported documents from %s/%s", len(documents), owner, repo)
        return documents

    def _fetch_google_drive_file(self, source_url: str, workspace_dir: Path) -> SourceDocument:
        file_id = self._parse_google_drive_file_id(source_url)
        if not file_id:
            raise ValueError("Google Drive URL must be a public file link or public folder link.")

        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        response = requests.get(download_url, timeout=30, stream=True)
        response.raise_for_status()

        filename = self._filename_from_response(response) or f"google_drive_{file_id}"
        suffix = Path(filename).suffix.lower()
        if suffix not in settings.SUPPORTED_FILE_TYPES:
            raise ValueError(f"Unsupported Google Drive file type: {suffix or 'unknown'}")

        destination = workspace_dir / filename
        with open(destination, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)

        return SourceDocument(
            path=destination,
            metadata={
                "source_type": "google_drive",
                "source_url": source_url,
                "source_root": source_url,
                "source_path": filename,
                "document_id": f"google_drive:{file_id}",
            },
        )

    def _fetch_google_drive_folder(
        self,
        source_url: str,
        folder_id: str,
        workspace_dir: Path,
    ) -> List[SourceDocument]:
        try:
            import gdown
        except ImportError as exc:
            raise RuntimeError("Google Drive folder ingestion requires the gdown package. Install requirements.txt again.") from exc

        output_dir = workspace_dir / f"google_drive_{folder_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        listing_error = None
        download_errors: list[str] = []
        folder_entries = []

        try:
            folder_entries = gdown.download_folder(
                url=source_url,
                output=str(output_dir),
                quiet=True,
                use_cookies=False,
                skip_download=True,
            ) or []
        except Exception as exc:
            listing_error = exc
            logger.warning("Google Drive folder listing failed; trying bulk download fallback: %s", exc)

        supported_files: list[Path] = []
        if folder_entries:
            for entry in folder_entries:
                entry_id = getattr(entry, "id", None)
                entry_path = Path(getattr(entry, "local_path", "") or getattr(entry, "path", "") or "")
                if not entry_id or entry_path.suffix.lower() not in settings.SUPPORTED_FILE_TYPES:
                    continue

                if not entry_path.is_absolute():
                    entry_path = output_dir / entry_path
                entry_path.parent.mkdir(parents=True, exist_ok=True)

                try:
                    downloaded_path = gdown.download(
                        url=f"https://drive.google.com/uc?id={entry_id}",
                        output=str(entry_path),
                        quiet=True,
                        use_cookies=False,
                    )
                except Exception as exc:
                    download_errors.append(f"{entry_path.name}: {exc}")
                    logger.warning("Skipping blocked Google Drive file %s: %s", entry_path.name, exc)
                    continue

                if downloaded_path and entry_path.is_file():
                    supported_files.append(entry_path)
                else:
                    download_errors.append(f"{entry_path.name}: Drive did not return a downloadable file URL")
                    logger.warning("Skipping Google Drive file %s because gdown returned no path", entry_path.name)

        if not supported_files:
            try:
                downloaded_paths = gdown.download_folder(
                    url=source_url,
                    output=str(output_dir),
                    quiet=True,
                    use_cookies=False,
                ) or []
            except Exception as exc:
                download_errors.append(str(exc))
                logger.warning("Google Drive folder bulk download was blocked: %s", exc)
                downloaded_paths = [str(path) for path in output_dir.rglob("*") if path.is_file()]

            supported_files = [
                Path(path)
                for path in downloaded_paths
                if Path(path).is_file() and Path(path).suffix.lower() in settings.SUPPORTED_FILE_TYPES
            ]

        if not supported_files:
            detail = (
                "Could not download any supported files from this Google Drive folder. "
                "Make sure every file is shared as 'Anyone with the link', not just the folder. "
                "Google Drive/gdown may also block files after many accesses."
            )
            if listing_error:
                detail = f"{detail} Folder listing error: {listing_error}"
            if download_errors:
                detail = f"{detail} First skipped file error: {download_errors[0]}"
            raise RuntimeError(detail)

        documents = []
        for path in supported_files:
            relative_path = str(path.relative_to(output_dir)).replace("\\", "/")
            documents.append(
                SourceDocument(
                    path=path,
                    metadata={
                        "source_type": "google_drive_folder",
                        "source_url": source_url,
                        "source_root": source_url,
                        "source_path": relative_path,
                        "document_id": f"google_drive_folder:{folder_id}:{relative_path}",
                    },
                )
            )

        if download_errors:
            logger.warning(
                "Fetched %s supported documents from Google Drive folder %s after skipping %s blocked files",
                len(documents),
                folder_id,
                len(download_errors),
            )
        else:
            logger.info("Fetched %s supported documents from Google Drive folder %s", len(documents), folder_id)
        return documents

    def _download_file(self, url: str, destination: Path) -> None:
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()

        with open(destination, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)

    def _parse_github_repo(self, source_url: str) -> tuple[str, str]:
        parsed = urlparse(source_url)
        parts = [part for part in parsed.path.split("/") if part]

        if len(parts) < 2:
            raise ValueError("GitHub URL must look like https://github.com/owner/repo")

        return parts[0], parts[1].removesuffix(".git")

    def _repo_relative_path(self, path: Path, owner: str, repo: str, branch: str) -> str:
        marker = f"{repo}-{branch}"
        parts = path.parts

        if marker in parts:
            marker_index = parts.index(marker)
            return str(Path(*parts[marker_index + 1 :])).replace("\\", "/")

        fallback = path.name
        logger.warning("Could not derive repo-relative path for %s; using %s", path, fallback)
        return fallback

    def _parse_google_drive_file_id(self, source_url: str) -> str | None:
        patterns = [
            r"/file/d/([^/]+)",
            r"[?&]id=([^&]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, source_url)
            if match:
                return match.group(1)

        return None

    def _parse_google_drive_folder_id(self, source_url: str) -> str | None:
        match = re.search(r"/drive/folders/([^/?]+)", source_url)
        if match:
            return match.group(1)

        return None

    def _filename_from_response(self, response: requests.Response) -> str | None:
        content_disposition = response.headers.get("content-disposition", "")
        match = re.search(r'filename="?([^";]+)"?', content_disposition)
        if match:
            return match.group(1)

        return None


def get_source_connector() -> SourceConnector:
    return SourceConnector()
