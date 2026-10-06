"""Exercise the bootstrap server, or the automatic updater with --latest."""
import argparse
import os
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import core, install


class GitHubAPIAuth(urllib.request.BaseHandler):
    def https_request(self, request):
        token = os.environ.get('GH_TOKEN')
        if token and urlsplit(request.full_url).netloc == 'api.github.com':
            request.add_unredirected_header('Authorization', 'Bearer ' + token)
        return request


# Hosted runners share unauthenticated API limits. Keep CI credentials confined
# to GitHub API requests; release-asset downloads do not receive this header.
urllib.request.install_opener(urllib.request.build_opener(GitHubAPIAuth()))
parser = argparse.ArgumentParser()
parser.add_argument('--latest', action='store_true')
args = parser.parse_args()
storage = ROOT / '.dev/storage'
if args.latest:
    # Do not count an offline fallback as a latest-release check.
    stable_version, _ = install.latest_server()
    server = install.managed_server(storage)
    version = max([stable_version, core.SERVER_VERSION] + list(install.cached_servers(storage)), key=install.version_tuple)
else:
    version = core.SERVER_VERSION
    server = install.install_release(storage, 'server-' + version, install.SERVER, 'server.js')
subprocess.run([sys.executable, str(ROOT / 'scripts/protocol_smoke.py'), '--server', str(server),
                '--expected-version', version], check=True)
