"""
Package script: Creates a clean distribution zip of the project.
Excludes logs, cache, temp artifacts, and archived templates.
"""
import os
import shutil
import zipfile
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, "dist")

EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
    ".antigravity",
    ".vscode",
    "logs",
    "scratch",
    "dist",
    "archive",
    "archive_templates",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
}

EXCLUDE_FILES = {
    ".env",
    "ai_config.json",
}


def clean_project_caches():
    """Remove any existing __pycache__ directories and .pyc files."""
    removed_count = 0
    for root, dirs, files in os.walk(BASE_DIR):
        for d in list(dirs):
            if d in ("__pycache__", ".pytest_cache") or "sao chép" in d.lower():
                full_path = os.path.join(root, d)
                if d in ("__pycache__", ".pytest_cache"):
                    shutil.rmtree(full_path, ignore_errors=True)
                    removed_count += 1
                dirs.remove(d)
        for f in files:
            if any(f.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
                try:
                    os.remove(os.path.join(root, f))
                    removed_count += 1
                except Exception:
                    pass
    print(f"[*] Cleaned {removed_count} cache files / directories.")


def should_include_file(rel_path: str) -> bool:
    """Check if file should be included in the release zip."""
    parts = rel_path.replace("\\", "/").split("/")
    # Exclude files inside blacklisted directories
    for part in parts:
        if part in EXCLUDE_DIRS or "sao chép" in part.lower():
            return False
    # Exclude sensitive files (.env, .env.*, ai_config.json)
    filename = os.path.basename(rel_path)
    if filename in EXCLUDE_FILES or "sao chép" in filename.lower():
        return False
    if filename.startswith(".env") and filename != ".env.example":
        return False
    # Exclude unwanted extensions
    _, ext = os.path.splitext(rel_path)
    if ext.lower() in EXCLUDE_EXTENSIONS:
        return False
    return True


def package_project(zip_name: str = None) -> str:
    """Pack project files into a clean zip archive in dist/."""
    clean_project_caches()
    os.makedirs(DIST_DIR, exist_ok=True)

    if not zip_name:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"chaos_bot_release_{date_str}.zip"

    zip_path = os.path.join(DIST_DIR, zip_name)
    file_count = 0
    total_uncompressed = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BASE_DIR):
            # Prune excluded dirs
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, BASE_DIR)
                if should_include_file(rel_path):
                    zf.write(full_path, rel_path)
                    file_count += 1
                    total_uncompressed += os.path.getsize(full_path)

    zip_size = os.path.getsize(zip_path)
    print("\n" + "=" * 50)
    print("📦 PACKAGING SUCCESSFUL!")
    print("=" * 50)
    print(f"Destination : {zip_path}")
    print(f"Total files : {file_count}")
    print(f"Raw size    : {total_uncompressed / 1024 / 1024:.2f} MB")
    print(f"Zip size    : {zip_size / 1024 / 1024:.2f} MB")
    print("=" * 50)
    return zip_path


if __name__ == "__main__":
    package_project()
