package ai.morice.companion;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.json.JSONObject;

import java.security.KeyPair;
import java.util.Arrays;

import org.junit.Test;
import org.junit.runner.RunWith;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

@RunWith(AndroidJUnit4.class)
public final class ProtocolInstrumentedTest {
    @Test
    public void testIdentityAndSecureEnvelopeRoundTrip() throws Exception {
        KeyPair localKeys = MoriceProtocol.generateEcKeyPair();
        MoriceProtocol.Identity identity = new MoriceProtocol.Identity(localKeys.getPrivate(), localKeys.getPublic());
        assertEquals(65, MoriceProtocol.unb64(identity.publicText()).length);
        assertTrue(identity.fingerprint().contains(":"));

        byte[] key = MoriceProtocol.randomBytes(32);
        JSONObject payload = new JSONObject();
        payload.put("capability", "device.status");
        MoriceProtocol.Message request = new MoriceProtocol.Message("TASK_REQUEST", "phone", "desktop", payload);
        JSONObject sealed = MoriceProtocol.seal(request, key);
        MoriceProtocol.Message opened = MoriceProtocol.open(sealed, key, "desktop", "phone");
        assertEquals(request.messageId, opened.messageId);
        assertEquals("device.status", opened.payload.getString("capability"));
    }

    @Test
    public void testKeystoreIdentityAndPeerSurviveReload() throws Exception {
        SecureNodeStore first = new SecureNodeStore(InstrumentationRegistry.getInstrumentation().getTargetContext());
        MoriceProtocol.Identity identity = first.identity();
        String publicKey = identity.publicText();
        first.putSecret("test-secret", "secret-value");

        MoriceProtocol.Descriptor desktop = new MoriceProtocol.Descriptor(
                "desktop-test", "Desktop Test", "windows",
                Arrays.asList("system.status", "media.control"), "test"
        );
        first.putPeer(new SecureNodeStore.Peer(
                desktop, "127.0.0.1", 47651, MoriceProtocol.randomBytes(32),
                Arrays.asList("device.status"), Arrays.asList("system.status"),
                System.currentTimeMillis()
        ));

        SecureNodeStore second = new SecureNodeStore(InstrumentationRegistry.getInstrumentation().getTargetContext());
        assertEquals(publicKey, second.identity().publicText());
        assertEquals("secret-value", second.secret("test-secret"));
        assertNotNull(second.peer("desktop-test"));
        second.revoke("desktop-test");
        second.putSecret("test-secret", "");
    }
}
