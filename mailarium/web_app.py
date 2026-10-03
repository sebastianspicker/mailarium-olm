"""Streamlit launcher: ``streamlit run mailarium/web_app.py`` executes this script as ``__main__``."""

from __future__ import annotations

from mailarium.interfaces.web.app import invalidate_runtime_cache, main

__all__ = ["invalidate_runtime_cache"]

if __name__ == "__main__":
    main()
