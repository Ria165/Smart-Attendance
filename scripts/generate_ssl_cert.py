import os
import socket
import ipaddress
from datetime import datetime, timezone, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def get_local_ip():
    """Detect the local LAN IPv4 address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def generate_self_signed_cert(cert_path="cert.pem", key_path="key.pem", additional_ips=None):
    """
    Generate an X.509 self-signed certificate and private key with SANs
    for localhost, 127.0.0.1, and the local LAN IP address (e.g., 10.207.6.30).
    """
    local_ip = get_local_ip()
    ip_list = {"127.0.0.1", local_ip}
    if additional_ips:
        for ip in additional_ips:
            if ip:
                ip_list.add(ip.strip())

    san_entries = [x509.DNSName("localhost")]
    for ip_str in ip_list:
        try:
            san_entries.append(x509.IPAddress(ipaddress.IPv4Address(ip_str)))
        except ValueError:
            san_entries.append(x509.DNSName(ip_str))

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Smart Attendance System"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Biometric Security"),
        x509.NameAttribute(NameOID.COMMON_NAME, local_ip),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"[SSL] Generated self-signed certificate: {cert_path}")
    print(f"[SSL] Generated private key: {key_path}")
    print(f"[SSL] Configured Subject Alternative Names: {[str(s.value) for s in san_entries]}")
    return cert_path, key_path

if __name__ == "__main__":
    generate_self_signed_cert()
