"""自签名证书：浏览器录音 API 要求安全上下文，所以必须提供 HTTPS。

证书要能被 iPhone 接受，必须满足 Apple 的硬性要求（support.apple.com/HT210176）：
  · 有效期 ≤ 825 天        —— 超了 iOS 直接判为不受信任，装了也没用
  · 带 ExtendedKeyUsage: serverAuth
  · 用 SAN 而不是 CN 来标识主机，且签名算法 ≥ SHA-256
同时它自己要是 CA（BasicConstraints ca=True），才能作为根证书装进手机。

IP 变了（换路由器/换网段）会自动重新签发，不用手动删文件。
"""
from __future__ import annotations

import datetime
import ipaddress
import socket

from .config import CERT_DIR

CERT_FILE = CERT_DIR / "server.crt"
KEY_FILE = CERT_DIR / "server.key"
VALID_DAYS = 800  # 必须 ≤ 825，否则 iOS 不认


def local_ips() -> list[str]:
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            addr = info[4][0]
            if ":" not in addr:
                ips.add(addr)
    except OSError:
        pass
    # 取默认出口网卡地址（不会真的发包）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def _hostnames() -> list[str]:
    names = ["localhost"]
    try:
        host = socket.gethostname()
        names.append(host)
        if not host.endswith(".local"):
            names.append(f"{host}.local")
    except OSError:
        pass
    return list(dict.fromkeys(names))


def _cert_is_usable() -> bool:
    """现有证书是否还能用：没过期、覆盖当前 IP、符合 iOS 要求。"""
    if not (CERT_FILE.exists() and KEY_FILE.exists()):
        return False
    try:
        from cryptography import x509
        from cryptography.x509.oid import ExtendedKeyUsageOID

        cert = x509.load_pem_x509_certificate(CERT_FILE.read_bytes())
    except Exception:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        not_before, not_after = cert.not_valid_before_utc, cert.not_valid_after_utc
    except AttributeError:  # cryptography < 42
        not_before = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
        not_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
    if not (not_before <= now <= not_after):
        return False
    if (not_after - not_before).days > 825:
        return False  # 老版本签的 10 年证书，iOS 不认，重签

    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        if ExtendedKeyUsageOID.SERVER_AUTH not in eku:
            return False
    except x509.ExtensionNotFound:
        return False

    # 当前网段的 IP 必须都在 SAN 里，否则换了网络会报证书错误
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        covered = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    except x509.ExtensionNotFound:
        return False
    return set(local_ips()).issubset(covered)


def ensure_cert(force: bool = False) -> tuple[str, str] | None:
    """可用就复用，否则重新签发。失败返回 None（降级为纯 HTTP）。"""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if not force and _cert_is_usable():
        return str(CERT_FILE), str(KEY_FILE)

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError:
        return None

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "书画室看板"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Shuhuashi Local LAN"),
    ])

    alt_names: list = [x509.DNSName(n) for n in _hostnames()]
    for ip in local_ips():
        try:
            alt_names.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
            .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, key_encipherment=True, key_cert_sign=True,
                content_commitment=False, data_encipherment=False, key_agreement=False,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                           critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                           critical=False)
            .sign(key, hashes.SHA256()))

    KEY_FILE.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    try:
        KEY_FILE.chmod(0o600)
    except OSError:
        pass
    return str(CERT_FILE), str(KEY_FILE)
