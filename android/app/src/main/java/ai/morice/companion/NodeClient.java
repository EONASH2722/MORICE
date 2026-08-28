package ai.morice.companion;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

final class NodeClient {
    static final class PairingSession {
        final String host;
        final int port;
        final MoriceProtocol.Descriptor peer;
        final String peerIdentityPublic;
        final byte[] sessionKey;
        final String verificationCode;

        PairingSession(String host, int port, MoriceProtocol.Descriptor peer, String peerIdentityPublic,
                       byte[] sessionKey, String verificationCode) {
            this.host = host;
            this.port = port;
            this.peer = peer;
            this.peerIdentityPublic = peerIdentityPublic;
            this.sessionKey = sessionKey.clone();
            this.verificationCode = verificationCode;
        }
    }

    private final SecureNodeStore store;
    private final MoriceProtocol.Descriptor local;
    private final MoriceProtocol.Identity identity;

    NodeClient(SecureNodeStore store) throws GeneralSecurityException, JSONException {
        this.store = store;
        this.local = store.localDescriptor();
        this.identity = store.identity();
    }

    PairingSession beginPairing(String host, int port) throws Exception {
        KeyPair ephemeral = MoriceProtocol.generateEcKeyPair();
        byte[] requestNonce = MoriceProtocol.randomBytes(16);
        JSONObject payload = new JSONObject();
        payload.put("descriptor", local.toJson());
        payload.put("identityPublicKey", identity.publicText());
        payload.put("ephemeralPublicKey", MoriceProtocol.b64(MoriceProtocol.uncompressedPoint(ephemeral.getPublic())));
        payload.put("requestNonce", MoriceProtocol.b64(requestNonce));
        MoriceProtocol.Message request = new MoriceProtocol.Message("PAIR_REQUEST", local.deviceId, "unpaired", payload);
        MoriceProtocol.Message challenge = MoriceProtocol.Message.fromJson(transact(host, port, request.toJson(), 15_000));
        if (!"PAIR_CHALLENGE".equals(challenge.type)) throw new GeneralSecurityException("Desktop did not return a pairing challenge.");
        JSONObject response = challenge.payload;
        byte[] responseNonce = MoriceProtocol.unb64(response.getString("responseNonce"));
        byte[] key = MoriceProtocol.derivePairKey(
                ephemeral.getPrivate(), response.getString("ephemeralPublicKey"), requestNonce, responseNonce
        );
        MoriceProtocol.Descriptor peer = MoriceProtocol.Descriptor.fromJson(response.getJSONObject("descriptor"));
        String code = MoriceProtocol.verificationCode(key, local.deviceId, peer.deviceId);
        if (!code.equals(response.getString("verificationCode"))) throw new GeneralSecurityException("Pairing code authentication failed.");
        return new PairingSession(host, port, peer, response.getString("identityPublicKey"), key, code);
    }

    SecureNodeStore.Peer confirmPairing(
            PairingSession session,
            List<String> requestedDesktopCapabilities,
            List<String> desktopPermissionsOnPhone
    ) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("verificationCode", session.verificationCode);
        payload.put("requestedCapabilities", new JSONArray(requestedDesktopCapabilities));
        payload.put("offeredCapabilities", new JSONArray(desktopPermissionsOnPhone));
        payload.put("nodePort", NodeConnectionService.PHONE_NODE_PORT);
        MoriceProtocol.Message accept = new MoriceProtocol.Message(
                "PAIR_ACCEPT", local.deviceId, session.peer.deviceId, payload
        );
        MoriceProtocol.Message accepted = MoriceProtocol.Message.fromJson(
                transact(session.host, session.port, accept.toJson(), 15_000)
        );
        if (!"PAIR_ACCEPT".equals(accepted.type) || !accepted.payload.optBoolean("paired", false)) {
            throw new GeneralSecurityException(accepted.payload.optString("error", "Pairing was rejected."));
        }
        List<String> remoteGrants = MoriceProtocol.strings(accepted.payload.optJSONArray("grantedCapabilities"));
        SecureNodeStore.Peer peer = new SecureNodeStore.Peer(
                session.peer, session.host, session.port, session.sessionKey,
                desktopPermissionsOnPhone, remoteGrants, System.currentTimeMillis()
        );
        store.putPeer(peer);
        return peer;
    }

    MoriceProtocol.Message task(SecureNodeStore.Peer peer, String capability, JSONObject arguments, int timeoutMs) throws Exception {
        if (!peer.remoteGrants.contains(capability)) {
            throw new SecurityException("This desktop did not grant " + capability + " to the phone.");
        }
        JSONObject payload = new JSONObject();
        payload.put("capability", capability);
        payload.put("arguments", arguments == null ? new JSONObject() : arguments);
        String taskId = UUID.randomUUID().toString().replace("-", "");
        MoriceProtocol.Message request = new MoriceProtocol.Message(
                "TASK_REQUEST", local.deviceId, peer.descriptor.deviceId, payload,
                UUID.randomUUID().toString().replace("-", ""), taskId,
                System.currentTimeMillis() / 1000.0
        );
        JSONObject envelope = MoriceProtocol.seal(request, peer.sessionKey);
        JSONObject responseEnvelope = transact(peer.host, peer.port, envelope, timeoutMs);
        MoriceProtocol.Message response = MoriceProtocol.open(
                responseEnvelope, peer.sessionKey, local.deviceId, peer.descriptor.deviceId
        );
        if ("ERROR".equals(response.type)) {
            throw new IOException(response.payload.optString("error", "Remote MORICE task failed."));
        }
        return response;
    }

    private JSONObject transact(String host, int port, JSONObject payload, int timeoutMs) throws IOException, JSONException {
        byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8);
        if (bytes.length <= 0 || bytes.length > MoriceProtocol.MAX_FRAME_BYTES) throw new IOException("MORICE frame is too large.");
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), timeoutMs);
            socket.setSoTimeout(timeoutMs);
            DataOutputStream output = new DataOutputStream(socket.getOutputStream());
            output.writeInt(bytes.length);
            output.write(bytes);
            output.flush();
            DataInputStream input = new DataInputStream(socket.getInputStream());
            int size = input.readInt();
            if (size <= 0 || size > MoriceProtocol.MAX_FRAME_BYTES) throw new IOException("Invalid MORICE frame size.");
            byte[] response = new byte[size];
            input.readFully(response);
            return new JSONObject(new String(response, StandardCharsets.UTF_8));
        }
    }
}
