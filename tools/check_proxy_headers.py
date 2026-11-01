"""사내 로그인 프록시 점검 (deploy/oidc-proxy, design §12.3 운영 인증의 자리).

  python tools/check_proxy_headers.py --conf deploy/oidc-proxy/nginx.conf            # the configuration, offline
  python tools/check_proxy_headers.py --url https://croscan.example.internal --app http://host:8765   # the live setup

Offline: every route but the health check asks the sign-in (auth_request); the two croScan headers are set by nginx
from the sign-in's answer (so a browser's own header of that name is replaced); the role comes only from the IdP
groups; the compose file does not publish the app's port and runs it with CROSCAN_AUTH=proxy.
Live: without signing in nothing of croScan opens; a forged role header does not open the manager's side; the app's
own port is not reachable from where this runs.
"""
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def offline(conf):
    text = Path(conf).read_text(encoding="utf-8")
    body = re.sub(r"#[^\n]*", "", text)
    loc = re.search(r"location\s+/\s*\{(.*?)\n\s*\}", body, re.S)
    root = loc.group(1) if loc else ""
    check("본 경로는 로그인 확인(auth_request)을 거침", "auth_request /oauth2/auth" in root)
    check("사용자 헤더는 프록시가 로그인 답에서 넣음", re.search(r"proxy_set_header\s+X-Croscan-User\s+\$croscan_user", root) is not None
          and "auth_request_set $croscan_user" in root)
    check("역할 헤더는 프록시가 IdP 그룹에서 넣음(브라우저 값 덮어씀)", re.search(r"proxy_set_header\s+X-Croscan-Role\s+\$croscan_role", root) is not None
          and re.search(r"map\s+\$croscan_groups\s+\$croscan_role", body) is not None)
    check("그룹에 없으면 역할 없음(기본값 빈칸)", re.search(r'default\s+""', body) is not None)
    opens = re.findall(r"location\s+(=?\s*\S+)\s*\{(.*?)\}", body, re.S)
    bare = [p for p, b in opens if "auth_request" not in b and "internal" not in b and p.strip() not in ("/oauth2/", "= /api/health")]
    check("로그인 없이 열리는 경로는 /oauth2/·/api/health뿐", not bare)
    compose = Path(conf).with_name("docker-compose.yml")
    if compose.exists():
        c = re.sub(r"#[^\n]*", "", compose.read_text(encoding="utf-8"))          # comments say nothing
        app = re.search(r"\n  croscan:\n(.*?)(?=\n  \S)", c, re.S)
        block = app.group(1) if app else ""
        check("앱은 CROSCAN_AUTH=proxy로 실행", "CROSCAN_AUTH: proxy" in block)
        check("앱 포트는 바깥에 열지 않음(ports 없음)", "ports:" not in block)


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, url
    except (urllib.error.URLError, OSError) as e:
        return None, str(e)


def live(url, app):
    s, where = _get(url + "/api/knowledge/map")
    check("로그인 없이 근거 지도가 열리지 않음", s != 200 or "/oauth2/" in where)
    s, where = _get(url + "/api/knowledge/map", {"X-Croscan-Role": "manager", "X-Croscan-User": "someone"})
    check("역할 헤더를 위조해도 열리지 않음", s != 200 or "/oauth2/" in where)
    s, _ = _get(url + "/api/health")
    check("상태 확인은 열림", s == 200)
    if app:
        s, _ = _get(app + "/api/health")
        check("앱 포트는 이 자리에서 닿지 않음", s is None)


def main():
    a = sys.argv
    if "--conf" in a:
        offline(a[a.index("--conf") + 1])
    if "--url" in a:
        live(a[a.index("--url") + 1].rstrip("/"), a[a.index("--app") + 1].rstrip("/") if "--app" in a else None)
    if not OK:
        print(__doc__)
        sys.exit(1)
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
