package ai.morice.companion;

import android.content.Context;
import android.content.Intent;
import android.media.AudioManager;
import android.os.BatteryManager;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.concurrent.ConcurrentHashMap;

/** Minimal real Android adapters. Unsupported capture/sensors/shell are never advertised. */
final class MeshNode {
    final Context context;
    final MeshIdentity identity;
    final ConcurrentHashMap<String, JSONObject> results = new ConcurrentHashMap<>();
    final ConcurrentHashMap<String, JSONObject> observations = new ConcurrentHashMap<>();
    final File inbox;
    final JSONObject intents;
    static volatile boolean foreground;

    MeshNode(Context context, SecureNodeStore store) throws Exception {
        this.context = context; identity = new MeshIdentity(store);
        inbox = new File(context.getFilesDir(), "mesh-inbox"); inbox.mkdirs();
        String ledger = store.secret("mesh.commands"); intents = ledger.isEmpty() ? new JSONObject() : new JSONObject(ledger);
    }
    JSONObject status() throws Exception {
        BatteryManager battery = (BatteryManager) context.getSystemService(Context.BATTERY_SERVICE);
        return new JSONObject().put("platform", "android").put("battery", battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))
            .put("online", true).put("cpu_count", Runtime.getRuntime().availableProcessors());
    }
    JSONObject capabilities() throws Exception {
        JSONArray entries = new JSONArray();
        for (String cap : new String[]{"device.status", "battery.status", "file.receive", "volume.get", "volume.set", "application.open"}) {
            entries.put(new JSONObject().put("capability_id", cap).put("name", cap).put("input_schema", new JSONObject().put("type", "object"))
                .put("status", cap.equals("application.open") ? (foreground ? "degraded" : "unavailable") : "available")
                .put("risk_level", "low").put("timeout", 15).put("supported_resources", new JSONArray()));
        }
        return new JSONObject().put("capabilities", entries).put("status", status()).put("resource_capacities", new JSONObject().put("CPU", 1).put("DISK", 1));
    }
    static boolean contains(JSONArray items, String value) {
        for (int i = 0; items != null && i < items.length(); i++) if (value.equals(items.optString(i))) return true;
        return false;
    }
    static String hash(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream stream = new FileInputStream(file)) {
            byte[] bytes = new byte[131072]; int count;
            while ((count = stream.read(bytes)) != -1) digest.update(bytes, 0, count);
        }
        return MeshIdentity.hex(digest.digest());
    }
    static boolean replaySafe(String cap) {
        return cap.equals("file.receive") || cap.equals("device.status") || cap.equals("battery.status") || cap.equals("volume.get");
    }
    void persistIntents() throws Exception {
        JSONObject durable = new JSONObject();
        for (java.util.Iterator<String> keys = intents.keys(); keys.hasNext();) {
            String key = keys.next(); JSONObject record = intents.getJSONObject(key);
            if (!replaySafe(record.getString("capability"))) durable.put(key, record);
        }
        identity.store.putSecret("mesh.commands", durable.toString());
    }
    static String digest(JSONObject payload) throws Exception {
        return MeshIdentity.hex(MessageDigest.getInstance("SHA-256").digest((payload.getString("capability") + "|" + payload.getJSONObject("inputs").toString() + "|" + payload.opt("expected")).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }
    synchronized JSONObject file(JSONObject args, String peer) throws Exception {
        String key = args.getString("transfer_id");
        if (!key.matches("[a-f0-9]{32}")) throw new SecurityException("Invalid transfer ID.");
        String op = args.getString("op");
        File metadata = new File(inbox, "." + key + ".json"), partial = new File(inbox, "." + key + ".partial");
        JSONObject record = metadata.exists() ? new JSONObject(new String(Files.readAllBytes(metadata.toPath()), java.nio.charset.StandardCharsets.UTF_8)) : null;
        if (record != null && !peer.equals(record.getString("peer"))) throw new SecurityException("Transfer owner differs.");
        if (op.equals("cancel")) { partial.delete(); metadata.delete(); return new JSONObject().put("complete", false).put("cancelled", true); }
        if (op.equals("begin")) {
            String name = args.getString("name"); long size = args.getLong("size"); String sha = args.getString("sha256");
            if (!name.matches("[A-Za-z0-9][A-Za-z0-9_. -]{0,150}") || name.endsWith(".") || name.endsWith(" ") || size < 0 || size > 67108864 || !sha.matches("[a-f0-9]{64}")) throw new SecurityException("Invalid Inbox file metadata.");
            File destination = new File(inbox, name);
            if (destination.exists()) {
                if (destination.length() == size && hash(destination).equals(sha)) return new JSONObject().put("complete", true).put("size", size).put("offset", size).put("sha256", sha).put("deduplicated", true);
                throw new SecurityException("Destination already exists.");
            }
            if (record != null && (!name.equals(record.getString("name")) || size != record.getLong("size") || !sha.equals(record.getString("sha256")))) throw new SecurityException("Transfer metadata conflict.");
            if (record == null) {
                if (inbox.listFiles().length > 128) throw new SecurityException("Inbox record limit reached.");
                record = new JSONObject().put("peer", peer).put("name", name).put("size", size).put("sha256", sha).put("offset", 0).put("partial_hash", MeshIdentity.hex(MessageDigest.getInstance("SHA-256").digest(new byte[0])));
                partial.createNewFile();
            }
            if (partial.length() != record.getLong("offset") || !hash(partial).equals(record.getString("partial_hash"))) throw new SecurityException("Partial transfer is corrupt.");
        } else {
            if (record == null) throw new SecurityException("Transfer not found.");
            if (op.equals("chunk")) {
                byte[] data = Base64.decode(args.getString("data"), Base64.NO_WRAP); long offset = args.getLong("offset");
                if (data.length == 0 || data.length > 131072 || offset != record.getLong("offset") || offset + data.length > record.getLong("size")) throw new SecurityException("Invalid file range.");
                try (RandomAccessFile stream = new RandomAccessFile(partial, "rw")) { stream.seek(offset); stream.write(data); stream.getFD().sync(); }
                record.put("offset", offset + data.length).put("partial_hash", hash(partial));
            } else if (op.equals("finish")) {
                if (partial.length() != record.getLong("size") || !hash(partial).equals(record.getString("sha256"))) throw new SecurityException("File integrity verification failed.");
                File destination = new File(inbox, record.getString("name"));
                if (destination.exists()) throw new SecurityException("Destination changed.");
                Files.move(partial.toPath(), destination.toPath(), StandardCopyOption.ATOMIC_MOVE); metadata.delete();
                return new JSONObject().put("complete", true).put("offset", destination.length()).put("size", destination.length()).put("sha256", hash(destination)).put("name", destination.getName());
            } else if (!op.equals("status")) throw new SecurityException("Unsupported transfer operation.");
        }
        File tmp = new File(inbox, "." + key + ".tmp");
        Files.write(tmp.toPath(), record.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
        Files.move(tmp.toPath(), metadata.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        return new JSONObject().put("complete", false).put("offset", partial.length()).put("size", record.getLong("size")).put("sha256", "").put("name", record.getString("name"));
    }
    synchronized JSONObject dispatch(String op, JSONObject payload, String sender) throws Exception {
        JSONObject peer = identity.peer(sender);
        if (peer == null) throw new SecurityException("Revoked/unpaired peer.");
        if (op.equals("hello")) return capabilities().put("granted_capabilities", peer.getJSONArray("local_grants"));
        if (op.equals("ping")) return new JSONObject().put("online", true);
        String key = payload.getString("command_id");
        if (!key.matches("[a-zA-Z0-9_.:-]{1,100}")) throw new SecurityException("Invalid command ID.");
        if (results.containsKey(key)) {
            if (!sender.equals(intents.getJSONObject(key).getString("peer"))) throw new SecurityException("Command owner differs.");
            String granted = intents.getJSONObject(key).getString("capability");
            if (!contains(peer.getJSONArray("local_grants"), granted)) throw new SecurityException("Capability permission was withdrawn.");
            if (op.equals("submit")) {
                String digest = digest(payload);
                if (!digest.equals(intents.getJSONObject(key).getString("digest"))) throw new SecurityException("Command ID reused for a different action.");
            }
            if (op.equals("observe")) {
                JSONObject proof = new JSONObject(observations.get(key).toString());
                String cap = proof.getString("capability");
                if (cap.equals("device.status") || cap.equals("battery.status")) proof.put("observation", status());
                else if (cap.startsWith("volume.")) {
                    AudioManager audio = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
                    int observedLevel = audio.getStreamVolume(AudioManager.STREAM_MUSIC);
                    if (cap.equals("volume.set") && observedLevel != proof.getJSONObject("observation").getInt("level")) {
                        proof.put("verification", "inconclusive").put("state", "failed");
                    }
                    proof.put("observation", new JSONObject().put("level", observedLevel).put("maximum", audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)));
                } else if (cap.equals("file.receive")) {
                    JSONObject actual = proof.getJSONObject("observation");
                    if (actual.optBoolean("complete")) {
                        File destination = new File(inbox, actual.getString("name"));
                        actual.put("complete", destination.isFile() && destination.length() == actual.getLong("size") && hash(destination).equals(actual.getString("sha256")));
                        if (!actual.getBoolean("complete")) proof.put("verification", "inconclusive").put("state", "failed");
                    } else if (intents.getJSONObject(key).has("transfer_id")) {
                        File partial = new File(inbox, "." + intents.getJSONObject(key).getString("transfer_id") + ".partial");
                        actual.put("offset", partial.isFile() ? partial.length() : 0);
                    }
                }
                return proof;
            }
            if (op.equals("cancel")) return new JSONObject().put("state", results.get(key).getString("state"));
            return results.get(key);
        }
        if (!op.equals("submit")) return new JSONObject().put("state", "unknown");
        if (intents.has(key)) return new JSONObject().put("state", "unknown").put("error", "Interrupted action requires observation; no replay.");
        String cap = payload.getString("capability"); JSONObject args = payload.getJSONObject("inputs");
        if (!contains(peer.getJSONArray("local_grants"), cap)) throw new SecurityException("Capability permission denied.");
        Object ttl = payload.opt("ttl");
        if (ttl != null && (!(ttl instanceof Number) || !Double.isFinite(((Number) ttl).doubleValue()) || ((Number) ttl).doubleValue() < .05 || ((Number) ttl).doubleValue() > 60)) throw new SecurityException("Invalid deadline.");
        if (intents.length() >= 200) {
            java.util.ArrayList<String> discard = new java.util.ArrayList<>();
            for (java.util.Iterator<String> keys = intents.keys(); keys.hasNext();) {
                String previous = keys.next();
                if (results.containsKey(previous) && replaySafe(intents.getJSONObject(previous).getString("capability"))) discard.add(previous);
            }
            for (String previous : discard) { intents.remove(previous); results.remove(previous); observations.remove(previous); }
        }
        if (intents.length() >= 256) throw new SecurityException("Command ledger is full.");
        String digest = digest(payload);
        JSONObject intent = new JSONObject().put("peer", sender).put("capability", cap).put("digest", digest);
        if (cap.equals("file.receive")) intent.put("transfer_id", args.getString("transfer_id"));
        intents.put(key, intent);
        persistIntents();
        JSONObject actual; boolean verified = true;
        AudioManager audio = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
        if (cap.equals("device.status") || cap.equals("battery.status")) actual = status();
        else if (cap.equals("file.receive")) actual = file(args, sender);
        else if (cap.equals("volume.get") || cap.equals("volume.set")) {
            if (cap.equals("volume.set")) {
                int percent = args.getInt("percent"); if (percent < 0 || percent > 100) throw new SecurityException("Invalid volume.");
                audio.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC) * percent / 100f), AudioManager.FLAG_SHOW_UI);
                verified = audio.getStreamVolume(AudioManager.STREAM_MUSIC) == Math.round(audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC) * percent / 100f);
            }
            actual = new JSONObject().put("level", audio.getStreamVolume(AudioManager.STREAM_MUSIC)).put("maximum", audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC));
        } else if (cap.equals("application.open")) {
            if (!foreground) throw new SecurityException("Open the MORICE phone app in the foreground first.");
            String url = args.getString("url"); android.net.Uri uri = android.net.Uri.parse(url);
            if (!"https".equals(uri.getScheme()) && !"http".equals(uri.getScheme())) throw new SecurityException("Only explicit web links are supported.");
            context.startActivity(new Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            actual = new JSONObject().put("intent_requested", true); verified = false;
        } else throw new SecurityException("Unsupported Android capability.");
        JSONObject desired = payload.optJSONObject("expected");
        if (desired != null) for (java.util.Iterator<String> keys = desired.keys(); keys.hasNext();) {
            String field = keys.next(); if (!actual.has(field) || !desired.get(field).equals(actual.get(field))) verified = false;
        }
        String verification = verified ? "verified" : "inconclusive";
        JSONObject proof = new JSONObject().put("status", verification).put("evidence", new JSONArray(new String[]{"Android API/file observation"})).put("message", verified ? "" : "Final Android app state cannot be independently observed.");
        JSONObject result = new JSONObject().put("status", verified ? "succeeded" : "failed").put("success", verified).put("output", actual)
            .put("verification", proof).put("verification_required", true).put("task_id", key).put("capability_id", cap)
            .put("execution_id", java.util.UUID.randomUUID().toString().replace("-", ""));
        JSONObject envelope = new JSONObject().put("state", verified ? "verified" : "failed").put("command_id", key).put("result", result).put("physical_active", false);
        results.put(key, envelope);
        observations.put(key, new JSONObject().put("state", envelope.getString("state")).put("command_id", key).put("capability", cap).put("verification", verification).put("observation", actual));
        return envelope;
    }
}
