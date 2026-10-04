"""Shoutcast v1/v2 and Icecast 2 source protocol, metadata updates and listener URLs."""

import base64
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from . import VERSION

HTTP_UA = f"Mozilla/5.0 (compatible; 3DXRadioStreamer/{VERSION})"


class StreamError(Exception):
    pass


def _clean(value):
    return re.sub(r"[\r\n]+", " ", str(value)).strip()


def mount_path(cfg):
    mount = str(cfg.get("mount", "")).strip() or "/stream"
    return mount if mount.startswith("/") else "/" + mount


def listener_url(cfg):
    """The URL listeners play."""
    host = str(cfg.get("host", "")).strip() or "host"
    port = cfg.get("port", "")
    if cfg.get("server_type") == "Icecast 2":
        return f"http://{host}:{port}{mount_path(cfg)}"
    if cfg.get("server_type") == "Shoutcast v2":
        return f"http://{host}:{port}/stream/{cfg.get('sid', 1)}/"
    return f"http://{host}:{port}/"


def source_port(cfg):
    port = int(cfg["port"])
    return port + 1 if cfg["server_type"].startswith("Shoutcast") else port


def describe_socket_error(exc, host, port):
    if isinstance(exc, ConnectionRefusedError):
        return (f"{host}:{port} refused the connection - the stream server is not running (turn it on "
                f"in your host's control panel) or the host/port is wrong.")
    if isinstance(exc, socket.gaierror):
        return f"Cannot find server '{host}' - check the host name."
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return f"{host}:{port} did not respond - wrong host, a firewall, or the server is down."
    return f"{host}:{port}: {exc}"


def _read_reply(sock, limit=4096):
    data = b""
    while len(data) < limit:
        try:
            chunk = sock.recv(1024)
        except (socket.timeout, TimeoutError):
            if data:
                break
            raise
        if not chunk:
            break
        data += chunk
        if b"\r\n\r\n" in data or b"\n\n" in data:
            break
    return data.decode("utf-8", errors="replace")


def open_source_connection(cfg, timeout=10):
    """Connect and log in as a source. Returns a socket ready for MP3 data."""
    host = str(cfg["host"]).strip()
    stype = cfg["server_type"]
    if not host:
        raise StreamError("No server host set.")
    port = source_port(cfg)
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        raise StreamError(describe_socket_error(e, host, port)) from e

    try:
        if stype.startswith("Shoutcast"):
            pw = cfg["password"]
            if stype == "Shoutcast v2":
                pw = f"{pw}:#{int(cfg['sid'])}"
            sock.sendall(pw.encode("utf-8") + b"\r\n")
            reply = _read_reply(sock)
            first = reply.strip().splitlines()[0] if reply.strip() else ""
            if not first.upper().startswith("OK"):
                hint = " (wrong password?)" if "password" in first.lower() or not first else ""
                raise StreamError(f"Server rejected the login: '{first or 'connection closed'}'{hint}")
            headers = {
                "content-type": "audio/mpeg",
                "icy-name": cfg["name"],
                "icy-genre": cfg["genre"],
                "icy-url": cfg["url"],
                "icy-pub": "1" if cfg["public"] else "0",
                "icy-br": str(int(cfg["bitrate"])),
            }
            sock.sendall("".join(f"{k}:{_clean(v)}\r\n" for k, v in headers.items())
                         .encode("utf-8") + b"\r\n")
        else:
            auth = base64.b64encode(f"{cfg['username'] or 'source'}:{cfg['password']}"
                                    .encode("utf-8")).decode("ascii")
            headers = {
                "Host": f"{host}:{port}",
                "Authorization": f"Basic {auth}",
                "User-Agent": HTTP_UA,
                "Content-Type": "audio/mpeg",
                "Ice-Name": cfg["name"],
                "Ice-Description": cfg["description"],
                "Ice-Genre": cfg["genre"],
                "Ice-Url": cfg["url"],
                "Ice-Public": "1" if cfg["public"] else "0",
                "Ice-Audio-Info": (f"ice-bitrate={int(cfg['bitrate'])};ice-channels={int(cfg['channels'])};"
                                   f"ice-samplerate={int(cfg['samplerate'])}"),
                "Expect": "100-continue",
            }
            req = f"PUT {urllib.parse.quote(mount_path(cfg))} HTTP/1.1\r\n" + \
                  "".join(f"{k}: {_clean(v)}\r\n" for k, v in headers.items()) + "\r\n"
            sock.sendall(req.encode("utf-8"))
            reply = _read_reply(sock)
            m = re.match(r"HTTP/\d\.\d\s+(\d+)", reply)
            code = int(m.group(1)) if m else 0
            if code not in (100, 200):
                reason = {401: "wrong username/password",
                          403: "mount point in use or not allowed",
                          404: "mount point not found"}.get(code, "")
                status = reply.strip().splitlines()[0] if reply.strip() else "connection closed"
                raise StreamError(f"Server rejected the login: '{status}'" + (f" ({reason})" if reason else ""))
    except StreamError:
        sock.close()
        raise
    except OSError as e:
        sock.close()
        raise StreamError(describe_socket_error(e, host, port)) from e
    return sock


def update_metadata(cfg, title):
    """Push 'now playing' text to the server. Returns a status message."""
    host, port = str(cfg["host"]).strip(), int(cfg["port"])
    stype = cfg["server_type"]
    headers = {"User-Agent": HTTP_UA}
    if stype.startswith("Shoutcast"):
        params = {"pass": cfg["password"], "mode": "updinfo", "song": title}
        if stype == "Shoutcast v2":
            params["sid"] = str(int(cfg["sid"]))
        url = f"http://{host}:{port}/admin.cgi?" + urllib.parse.urlencode(params)
    else:
        url = f"http://{host}:{port}/admin/metadata?" + urllib.parse.urlencode(
            {"mount": mount_path(cfg), "mode": "updinfo", "song": title})
        auth = f"{cfg['username'] or 'source'}:{cfg['password']}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(auth).decode("ascii")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=8):
            pass
        return f"Stream title set: {title}"
    except urllib.error.HTTPError as e:
        return f"Stream title update failed: HTTP {e.code} {e.reason}"
    except (OSError, ValueError) as e:
        return f"Stream title update failed: {e}"
