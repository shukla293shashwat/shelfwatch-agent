"""Start the app locally or on a Python/container hosting service."""
import os

import uvicorn


if __name__ == "__main__":
    # Hosts can set these variables without editing the source.
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host=host, port=port)
