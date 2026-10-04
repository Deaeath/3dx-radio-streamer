"""Tiny Shoutcast v1 / Icecast source-server stand-in for tests."""
import socket, threading

class MockServer:
    def __init__(self, port, kind="sc"):
        self.kind, self.data, self.log = kind, bytearray(), []
        self.srv = socket.socket(); self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", port + (1 if kind == "sc" else 0))); self.srv.listen(4)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            conn, _ = self.srv.accept()
            buf = b""
            while b"\r\n" not in buf: buf += conn.recv(1024)
            if self.kind == "sc":
                self.log.append(buf.split(b"\r\n")[0].decode()); conn.sendall(b"OK2\r\nicy-caps:11\r\n\r\n")
                rest = b""
                while b"\r\n\r\n" not in rest: rest += conn.recv(1024)
                rest = rest.split(b"\r\n\r\n", 1)[1]
            else:
                while b"\r\n\r\n" not in buf: buf += conn.recv(1024)
                head, rest = buf.split(b"\r\n\r\n", 1); self.log.append(head.decode().splitlines()[0])
                conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
            self.data += rest
            while True:
                d = conn.recv(65536)
                if not d: break
                self.data += d
