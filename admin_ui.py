"""
Admin web UI -- entry point. The actual implementation lives at
swingbot/admin/app.py; this file just launches it.

Run with: python admin_ui.py
Listens on ADMIN_HOST:ADMIN_PORT (default 0.0.0.0:1234).
"""
from swingbot.admin.app import main

if __name__ == "__main__":
    main()
