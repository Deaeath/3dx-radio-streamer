"""3DX Radio Streamer launcher (also the PyInstaller entry point).

    RadioStreamer.py                     start the app
    RadioStreamer.py --selftest [file]   check tools and the broadcast pipeline, write a report
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from radiostreamer.selftest import run as selftest
        args = sys.argv[sys.argv.index("--selftest") + 1:]
        sys.exit(selftest(args[0] if args else None))
    from radiostreamer.gui import run
    run()
