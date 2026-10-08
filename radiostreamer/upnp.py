"""Ask the home router to forward a port to this PC (UPnP IGD), and find the public address.

Pure Python: SSDP discovery, the router's device description, then SOAP AddPortMapping /
GetExternalIPAddress / DeletePortMapping on its WANIPConnection or WANPPPConnection service.
"""

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2", "urn:schemas-upnp-org:service:WANIPConnection:1",
            "urn:schemas-upnp-org:service:WANPPPConnection:1")


class UPnPError(Exception):
    pass


def local_ip():
    """The LAN address this PC uses to reach the internet."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def is_private(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return a.is_private or a in ipaddress.ip_network("100.64.0.0/10")   # 100.64/10 = carrier-grade NAT


def public_ip(timeout=8):
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8"}), timeout=timeout) as r:
                ip = r.read().decode().strip()
                ipaddress.ip_address(ip)
                return ip
        except (OSError, ValueError):
            continue
    return None


def _discover(timeout=3):
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
           "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n").encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.settimeout(timeout)
    try:
        s.bind((local_ip(), 0))
        s.sendto(msg, ("239.255.255.250", 1900))
        while True:
            data, _ = s.recvfrom(8192)
            m = re.search(rb"(?im)^location:\s*(\S+)", data)
            if m:
                return m.group(1).decode()
    except OSError:
        return None
    finally:
        s.close()


def _control(location):
    with urllib.request.urlopen(location, timeout=6) as r:
        root = ET.fromstring(r.read())
    ns = {"d": "urn:schemas-upnp-org:device-1-0"}
    for svc in root.iter("{urn:schemas-upnp-org:device-1-0}service"):
        st = svc.findtext("d:serviceType", default="", namespaces=ns)
        if st in SERVICES:
            ctl = svc.findtext("d:controlURL", default="", namespaces=ns)
            return urllib.parse.urljoin(location, ctl), st
    raise UPnPError("the router doesn't offer port forwarding over UPnP")


def _soap(url, service, action, args):
    body = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
    envelope = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>').encode()
    req = urllib.request.Request(url, data=envelope, headers={"Content-Type": 'text/xml; charset="utf-8"',
                                                              "SOAPAction": f'"{service}#{action}"'})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = re.search(r"<errorDescription>(.*?)</errorDescription>", e.read().decode("utf-8", "replace"))
        raise UPnPError(f"the router refused ({detail.group(1) if detail else e.code})") from e
    except OSError as e:
        raise UPnPError(f"couldn't talk to the router ({e})") from e


class PortMapping:
    """Opens a TCP port on the router while broadcasting; close() removes it again."""

    def __init__(self, port, description="3DX Radio Streamer"):
        self.port, self.description = int(port), description
        self.url = self.service = None
        self.external_ip = None

    def open(self):
        loc = _discover()
        if not loc:
            raise UPnPError("no router answered (UPnP is off on the router, or you're on a VPN)")
        self.url, self.service = _control(loc)
        _soap(self.url, self.service, "AddPortMapping", {
            "NewRemoteHost": "", "NewExternalPort": self.port, "NewProtocol": "TCP", "NewInternalPort": self.port,
            "NewInternalClient": local_ip(), "NewEnabled": 1, "NewPortMappingDescription": self.description,
            "NewLeaseDuration": 0})
        reply = _soap(self.url, self.service, "GetExternalIPAddress", {})
        m = re.search(r"<NewExternalIPAddress>(.*?)</NewExternalIPAddress>", reply)
        self.external_ip = m.group(1) if m else None
        return self.external_ip

    def close(self):
        if not self.url:
            return
        try:
            _soap(self.url, self.service, "DeletePortMapping",
                  {"NewRemoteHost": "", "NewExternalPort": self.port, "NewProtocol": "TCP"})
        except UPnPError:
            pass
        self.url = None
