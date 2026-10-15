"""Existing P-256 node identity, X.509 TLS, and platform-protected storage."""
from __future__ import annotations

import hashlib
import os
import ssl
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

from ..node_protocol import NodeIdentity, TrustedNodeStore
from ..platform_services import SecureVault


def certificate_id(certificate):
    cert = x509.load_pem_x509_certificate(certificate.encode()) if isinstance(certificate, str) else x509.load_der_x509_certificate(certificate)
    public = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return "node-" + hashlib.sha256(public).hexdigest()[:40]


def certificate_pin(certificate):
    cert = x509.load_pem_x509_certificate(certificate.encode()) if isinstance(certificate, str) else x509.load_der_x509_certificate(certificate)
    return cert.fingerprint(hashes.SHA256()).hex()


class NodeCredentials:
    def __init__(self, directory, identity=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            self.vault = SecureVault(self.directory / "vault")
            pem = self.vault.get("mesh.identity", "")
            self.identity = NodeIdentity.from_pem(pem) if pem else identity or NodeIdentity()
            if not pem:
                self.vault.set("mesh.identity", self.identity.private_pem())
        else:
            # Linux: private local runtime directory, never project configuration.
            self.directory.chmod(0o700)
            self.vault = None
            path = self.directory / "identity.pem"
            if path.is_symlink():
                raise ValueError("Identity path cannot be a symlink.")
            self.identity = NodeIdentity.from_pem(path.read_bytes()) if path.exists() else identity or NodeIdentity()
            if not path.exists():
                with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as stream:
                    stream.write(self.identity.private_pem())
            path.chmod(0o600)
        cert_path = self.directory / "certificate.pem"
        if cert_path.exists():
            self.certificate = cert_path.read_text()
        else:
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MORICE Device Mesh")])
            now = datetime.now(timezone.utc)
            certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(self.identity.public_key).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=1825))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
                .sign(self.identity._private_key, hashes.SHA256()))
            self.certificate = certificate.public_bytes(serialization.Encoding.PEM).decode()
            cert_path.write_text(self.certificate)
        public = x509.load_pem_x509_certificate(self.certificate.encode()).public_key()
        if public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != self.identity.public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
            raise ValueError("Certificate does not match node identity.")
        self.node_id = certificate_id(self.certificate)
        self.pin = certificate_pin(self.certificate)

    @contextmanager
    def _key_file(self):
        # CPython SSL requires a filename. It receives only an encrypted PKCS8 file.
        password = os.urandom(32).hex()
        encrypted = self.identity._private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(password.encode()))
        handle, name = tempfile.mkstemp(prefix="tls-key-", dir=self.directory)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(encrypted)
            yield name, password
        finally:
            Path(name).unlink(missing_ok=True)

    def context(self, *, server=False, certificates=(), pairing=False):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        if not server:
            ctx.check_hostname = False  # Identity is pinned cryptographically, independent of IP.
        ctx.verify_mode = ssl.CERT_NONE if pairing else ssl.CERT_REQUIRED
        if not pairing and certificates:
            ctx.load_verify_locations(cadata="\n".join(certificates))
            ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        with self._key_file() as (name, password):
            ctx.load_cert_chain(str(self.directory / "certificate.pem"), name, password)
        return ctx


class ProtectedTrustStore(TrustedNodeStore):
    """Reuse the existing trust records; protect their stored representation."""
    def __init__(self, directory, credentials):
        self.credentials = credentials
        super().__init__(Path(directory) / "trusted-nodes.json")

    def _save(self):
        import json
        value = json.dumps({"nodes": [n.to_dict() for n in self._nodes.values()]})
        if self.credentials.vault:
            self.credentials.vault.set("mesh.trusted-nodes", value)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            temporary = self.path.with_suffix(".tmp")
            with os.fdopen(os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), "w") as stream:
                stream.write(value)
            os.replace(temporary, self.path)

    def _load(self):
        import json
        from ..node_protocol import TrustedNode
        raw = self.credentials.vault.get("mesh.trusted-nodes", "{}") if self.credentials.vault else self.path.read_text() if self.path.exists() else "{}"
        for item in json.loads(raw).get("nodes", ())[:64]:
            node = TrustedNode.from_dict(item)
            if node.descriptor.device_id != certificate_id(node.identity_public_key):
                raise ValueError("Stored node identity mismatch.")
            self._nodes[node.descriptor.device_id] = node
