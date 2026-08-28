package ai.morice.companion;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyStore;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

final class SecureNodeStore {
    private static final String PREFS = "morice_secure_nodes_v1";
    private static final String MASTER_ALIAS = "morice-node-store-master-v1";
    private static final String IDENTITY = "identity";
    private static final String PEERS = "peers";

    static final class Peer {
        final MoriceProtocol.Descriptor descriptor;
        final String host;
        final int port;
        final byte[] sessionKey;
        final List<String> localPermissions;
        final List<String> remoteGrants;
        final long pairedAt;

        Peer(MoriceProtocol.Descriptor descriptor, String host, int port, byte[] sessionKey,
             List<String> localPermissions, List<String> remoteGrants, long pairedAt) {
            this.descriptor = descriptor;
            this.host = host;
            this.port = port;
            this.sessionKey = sessionKey.clone();
            this.localPermissions = Collections.unmodifiableList(new ArrayList<>(localPermissions));
            this.remoteGrants = Collections.unmodifiableList(new ArrayList<>(remoteGrants));
            this.pairedAt = pairedAt;
        }

        JSONObject toJson() throws JSONException {
            JSONObject value = new JSONObject();
            value.put("descriptor", descriptor.toJson());
            value.put("host", host);
            value.put("port", port);
            value.put("sessionKey", MoriceProtocol.b64(sessionKey));
            value.put("localPermissions", new JSONArray(localPermissions));
            value.put("remoteGrants", new JSONArray(remoteGrants));
            value.put("pairedAt", pairedAt);
            return value;
        }

        static Peer fromJson(JSONObject value) throws JSONException {
            return new Peer(
                    MoriceProtocol.Descriptor.fromJson(value.getJSONObject("descriptor")),
                    value.getString("host"), value.getInt("port"),
                    MoriceProtocol.unb64(value.getString("sessionKey")),
                    MoriceProtocol.strings(value.optJSONArray("localPermissions")),
                    MoriceProtocol.strings(value.optJSONArray("remoteGrants")),
                    value.optLong("pairedAt", System.currentTimeMillis())
            );
        }
    }

    private final Context context;
    private final SharedPreferences preferences;

    SecureNodeStore(Context context) {
        this.context = context.getApplicationContext();
        this.preferences = this.context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    synchronized MoriceProtocol.Identity identity() throws GeneralSecurityException, JSONException {
        String encoded = preferences.getString(IDENTITY, "");
        if (!encoded.isEmpty()) {
            JSONObject value = new JSONObject(new String(unprotect(encoded), StandardCharsets.UTF_8));
            return MoriceProtocol.restoreIdentity(
                    MoriceProtocol.unb64(value.getString("private")),
                    MoriceProtocol.unb64(value.getString("public"))
            );
        }
        KeyPair pair = MoriceProtocol.generateEcKeyPair();
        MoriceProtocol.Identity identity = new MoriceProtocol.Identity(pair.getPrivate(), pair.getPublic());
        JSONObject value = new JSONObject();
        value.put("private", MoriceProtocol.b64(pair.getPrivate().getEncoded()));
        value.put("public", MoriceProtocol.b64(pair.getPublic().getEncoded()));
        preferences.edit().putString(IDENTITY, protect(value.toString().getBytes(StandardCharsets.UTF_8))).apply();
        return identity;
    }

    MoriceProtocol.Descriptor localDescriptor() {
        String stable = preferences.getString("local-device-id", "");
        if (stable.isEmpty()) {
            stable = UUID.randomUUID().toString();
            preferences.edit().putString("local-device-id", stable).apply();
        }
        return new MoriceProtocol.Descriptor(
                "android-" + stable,
                Build.MANUFACTURER + " " + Build.MODEL,
                "android",
                Arrays.asList(
                        "device.status", "camera.capture", "vision.stream", "microphone.input",
                        "notifications.read", "media.control", "application.open", "file.receive"
                ),
                "0.8.0-android"
        );
    }

    synchronized void putPeer(Peer peer) throws GeneralSecurityException, JSONException {
        JSONObject peers = readPeers();
        peers.put(peer.descriptor.deviceId, peer.toJson());
        writePeers(peers);
    }

    synchronized Peer peer(String deviceId) throws GeneralSecurityException, JSONException {
        JSONObject value = readPeers().optJSONObject(deviceId);
        return value == null ? null : Peer.fromJson(value);
    }

    synchronized List<Peer> peers() throws GeneralSecurityException, JSONException {
        JSONObject values = readPeers();
        List<Peer> result = new ArrayList<>();
        for (java.util.Iterator<String> keys = values.keys(); keys.hasNext();) {
            JSONObject value = values.optJSONObject(keys.next());
            if (value != null) result.add(Peer.fromJson(value));
        }
        result.sort((left, right) -> left.descriptor.deviceName.compareToIgnoreCase(right.descriptor.deviceName));
        return result;
    }

    synchronized void revoke(String deviceId) throws GeneralSecurityException, JSONException {
        JSONObject peers = readPeers();
        peers.remove(deviceId);
        writePeers(peers);
    }

    synchronized void putSecret(String name, String value) throws GeneralSecurityException {
        String cleanName = name == null ? "" : name.replaceAll("[^A-Za-z0-9_.-]", "");
        if (cleanName.isEmpty()) throw new GeneralSecurityException("Invalid secret name.");
        SharedPreferences.Editor editor = preferences.edit();
        if (value == null || value.isEmpty()) editor.remove("secret." + cleanName);
        else editor.putString("secret." + cleanName, protect(value.getBytes(StandardCharsets.UTF_8)));
        editor.apply();
    }

    synchronized String secret(String name) throws GeneralSecurityException, JSONException {
        String cleanName = name == null ? "" : name.replaceAll("[^A-Za-z0-9_.-]", "");
        String value = preferences.getString("secret." + cleanName, "");
        return value.isEmpty() ? "" : new String(unprotect(value), StandardCharsets.UTF_8);
    }

    private JSONObject readPeers() throws GeneralSecurityException, JSONException {
        String encoded = preferences.getString(PEERS, "");
        if (encoded.isEmpty()) return new JSONObject();
        return new JSONObject(new String(unprotect(encoded), StandardCharsets.UTF_8));
    }

    private void writePeers(JSONObject peers) throws GeneralSecurityException {
        preferences.edit().putString(PEERS, protect(peers.toString().getBytes(StandardCharsets.UTF_8))).apply();
    }

    private SecretKey masterKey() throws GeneralSecurityException {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        try {
            store.load(null);
        } catch (IOException error) {
            throw new GeneralSecurityException(error);
        }
        if (store.containsAlias(MASTER_ALIAS)) {
            return ((KeyStore.SecretKeyEntry) store.getEntry(MASTER_ALIAS, null)).getSecretKey();
        }
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(
                MASTER_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT
        ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return generator.generateKey();
    }

    private String protect(byte[] plaintext) throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, masterKey());
        byte[] ciphertext = cipher.doFinal(plaintext);
        JSONObject envelope = new JSONObject();
        try {
            envelope.put("nonce", MoriceProtocol.b64(cipher.getIV()));
            envelope.put("ciphertext", MoriceProtocol.b64(ciphertext));
        } catch (JSONException error) {
            throw new GeneralSecurityException(error);
        }
        return MoriceProtocol.b64(envelope.toString().getBytes(StandardCharsets.UTF_8));
    }

    private byte[] unprotect(String encoded) throws GeneralSecurityException, JSONException {
        JSONObject envelope = new JSONObject(new String(MoriceProtocol.unb64(encoded), StandardCharsets.UTF_8));
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, masterKey(), new GCMParameterSpec(128, MoriceProtocol.unb64(envelope.getString("nonce"))));
        return cipher.doFinal(MoriceProtocol.unb64(envelope.getString("ciphertext")));
    }
}
