package ai.morice.companion;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.UUID;
import static org.junit.Assert.*;

/** Requires an owned Android 10+ device; compilation alone is not execution evidence. */
@RunWith(AndroidJUnit4.class)
public final class MeshInstrumentedTest {
    @Test public void identityIsStableAndPrivateKeyCannotBeExported() throws Exception {
        SecureNodeStore store = new SecureNodeStore(InstrumentationRegistry.getInstrumentation().getTargetContext());
        MeshIdentity first = new MeshIdentity(store), second = new MeshIdentity(store);
        assertEquals(first.nodeId, second.nodeId);
        assertEquals(MeshIdentity.pin(first.certificate), MeshIdentity.pin(second.certificate));
        assertNull(first.keys.getKey(MeshIdentity.ALIAS, null).getEncoded());
    }
    @Test public void strictFramesRejectDuplicatesAndUnboundedStructures() throws Exception {
        String[] values = {"{\"version\":1,\"version\":2}", "{\"x\":NaN}", "{\"x\":[[[[[[[[[[[[[[0]]]]]]]]]]]]]]}", "{\"x\":01}"};
        for (String text : values) {
            boolean rejected = false;
            try { MeshJson.parse(text.getBytes(StandardCharsets.UTF_8)); } catch (Exception expected) { rejected = true; }
            assertTrue(text, rejected);
        }
        assertEquals(5, MeshJson.parse("{\"x\":5}".getBytes(StandardCharsets.UTF_8)).getInt("x"));
    }
    @Test public void privateInboxTransferHasActualHashProofAndRejectsTraversal() throws Exception {
        android.content.Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        MeshNode node = new MeshNode(context, new SecureNodeStore(context));
        String key = UUID.randomUUID().toString().replace("-", ""), name = "qa-" + key + ".txt";
        byte[] data = "owned mesh test bytes".getBytes(StandardCharsets.UTF_8);
        String sha = MeshIdentity.hex(MessageDigest.getInstance("SHA-256").digest(data));
        try {
            JSONObject begin = new JSONObject().put("op", "begin").put("transfer_id", key).put("name", name).put("size", data.length).put("sha256", sha);
            assertFalse(node.file(begin, "qa-peer").getBoolean("complete"));
            node.file(new JSONObject().put("op", "chunk").put("transfer_id", key).put("offset", 0).put("data", android.util.Base64.encodeToString(data, android.util.Base64.NO_WRAP)), "qa-peer");
            JSONObject proof = node.file(new JSONObject().put("op", "finish").put("transfer_id", key), "qa-peer");
            assertTrue(proof.getBoolean("complete")); assertEquals(sha, proof.getString("sha256"));
            boolean rejected = false;
            try { node.file(begin.put("transfer_id", UUID.randomUUID().toString().replace("-", "")).put("name", "../outside.txt"), "qa-peer"); }
            catch (SecurityException expected) { rejected = true; }
            assertTrue(rejected);
        } finally {
            new java.io.File(node.inbox, name).delete();
            new java.io.File(node.inbox, "." + key + ".partial").delete();
            new java.io.File(node.inbox, "." + key + ".json").delete();
        }
    }
}
