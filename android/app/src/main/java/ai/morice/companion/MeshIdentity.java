package ai.morice.companion;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import java.math.BigInteger;
import java.security.*;
import java.security.cert.*;
import java.security.spec.ECGenParameterSpec;
import java.util.Date;
import javax.net.ssl.*;
import javax.security.auth.x500.X500Principal;

/** TLS keys stay non-exportable in Android Keystore. Trust is explicit and certificate-pinned. */
final class MeshIdentity {
    static final String ALIAS = "morice-mesh-tls-v2";
    final SecureNodeStore store;
    final KeyStore keys;
    final X509Certificate certificate;
    final String nodeId;

    MeshIdentity(SecureNodeStore store) throws Exception {
        this.store = store;
        keys = KeyStore.getInstance("AndroidKeyStore"); keys.load(null);
        if (!keys.containsAlias(ALIAS)) {
            KeyPairGenerator generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
            generator.initialize(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setCertificateSubject(new X500Principal("CN=MORICE Android Node"))
                .setCertificateSerialNumber(new BigInteger(128, new SecureRandom()))
                .setCertificateNotBefore(new Date(System.currentTimeMillis() - 300000))
                .setCertificateNotAfter(new Date(System.currentTimeMillis() + 157680000000L)).build());
            generator.generateKeyPair();
        }
        certificate = (X509Certificate) keys.getCertificate(ALIAS);
        nodeId = id(certificate);
    }

    static String hex(byte[] value) {
        StringBuilder text = new StringBuilder();
        for (byte b : value) text.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return text.toString();
    }
    static String id(X509Certificate certificate) throws Exception {
        return "node-" + hex(MessageDigest.getInstance("SHA-256").digest(certificate.getPublicKey().getEncoded())).substring(0, 40);
    }
    static String pin(X509Certificate certificate) throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded()));
    }
    static X509Certificate parse(String pem) throws Exception {
        if (pem.length() > 8192) throw new SecurityException("Certificate too large.");
        return (X509Certificate) CertificateFactory.getInstance("X.509").generateCertificate(
            new java.io.ByteArrayInputStream(pem.getBytes(java.nio.charset.StandardCharsets.US_ASCII)));
    }
    String pem() throws Exception {
        return "-----BEGIN CERTIFICATE-----\n" + Base64.encodeToString(certificate.getEncoded(), Base64.NO_WRAP) + "\n-----END CERTIFICATE-----\n";
    }
    synchronized JSONObject peers() throws Exception {
        String value = store.secret("mesh.peers");
        return value.isEmpty() ? new JSONObject() : new JSONObject(value);
    }
    synchronized JSONObject peer(String id) throws Exception { return peers().optJSONObject(id); }
    synchronized void savePeer(String id, JSONObject peer) throws Exception {
        JSONObject peers = peers();
        if (peers.length() >= 64 && !peers.has(id)) throw new SecurityException("Peer limit reached.");
        peers.put(id, peer); store.putSecret("mesh.peers", peers.toString());
    }
    synchronized void revoke(String id) throws Exception {
        JSONObject peers = peers(); peers.remove(id); store.putSecret("mesh.peers", peers.toString());
    }

    SSLContext context(String expectedPin, boolean server) throws Exception {
        X509ExtendedKeyManager keyManager = new X509ExtendedKeyManager() {
            public String[] getClientAliases(String type, Principal[] issuers) { return new String[]{ALIAS}; }
            public String chooseClientAlias(String[] types, Principal[] issuers, java.net.Socket socket) { return ALIAS; }
            public String[] getServerAliases(String type, Principal[] issuers) { return new String[]{ALIAS}; }
            public String chooseServerAlias(String type, Principal[] issuers, java.net.Socket socket) { return ALIAS; }
            public String chooseEngineClientAlias(String[] types, Principal[] issuers, SSLEngine engine) { return ALIAS; }
            public String chooseEngineServerAlias(String type, Principal[] issuers, SSLEngine engine) { return ALIAS; }
            public X509Certificate[] getCertificateChain(String alias) { return new X509Certificate[]{certificate}; }
            public PrivateKey getPrivateKey(String alias) {
                try { return (PrivateKey) keys.getKey(ALIAS, null); } catch (Exception e) { throw new IllegalStateException(e); }
            }
        };
        X509TrustManager trust = new X509TrustManager() {
            private void verify(X509Certificate[] chain) throws CertificateException {
                try {
                    if (chain == null || chain.length != 1) throw new SecurityException("Single pinned device certificate required.");
                    chain[0].checkValidity();
                    if (expectedPin != null) {
                        if (!pin(chain[0]).equals(expectedPin)) throw new SecurityException("Certificate fingerprint mismatch.");
                    } else {
                        JSONObject peer = peer(id(chain[0]));
                        if (peer == null || !pin(chain[0]).equals(pin(parse(peer.getString("certificate")))))
                            throw new SecurityException("Unpaired or revoked node.");
                    }
                } catch (Exception e) { throw new CertificateException("Device authentication failed.", e); }
            }
            public void checkClientTrusted(X509Certificate[] chain, String type) throws CertificateException { verify(chain); }
            public void checkServerTrusted(X509Certificate[] chain, String type) throws CertificateException { verify(chain); }
            public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
        };
        SSLContext context = SSLContext.getInstance("TLSv1.3");
        context.init(new KeyManager[]{keyManager}, new TrustManager[]{trust}, new SecureRandom());
        return context;
    }
}
