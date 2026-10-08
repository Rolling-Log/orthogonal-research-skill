#!/usr/bin/env python3
"""
Proxy-aware web fetcher for blocked sites.
Reads proxy from Windows registry (HKCU Internet Settings) or HTTPS_PROXY env var.
Usage: python proxy_fetch.py <url> [--format text|html] [--output file]
"""

import sys, os, re, socket, ssl, json, argparse, urllib.parse, gzip, io

def get_proxy():
    for var in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
        val = os.environ.get(var)
        if val:
            return val
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')
        enabled = winreg.QueryValueEx(key, 'ProxyEnable')[0]
        if enabled:
            server = winreg.QueryValueEx(key, 'ProxyServer')[0]
            winreg.CloseKey(key)
            if '=' in server:
                for part in server.split(';'):
                    if '=' in part:
                        proto, addr = part.split('=', 1)
                        if proto.strip() in ('https', 'http'):
                            return f'http://{addr.strip()}'
            else:
                return f'http://{server}'
        winreg.CloseKey(key)
    except:
        pass
    return None


def fetch_via_proxy(url, proxy_addr, timeout=30, max_size=2000000):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    path = parsed.path + ('?' + parsed.query if parsed.query else '')
    
    proxy_parsed = urllib.parse.urlparse(proxy_addr)
    proxy_host = proxy_parsed.hostname
    proxy_port = proxy_parsed.port or 8080
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    
    try:
        sock.connect((proxy_host, proxy_port))
        
        if parsed.scheme == 'https':
            connect_req = f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\nProxy-Connection: Keep-Alive\r\n\r\n'
            sock.send(connect_req.encode())
            resp = b''
            while b'\r\n\r\n' not in resp:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp += chunk
            if b'200' not in resp:
                sys.stderr.write(f'CONNECT failed\n')
                return None
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            tunnel = ctx.wrap_socket(sock, server_hostname=host)
        else:
            tunnel = sock
        
        http_req = (
            f'GET {path if parsed.scheme == "https" else url} HTTP/1.1\r\n'
            f'Host: {host}\r\n'
            f'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n'
            f'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n'
            f'Accept-Language: en-US,en;q=0.9,zh-CN;q=0.8\r\n'
            f'Accept-Encoding: gzip, deflate\r\n'
            f'Connection: close\r\n'
            f'\r\n'
        )
        tunnel.send(http_req.encode())
        
        data = b''
        while True:
            try:
                chunk = tunnel.recv(16384)
                if not chunk:
                    break
                data += chunk
                if len(data) > max_size:
                    break
            except:
                break
        
        if parsed.scheme == 'https':
            tunnel.close()
        else:
            sock.close()
        
        # Parse HTTP response body
        body = data
        
        # Check if HTTP headers are present
        http_header_end = body.find(b'\r\n\r\n')
        if http_header_end >= 0 and body[:4] == b'HTTP':
            headers_raw = body[:http_header_end].decode('utf-8', errors='replace')
            body = body[http_header_end + 4:]
            
            if 'Transfer-Encoding: chunked' in headers_raw:
                decoded = b''
                pos = 0
                while pos < len(body):
                    line_end = body.find(b'\r\n', pos)
                    if line_end < 0:
                        break
                    try:
                        chunk_size = int(body[pos:line_end], 16)
                    except:
                        break
                    if chunk_size == 0:
                        break
                    pos = line_end + 2
                    decoded += body[pos:pos + chunk_size]
                    pos += chunk_size + 2
                body = decoded
        
        # Handle gzip compression (may be direct or after HTTP headers)
        if body[:2] == b'\x1f\x8b':
            try:
                body = gzip.decompress(body)
            except:
                pass
        
        return body
        
    except Exception as e:
        sys.stderr.write(f'Fetch error: {type(e).__name__}: {e}\n')
        return None


def html_to_text(html_bytes):
    try:
        html = html_bytes.decode('utf-8')
    except:
        try:
            html = html_bytes.decode('latin-1')
        except:
            return html_bytes.decode('utf-8', errors='replace')
    
    # Check if this is actually HTML
    if '<html' not in html.lower() and '<!doctype' not in html.lower():
        return html[:5000]
    
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL|re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL|re.IGNORECASE)
    html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL|re.IGNORECASE)
    
    for pattern in [
        r'<article[^>]*>(.*?)</article>',
        r'<main[^>]*>(.*?)</main>',
    ]:
        match = re.search(pattern, html, re.DOTALL|re.IGNORECASE)
        if match and len(match.group(1)) > 500:
            html = match.group(1)
            break
    
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'</?p[^>]*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?h[1-6][^>]*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?li[^>]*>', '\n- ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#x27;', "'").replace('&nbsp;', ' ')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text.strip()


def main():
    parser = argparse.ArgumentParser(description='Proxy-aware web fetcher')
    parser.add_argument('url', help='URL to fetch')
    parser.add_argument('--format', choices=['text', 'html'], default='text')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--max-size', type=int, default=2000000)
    parser.add_argument('--json', action='store_true', help='Output JSON with metadata')
    args = parser.parse_args()
    
    proxy = get_proxy()
    if not proxy:
        result = {'error': 'No proxy configured'}
        if args.json:
            print(json.dumps(result))
        else:
            sys.stderr.write('ERROR: No proxy\n')
        sys.exit(1)
    
    data = fetch_via_proxy(args.url, proxy, timeout=args.timeout, max_size=args.max_size)
    if not data:
        result = {'error': 'Failed to fetch URL', 'url': args.url}
        if args.json:
            print(json.dumps(result))
        else:
            sys.stderr.write('ERROR: Failed to fetch\n')
        sys.exit(1)
    
    if args.format == 'html':
        output = data.decode('utf-8', errors='replace')
    else:
        output = html_to_text(data)
    
    if args.json:
        result = {
            'url': args.url,
            'size': len(data),
            'content_length': len(output),
            'status': 'success'
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            sys.stderr.write(f'Saved {len(data)} bytes to {args.output}\n')
        else:
            # Write binary to stdout to avoid encoding issues
            sys.stdout.buffer.write(output.encode('utf-8', errors='replace'))
