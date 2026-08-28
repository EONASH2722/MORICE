package ai.morice.companion;

import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

final class MoriceProtocol {
    static final String VERSION = "morice-node/1";
    static final int DEFAULT_PORT = 47651;
    static final int MAX_FRAME_BYTES = 16 * 1024 * 1024;
    private static final SecureRandom RANDOM = new SecureRandom();

    private MoriceProtocol() {}

    static final class Identity {
        final PrivateKey privateKey;
        final PublicKey publicKey;

        Identity(PrivateKey privateKey, PublicKey publicKey) {
            this.privateKey = privateKey;
            this.publicKey = publicKey;
        }

        String publicText() {
            return b64(uncompressedPoint(publicKey));
        }

        String fingerprint() throws GeneralSecurityException {
            String hex = hex(MessageDigest.getInstance("SHA-256").digest(uncompressedPoint(publicKey))).toUpperCase(Locale.ROOT);
            List<String> groups = new ArrayList<>();
            for (int i = 0; i < 24; i += 4) groups.add(hex.substring(i, i + 4));
            return String.join(":", groups);
        }
    }

    static final class Descriptor {
        final String deviceId;
        final String deviceName;
        final String platform;
        final List<String> capabilities;
        final String appVersion;

        Descriptor(String deviceId, String deviceName, String platform, List<String> capabilities, String appVersion) {
            this.deviceId = deviceId;
            this.deviceName = deviceName;
            this.platform = platform;
            this.capabilities = Collections.unmodifiableList(new ArrayList<>(capabilities));
            this.appVersion = appVersion;
        }

        JSONObject toJson() throws JSONException {
            JSONObject value = new JSONObject();
            value.put("deviceId", deviceId);
            value.put("deviceName", deviceName);
            value.put("platform", platform);
            value.put("capabilities", new JSONArray(capabilities));
            value.put("appVersion", appVersion);
            value.put("connectionTypes", new JSONArray(Arrays.asList("lan", "direct-ip", "future-relay")));
            return value;
        }

        static Descriptor fromJson(JSONObject value) throws JSONException {
            return new Descriptor(
                    value.getString("deviceId"),
                    value.optString("deviceName", "MORICE node"),
                    value.optString("platform", "unknown"),
                    strings(value.optJSONArray("capabilities")),
                    value.optString("appVersion", "")
            );
        }
    }

    static final class Message {
        final String type;
        final String senderId;
        final String recipientId;
        final JSONObject payload;
        final String messageId;
        final String taskId;
        final double sentAt;

        Message(String type, String senderId, String recipientId, JSONObject payload) {
            this(type, senderId, recipientId, payload, UUID.randomUUID().toString().replace("-", ""), "", System.currentTimeMillis() / 1000.0);
        }

        Message(String type, String senderId, String recipientId, JSONObject payload, String messageId, String taskId, double sentAt) {
            this.type = type;
            this.senderId = senderId;
            this.recipientId = recipientId;
            this.payload = payload;
            this.messageId = messageId;
            this.taskId = taskId;
            this.sentAt = sentAt;
        }

        JSONObject toJson() throws JSONException {
            JSONObject value = new JSONObject();
            value.put("protocol", VERSION);
            value.put("type", type);
            value.put("messageId", messageId);
            value.put("taskId", taskId);
            value.put("senderId", senderId);
            value.put("recipientId", recipientId);
            value.put("sentAt", sentAt);
            value.put("payload", payload);
            return value;
        }

        static Message fromJson(JSONObject value) throws JSONException {
            if (!VERSION.equals(value.optString("protocol"))) throw new JSONException("Unsupported MORICE protocol.");
            return new Message(
                    value.getString("type"), value.getString("senderId"), value.getString("recipientId"),
                    value.getJSONObject("payload"), value.getString("messageId"), value.optString("taskId", ""),
                    value.getDouble("sentAt")
            );
        }
    }

    static KeyPair generateEcKeyPair() throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"), RANDOM);
        return generator.generateKeyPair();
    }

    static Identity restoreIdentity(byte[] privateEncoded, byte[] publicEncoded) throws GeneralSecurityException {
        KeyFactory factory = KeyFactory.getInstance("EC");
        return new Identity(
                factory.generatePrivate(new PKCS8EncodedKeySpec(privateEncoded)),
                factory.generatePublic(new X509EncodedKeySpec(publicEncoded))
        );
    }

    static PublicKey parseUncompressedPublic(String text) throws GeneralSecurityException {
        byte[] raw = unb64(text);
        if (raw.length != 65 || raw[0] != 4) throw new GeneralSecurityException("Invalid P-256 public key.");
        byte[] prefix = hexBytes("3059301306072A8648CE3D020106082A8648CE3D030107034200");
        byte[] encoded = new byte[prefix.length + raw.length];
        System.arraycopy(prefix, 0, encoded, 0, prefix.length);
        System.arraycopy(raw, 0, encoded, prefix.length, raw.length);
        return KeyFactory.getInstance("EC").generatePublic(new X509EncodedKeySpec(encoded));
    }

    static byte[] uncompressedPoint(PublicKey publicKey) {
        byte[] encoded = publicKey.getEncoded();
        return Arrays.copyOfRange(encoded, encoded.length - 65, encoded.length);
    }

    static byte[] derivePairKey(PrivateKey localEphemeral, String peerEphemeral, byte[] requestNonce, byte[] responseNonce) throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("ECDH");
        agreement.init(localEphemeral);
        agreement.doPhase(parseUncompressedPublic(peerEphemeral), true);
        byte[] salt = new byte[requestNonce.length + responseNonce.length];
        System.arraycopy(requestNonce, 0, salt, 0, requestNonce.length);
        System.arraycopy(responseNonce, 0, salt, requestNonce.length, responseNonce.length);
        return hkdf(agreement.generateSecret(), salt, "MORICE authenticated node pairing v1".getBytes(StandardCharsets.UTF_8), 32);
    }

    static String verificationCode(byte[] key, String firstId, String secondId) throws GeneralSecurityException {
        List<String> ids = new ArrayList<>(Arrays.asList(firstId, secondId));
        Collections.sort(ids);
        byte[] digest = hmac(key, ("verify|" + String.join("|", ids)).getBytes(StandardCharsets.UTF_8));
        long number = ByteBuffer.wrap(digest, 0, 4).getInt() & 0xffffffffL;
        return String.format(Locale.ROOT, "%06d", number % 1_000_000L);
    }

    static JSONObject seal(Message message, byte[] key) throws GeneralSecurityException, JSONException {
        byte[] nonce = randomBytes(12);
        JSONObject aad = aad(message.senderId, message.recipientId, message.messageId);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
        cipher.updateAAD(canonical(aad));
        byte[] ciphertext = cipher.doFinal(canonical(message.toJson()));
        aad.put("nonce", b64(nonce));
        aad.put("ciphertext", b64(ciphertext));
        return aad;
    }

    static Message open(JSONObject envelope, byte[] key, String localId, String peerId) throws GeneralSecurityException, JSONException {
        if (!peerId.equals(envelope.optString("senderId")) || !localId.equals(envelope.optString("recipientId"))) {
            throw new GeneralSecurityException("Envelope endpoints do not match the paired node.");
        }
        String messageId = envelope.getString("messageId");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, unb64(envelope.getString("nonce"))));
        cipher.updateAAD(canonical(aad(peerId, localId, messageId)));
        Message message = Message.fromJson(new JSONObject(new String(cipher.doFinal(unb64(envelope.getString("ciphertext"))), StandardCharsets.UTF_8)));
        if (!messageId.equals(message.messageId)) throw new GeneralSecurityException("Envelope id mismatch.");
        if (Math.abs(System.currentTimeMillis() / 1000.0 - message.sentAt) > 300) throw new GeneralSecurityException("Message expired.");
        return message;
    }

    static byte[] frame(byte[] payload) {
        return ByteBuffer.allocate(payload.length + 4).putInt(payload.length).put(payload).array();
    }

    static byte[] canonical(JSONObject value) {
        // org.json preserves insertion order. All protocol objects are built in
        // the same explicit field order as the desktop canonical envelope.
        return value.toString().getBytes(StandardCharsets.UTF_8);
    }

    static String b64(byte[] value) {
        return Base64.encodeToString(value, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    static byte[] unb64(String value) {
        return Base64.decode(value, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    static byte[] randomBytes(int length) {
        byte[] value = new byte[length];
        RANDOM.nextBytes(value);
        return value;
    }

    static List<String> strings(JSONArray array) throws JSONException {
        List<String> result = new ArrayList<>();
        if (array == null) return result;
        for (int index = 0; index < array.length(); index++) {
            String value = array.getString(index).trim();
            if (!value.isEmpty() && !result.contains(value)) result.add(value);
        }
        return result;
    }

    private static JSONObject aad(String sender, String recipient, String messageId) throws JSONException {
        JSONObject value = new JSONObject();
        value.put("messageId", messageId);
        value.put("protocol", VERSION);
        value.put("recipientId", recipient);
        value.put("senderId", sender);
        return value;
    }

    private static byte[] hkdf(byte[] ikm, byte[] salt, byte[] info, int length) throws GeneralSecurityException {
        byte[] prk = hmac(salt, ikm);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] previous = new byte[0];
        int counter = 1;
        while (output.size() < length) {
            ByteArrayOutputStream input = new ByteArrayOutputStream();
            input.write(previous, 0, previous.length);
            input.write(info, 0, info.length);
            input.write(counter++);
            previous = hmac(prk, input.toByteArray());
            output.write(previous, 0, previous.length);
        }
        return Arrays.copyOf(output.toByteArray(), length);
    }

    private static byte[] hmac(byte[] key, byte[] value) throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(value);
    }

    private static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) result.append(String.format(Locale.ROOT, "%02x", value));
        return result.toString();
    }

    private static byte[] hexBytes(String value) {
        byte[] result = new byte[value.length() / 2];
        for (int i = 0; i < result.length; i++) result[i] = (byte) Integer.parseInt(value.substring(i * 2, i * 2 + 2), 16);
        return result;
    }
}
