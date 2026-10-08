#!/usr/bin/env python3
"""Bounded text retrieval using configured HTTP proxies or a direct connection.

Transport success does not establish that a page is evidence or that a claim is true.
Uses Python's HTTP implementation and verified TLS; does not change proxy settings.
"""
from __future__ import annotations

import argparse
import codecs
from html.parser import HTMLParser
import http.client
import json
import math
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


class FetchError(Exception):
    def __init__(self, message, metadata=None):
        super().__init__(message)
        self.metadata = metadata or {}


def _safe_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        parsed.port
    except ValueError:
        raise FetchError("Malformed URL")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FetchError("URL must be an absolute HTTP or HTTPS address")
    if parsed.username is not None or parsed.password is not None:
        raise FetchError("Credentials in the requested URL are not supported")
    return url


def _save_complete_output(path, text):
    """Write a complete temporary file before replacing the requested destination."""
    descriptor, temporary = tempfile.mkstemp(dir=str(path.parent),
                 prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class BoundedRedirects(urllib.request.HTTPRedirectHandler):
    max_repeats = 2
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav"):
            self.ignored.append(tag)
        if not self.ignored and tag in ("br", "p", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.ignored and tag == self.ignored[-1]:
            self.ignored.pop()
        if not self.ignored and tag in ("p", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def html_to_text(content):
    parser = VisibleText()
    parser.feed(content)
    parser.close()
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n",
                  re.sub(r"[ \t]+", " ", "".join(parser.parts))).strip()


def fetch_text(url, timeout=30, max_size=2000000):
    _safe_url(url)
    if not math.isfinite(timeout) or timeout <= 0 or max_size <= 0:
        raise FetchError("timeout must be finite and positive; max-size must be positive")
    proxies = urllib.request.getproxies()
    if proxies.get("all"):
        proxies = dict(proxies)
        proxies.setdefault("http", proxies["all"])
        proxies.setdefault("https", proxies["all"])
    for scheme in ("http", "https"):
        if proxies.get(scheme):
            address = proxies[scheme]
            try:
                parsed = urllib.parse.urlsplit(address if "://" in address else "http://" + address)
                parsed.port
            except ValueError:
                raise FetchError("Malformed configured proxy address")
            if parsed.scheme != "http":
                raise FetchError("Only configured HTTP proxies are supported; use the environment's retrieval tools for other proxies")
            if not parsed.hostname:
                raise FetchError("Malformed configured proxy address")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies), BoundedRedirects(),
                 urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(url, headers={
        "User-Agent": "OrthogonalResearch/2.2 (Python text retrieval)",
        "Accept": "text/html,application/xhtml+xml,text/plain,application/json,application/xml;q=0.9",
        "Accept-Encoding": "identity"})
    metadata = {"url": url, "status": "error", "complete": False, "bytes_received": 0}
    try:
        with opener.open(request, timeout=timeout) as response:
            metadata.update({"final_url": _safe_url(response.geturl()),
                             "http_status": response.status,
                             "content_type": response.headers.get("Content-Type", "")})
            if not 200 <= response.status < 300:
                raise FetchError("HTTP response is not successful", metadata)
            ctype = response.headers.get_content_type()
            if not (ctype.startswith("text/") or ctype in (
                    "application/json", "application/xml", "application/xhtml+xml")):
                raise FetchError("Response is not a supported text type", metadata)
            encoding = response.headers.get("Content-Encoding", "identity").lower().strip()
            if encoding not in ("", "identity"):
                raise FetchError("Compressed responses are unsupported; identity encoding was requested", metadata)
            lengths = response.headers.get_all("Content-Length", [])
            transfer = response.headers.get_all("Transfer-Encoding", [])
            if len(lengths) > 1 or len(transfer) > 1 or (lengths and transfer):
                raise FetchError("Ambiguous HTTP response framing", metadata)
            if transfer and transfer[0].strip().lower() != "chunked":
                raise FetchError("Unsupported Transfer-Encoding", metadata)
            declared = lengths[0] if lengths else None
            expected = None
            if declared is not None:
                try:
                    expected = int(declared)
                except ValueError:
                    raise FetchError("Invalid Content-Length", metadata)
                if expected < 0:
                    raise FetchError("Invalid Content-Length", metadata)
                if expected > max_size:
                    raise FetchError("Response exceeds max-size", metadata)
            chunks = []
            deadline = time.monotonic() + timeout
            while True:
                if time.monotonic() > deadline:
                    raise FetchError("Response body reading deadline exceeded", metadata)
                chunk = response.read1(min(65536, max_size + 1 - metadata["bytes_received"]))
                metadata["bytes_received"] += len(chunk)
                if time.monotonic() > deadline:
                    raise FetchError("Response body reading deadline exceeded", metadata)
                if metadata["bytes_received"] > max_size:
                    raise FetchError("Response exceeds max-size", metadata)
                if not chunk:
                    break
                chunks.append(chunk)
            body = b"".join(chunks)
            if expected is not None and len(body) != expected:
                raise FetchError("Incomplete response: Content-Length does not match", metadata)
            charset = response.headers.get_content_charset()
            if not charset and ctype in ("text/html", "application/xhtml+xml", "application/xml"):
                match = re.search(br"(?:<meta\b[^>]*\bcharset\s*=\s*|<\?xml\b[^>]*\bencoding\s*=\s*)['\"]?\s*([\w.-]+)",
                                  body[:4096], re.I)
                if match:
                    charset = match.group(1).decode("ascii")
            charset = charset or "utf-8"
            codecs.lookup(charset)
            content = body.decode(charset)
            metadata.update({"status": "success", "complete": True, "charset": charset,
                             "size": len(body), "transport_only": True})
            return content, ctype, metadata
    except urllib.error.HTTPError as exc:
        metadata.update({"http_status": exc.code, "final_url": exc.geturl()})
        exc.close()
        raise FetchError("HTTP error {} (or redirect limit exceeded)".format(exc.code), metadata)
    except FetchError:
        raise
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError, LookupError) as exc:
        # Error class is useful, but exception text can include proxy credentials.
        metadata["error_type"] = type(exc).__name__
        if isinstance(exc, urllib.error.URLError):
            metadata["cause_type"] = type(exc.reason).__name__
        raise FetchError("Retrieval failed: {}".format(type(exc).__name__), metadata)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--format", choices=("text", "html"), default="text")
    parser.add_argument("--output", "-o", type=Path)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--max-size", type=int, default=2000000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        content, ctype, metadata = fetch_text(args.url, args.timeout, args.max_size)
        output = html_to_text(content) if args.format == "text" and ctype in (
                    "text/html", "application/xhtml+xml") else content
        if args.output:
            _save_complete_output(args.output, output)
        metadata["content_length"] = len(output)
        metadata["output_saved"] = args.output is not None
        if args.json:
            print(json.dumps(metadata, ensure_ascii=True))
        elif not args.output:
            sys.stdout.buffer.write(output.encode("utf-8"))
        return 0
    except (FetchError, OSError) as exc:
        metadata = dict(getattr(exc, "metadata", {}))
        metadata.update({"status": "error", "complete": False,
                         "error": str(exc) if isinstance(exc, FetchError) else "Cannot save output file"})
        if args.json:
            print(json.dumps(metadata, ensure_ascii=True))
        else:
            print(metadata["error"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
