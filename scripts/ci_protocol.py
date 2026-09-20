"""Exercise the bootstrap server, or the automatic updater with --latest."""
import argparse
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import core, install
parser = argparse.ArgumentParser()
parser.add_argument('--latest', action='store_true')
args = parser.parse_args()
storage = ROOT / '.dev/storage'
if args.latest:
    # Do not count an offline fallback as a latest-release check.
    version, _ = install.latest_server()
    server = install.managed_server(storage)
else:
    version = core.SERVER_VERSION
    server = install.install_release(storage, 'server-' + version, install.SERVER, 'server.js')
subprocess.run([sys.executable, str(ROOT / 'scripts/protocol_smoke.py'), '--server', str(server),
                '--expected-version', version], check=True)
