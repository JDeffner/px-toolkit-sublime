"""Download the pinned verified release, then exercise its actual wire API."""
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import install
server = install.install_release(ROOT / '.dev/storage', 'server-0.3.4', install.SERVER, 'server.js')
subprocess.run([sys.executable, str(ROOT / 'scripts/protocol_smoke.py'), '--server', str(server)], check=True)
