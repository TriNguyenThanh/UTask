"""Isolated STARTTLS mailbox for the real-domain Notification smoke.

Only test containers share this mailbox. Messages stay in memory and are never logged.
"""

import json
import socketserver
import ssl
import threading
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main():
    messages = []
    lock = threading.Lock()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain("/fixture/smtp.pem", "/fixture/smtp-key.pem")

    class SMTP(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 smtp test mailbox\r\n")
            self.wfile.flush()
            secured = False
            while line := self.rfile.readline():
                command = line.upper().split(b" ", 1)[0].strip()
                if command == b"EHLO":
                    self.wfile.write(b"250-smtp\r\n250-STARTTLS\r\n250 AUTH PLAIN\r\n")
                elif command == b"STARTTLS":
                    self.wfile.write(b"220 Begin TLS\r\n")
                    self.wfile.flush()
                    self.connection = tls.wrap_socket(self.connection, server_side=True)
                    self.rfile = self.connection.makefile("rb")
                    self.wfile = self.connection.makefile("wb")
                    secured = True
                elif command == b"AUTH" and secured:
                    self.wfile.write(b"235 Authenticated\r\n")
                elif command in {b"MAIL", b"RCPT", b"RSET", b"NOOP"} and secured:
                    self.wfile.write(b"250 OK\r\n")
                elif command == b"DATA" and secured:
                    self.wfile.write(b"354 End with dot\r\n")
                    self.wfile.flush()
                    parts = []
                    while (part := self.rfile.readline()) not in {b".\r\n", b""}:
                        parts.append(part[1:] if part.startswith(b"..") else part)
                    msg = BytesParser(policy=policy.default).parsebytes(b"".join(parts))
                    with lock:
                        messages.append(
                            {
                                "to": str(msg["To"]),
                                "subject": str(msg["Subject"]),
                                "body": msg.get_body(preferencelist=("plain",)).get_content(),
                                "id": str(msg["Message-ID"]),
                            }
                        )
                    self.wfile.write(b"250 Accepted\r\n")
                elif command == b"QUIT":
                    self.wfile.write(b"221 Bye\r\n")
                    self.wfile.flush()
                    return
                else:
                    self.wfile.write(b"530 STARTTLS required\r\n")
                self.wfile.flush()

    class Mailbox(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            with lock:
                body = json.dumps(messages).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    smtp = socketserver.ThreadingTCPServer(("0.0.0.0", 8025), SMTP)
    threading.Thread(target=smtp.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Mailbox).serve_forever()


if __name__ == "__main__":
    main()
