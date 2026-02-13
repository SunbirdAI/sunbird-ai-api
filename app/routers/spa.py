from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter()

# Path to the React build output
# Adjust this path if your build output location changes
BUILD_DIR = Path(__file__).parent.parent / "static" / "react_build"


@router.get("/{full_path:path}")
async def serve_spa(request: Request, full_path: str):
    """
    Serve the React Single Page Application.
    Any route not matched by other API routers will fall back to this,
    returning index.html so React Router can handle the routing.
    """
    # Check if the file exists in the build directory (e.g., favicon.ico, manifest.json)
    # We skip 'assets' because that should be mounted as a StaticFiles app in main.py
    file_path = BUILD_DIR / full_path
    if file_path.exists() and file_path.is_file() and "assets" not in full_path:
        return FileResponse(file_path)

    # Otherwise, return index.html
    index_path = BUILD_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>React Build Not Found</h1><p>Please run <code>npm run build</code> in the frontend directory.</p>",
            status_code=404,
        )

    return FileResponse(index_path)
