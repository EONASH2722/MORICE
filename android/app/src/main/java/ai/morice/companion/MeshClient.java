package ai.morice.companion;

import org.json.JSONArray;
import org.json.JSONObject;
import javax.net.ssl.SSLSocket;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/** Same bounded mesh/2 frames as the desktop; no custom encryption protocol. */
final class MeshClient {
    static final String VERSION = "morice-mesh/2";
    static final int MAX_FRAME = 384 * 1024;
    final MeshIdentity identity;
    MeshClient(SecureNodeStore store) throws Exception { identity = new MeshIdentity(store); }

    JSONObject descriptor() throws Exception {
        return new JSONObject().put("deviceId", identity.nodeId).put("deviceName", android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL)
            .put("platform", "android").put("appVersion", "0.8.0-android").put("protocolVersion", VERSION)
            .put("capabilities", new JSONArray()).put("metadata", new JSONObject().put("port", NodeConnectionService.PHONE_NODE_PORT));
    }

    static JSONObject read(DataInputStream input) throws Exception {
        int size = input.readInt();
        if (size < 2 || size > MAX_FRAME) throw new SecurityException("Invalid mesh frame length.");
        byte[] bytes = new byte[size]; input.readFully(bytes);
        JSONObject value = MeshJson.parse(bytes);
        if (!VERSION.equals(value.optString("version"))) throw new SecurityException("Incompatible mesh version.");
        return value;
    }
    static void write(DataOutputStream output, JSONObject value) throws Exception {
        byte[] bytes = value.toString().getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_FRAME) throw new SecurityException("Mesh frame too large.");
        output.writeInt(bytes.length); output.write(bytes); output.flush();
    }
    JSONObject rpc(String host, int port, String pin, String operation, JSONObject payload) throws Exception {
        if (pin == null || !pin.matches("[a-f0-9]{64}")) throw new SecurityException("Full certificate fingerprint required.");
        String request = UUID.randomUUID().toString().replace("-", "");
        try (SSLSocket socket = (SSLSocket) identity.context(pin, false).getSocketFactory().createSocket()) {
            socket.connect(new InetSocketAddress(host, port), 2500); socket.setSoTimeout(2500);
            socket.setEnabledProtocols(new String[]{"TLSv1.3"}); socket.startHandshake();
            write(new DataOutputStream(socket.getOutputStream()), new JSONObject().put("version", VERSION)
                .put("op", operation).put("request_id", request).put("sender", identity.nodeId).put("payload", payload));
            JSONObject response = read(new DataInputStream(socket.getInputStream()));
            if (!request.equals(response.optString("request_id"))) throw new SecurityException("Response identity mismatch.");
            return response.getJSONObject("payload");
        }
    }
    JSONObject begin(String host, int port, String code, String pin) throws Exception {
        JSONObject response = rpc(host, port, pin, "pair", new JSONObject().put("code", code)
            .put("certificate", identity.pem()).put("descriptor", descriptor()));
        return response.put("host", host).put("pair_port", port).put("pin", pin);
    }
    JSONObject finish(JSONObject pending) throws Exception {
        JSONObject result = rpc(pending.getString("host"), pending.getInt("pair_port"), pending.getString("pin"),
            "pair_status", new JSONObject().put("pair_id", pending.getString("pair_id")));
        if (!"trusted".equals(result.optString("state"))) throw new SecurityException("Confirm this phone on the desktop first.");
        String id = result.getJSONObject("descriptor").getString("deviceId");
        if (!id.equals(MeshIdentity.id(MeshIdentity.parse(result.getString("certificate"))))) throw new SecurityException("Peer identity mismatch.");
        JSONObject peer = new JSONObject().put("certificate", result.getString("certificate")).put("host", pending.getString("host"))
            .put("port", result.getInt("port")).put("grants", result.getJSONArray("grants"))
            .put("local_grants", new JSONArray(new String[]{"device.status", "battery.status", "file.receive", "volume.get", "volume.set", "application.open"}));
        identity.savePeer(id, peer);
        rpc(peer.getString("host"), peer.getInt("port"), MeshIdentity.pin(MeshIdentity.parse(peer.getString("certificate"))), "hello", new JSONObject());
        return result;
    }
}
