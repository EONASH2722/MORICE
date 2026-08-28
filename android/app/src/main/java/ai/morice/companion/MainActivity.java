package ai.morice.companion;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private final ExecutorService tasks = Executors.newSingleThreadExecutor();
    private SecureNodeStore store;
    private NodeClient client;
    private SpeechController speech;
    private LinearLayout messages;
    private ScrollView conversation;
    private EditText input;
    private TextView status;
    private Button voiceButton;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        store = new SecureNodeStore(this);
        try {
            client = new NodeClient(store);
        } catch (Exception error) {
            showFatal("Secure identity could not be opened: " + safe(error));
            return;
        }
        speech = new SpeechController(this, store, this::submitVoice, value -> runOnUiThread(() -> status.setText(value)));
        buildUi();
        refreshStatus();
        handlePairIntent(getIntent());
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(12), dp(10), dp(12), dp(10));
        root.setBackgroundColor(Color.rgb(8, 16, 25));

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView brand = text("M  MORICE", 22, Color.WHITE);
        brand.setTypeface(null, Typeface.BOLD);
        status = text("Starting…", 13, Color.rgb(156, 176, 194));
        status.setGravity(Gravity.END);
        header.addView(brand, new LinearLayout.LayoutParams(0, -2, 1));
        header.addView(status, new LinearLayout.LayoutParams(0, -2, 1));

        LinearLayout actions = new LinearLayout(this);
        actions.setGravity(Gravity.CENTER);
        Button pair = action("Devices", view -> startActivityForResult(new Intent(this, PairDeviceActivity.class), 2201));
        voiceButton = action("Voice off", view -> toggleVoice());
        Button vision = action("Live Vision", view -> openVision());
        Button settings = action("Settings", view -> voiceSettings());
        actions.addView(pair, weighted());
        actions.addView(voiceButton, weighted());
        actions.addView(vision, weighted());
        actions.addView(settings, weighted());

        conversation = new ScrollView(this);
        conversation.setFillViewport(true);
        messages = new LinearLayout(this);
        messages.setOrientation(LinearLayout.VERTICAL);
        messages.setPadding(0, dp(8), 0, dp(8));
        conversation.addView(messages, new ScrollView.LayoutParams(-1, -2));

        LinearLayout composer = new LinearLayout(this);
        composer.setGravity(Gravity.BOTTOM);
        input = new EditText(this);
        input.setHint("Message MORICE…");
        input.setHintTextColor(Color.rgb(120, 145, 165));
        input.setTextColor(Color.WHITE);
        input.setMinLines(1);
        input.setMaxLines(4);
        input.setImeOptions(EditorInfo.IME_ACTION_SEND);
        input.setOnEditorActionListener((view, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                submitTyped();
                return true;
            }
            return false;
        });
        Button send = action("Send", view -> submitTyped());
        composer.addView(input, new LinearLayout.LayoutParams(0, -2, 1));
        composer.addView(send, new LinearLayout.LayoutParams(dp(82), -2));

        root.addView(header, new LinearLayout.LayoutParams(-1, -2));
        root.addView(actions, margins(-1, -2, 0, 8, 0, 6));
        root.addView(conversation, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(composer, new LinearLayout.LayoutParams(-1, -2));
        setContentView(root);
        addMessage(false, "Connected conversations, voice, vision, and device control—without desktop Project Mode.");
    }

    private void submitTyped() {
        String value = input.getText().toString().trim();
        if (value.isEmpty()) return;
        input.setText("");
        submit(value);
    }

    private void submitVoice(String value) {
        runOnUiThread(() -> submit(value));
    }

    private void submit(String value) {
        addMessage(true, value);
        status.setText("Routing…");
        tasks.execute(() -> {
            try {
                SecureNodeStore.Peer peer = primaryPeer();
                if (peer == null) throw new IllegalStateException("Pair a MORICE Desktop first.");
                RoutedTask routed = route(value);
                MoriceProtocol.Message response = client.task(peer, routed.capability, routed.arguments, routed.timeoutMs);
                String answer = present(routed.capability, response.payload.optJSONObject("result"), response.payload);
                runOnUiThread(() -> {
                    addMessage(false, answer);
                    status.setText(peer.descriptor.deviceName + " • encrypted");
                    speech.speak(answer);
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    String answer = "Not yet. " + safe(error);
                    addMessage(false, answer);
                    status.setText("Offline/local");
                    speech.speak(answer);
                });
            }
        });
    }

    private RoutedTask route(String text) throws Exception {
        String lower = text.toLowerCase(Locale.ROOT).trim();
        JSONObject arguments = new JSONObject();
        boolean pcReference = lower.contains(" pc") || lower.contains("computer") || lower.contains("desktop") || lower.contains("laptop");
        if ((lower.contains("battery") || lower.contains("ram") || lower.contains("system status")) && pcReference) {
            return new RoutedTask("system.status", arguments, 20_000);
        }
        if (lower.startsWith("open ") && pcReference) {
            String application = text.substring(5)
                    .replaceAll("(?i)\\s+on\\s+(my\\s+)?(pc|computer|desktop|laptop).*$", "")
                    .trim();
            arguments.put("application", application);
            return new RoutedTask("application.open", arguments, 25_000);
        }
        String mediaAction = null;
        if (lower.matches(".*\\b(pause|stop)\\b.*(music|song|media|pc).*")) mediaAction = "pause";
        else if (lower.matches(".*\\b(resume|continue|play)\\b.*(music|song|media|pc).*")) mediaAction = "resume";
        else if (lower.matches(".*\\b(next|skip)\\b.*")) mediaAction = "next";
        else if (lower.matches(".*\\b(previous|back)\\b.*(song|track|music).*")) mediaAction = "previous";
        if (mediaAction != null) {
            arguments.put("action", mediaAction);
            return new RoutedTask("media.control", arguments, 20_000);
        }
        if (lower.contains("build") && (lower.contains("status") || lower.contains("happened") || lower.contains("going"))) {
            return new RoutedTask("project.status", arguments, 20_000);
        }
        arguments.put("message", text);
        return new RoutedTask("chat.complete", arguments, 150_000);
    }

    private String present(String capability, JSONObject result, JSONObject envelope) {
        if (result == null) return envelope.optString("message", "Done.");
        if ("chat.complete".equals(capability)) return result.optString("message", "I didn't receive a response.");
        if ("system.status".equals(capability)) {
            double total = result.optDouble("memory_total_gb", 0);
            double available = result.optDouble("memory_available_gb", 0);
            String battery = result.isNull("battery_percent") ? "no battery reading" : result.optInt("battery_percent") + "% battery";
            return String.format(Locale.ROOT, "%s: %.1f GB RAM, %.1f GB available, %s.",
                    result.optString("hostname", "Desktop"), total, available, battery);
        }
        if ("application.open".equals(capability)) return result.optBoolean("running") ? "Opened " + result.optString("application") + "." : "The app did not become visible.";
        if ("media.control".equals(capability)) return envelope.optBoolean("verified") ? "Done." : "The media command wasn't verified.";
        if ("project.status".equals(capability)) return result.toString();
        return result.toString();
    }

    private void toggleVoice() {
        boolean enable = !speech.isVoiceSession();
        speech.setVoiceSession(enable);
        voiceButton.setText(enable ? "Voice on" : "Voice off");
    }

    private void openVision() {
        startActivity(new Intent(this, LiveVisionActivity.class));
    }

    private void voiceSettings() {
        LinearLayout content = new LinearLayout(this);
        content.setPadding(dp(18), 0, dp(18), 0);
        content.setOrientation(LinearLayout.VERTICAL);
        EditText key = new EditText(this);
        key.setHint("ElevenLabs API key (optional)");
        key.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        EditText voice = new EditText(this);
        voice.setHint("ElevenLabs voice ID");
        try {
            voice.setText(store.secret("elevenlabs.voice-id"));
        } catch (Exception ignored) {}
        content.addView(key);
        content.addView(voice);
        new AlertDialog.Builder(this)
                .setTitle("Voice output")
                .setMessage("When configured, MORICE streams ElevenLabs PCM audio. Otherwise Android's offline-capable TTS is used.")
                .setView(content)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Save", (dialog, which) -> {
                    try {
                        if (!key.getText().toString().trim().isEmpty()) store.putSecret("elevenlabs.api-key", key.getText().toString().trim());
                        store.putSecret("elevenlabs.voice-id", voice.getText().toString().trim());
                        status.setText("Voice settings saved securely.");
                    } catch (Exception error) {
                        status.setText("Voice settings failed: " + safe(error));
                    }
                }).show();
    }

    private SecureNodeStore.Peer primaryPeer() throws Exception {
        List<SecureNodeStore.Peer> peers = store.peers();
        return peers.isEmpty() ? null : peers.get(0);
    }

    private void refreshStatus() {
        tasks.execute(() -> {
            try {
                SecureNodeStore.Peer peer = primaryPeer();
                runOnUiThread(() -> status.setText(peer == null ? "Offline/local" : peer.descriptor.deviceName + " • paired"));
            } catch (Exception error) {
                runOnUiThread(() -> status.setText("Secure store unavailable"));
            }
        });
    }

    private void addMessage(boolean user, String value) {
        TextView view = text((user ? "YOU\n" : "MORICE\n") + value, 16, Color.WHITE);
        view.setPadding(dp(14), dp(11), dp(14), dp(11));
        view.setBackgroundColor(user ? Color.rgb(23, 50, 71) : Color.rgb(16, 29, 41));
        LinearLayout.LayoutParams params = margins(-1, -2, user ? 34 : 0, 6, user ? 0 : 34, 6);
        messages.addView(view, params);
        conversation.post(() -> conversation.fullScroll(View.FOCUS_DOWN));
    }

    private Button action(String title, View.OnClickListener listener) {
        Button value = new Button(this);
        value.setText(title);
        value.setTextSize(12);
        value.setOnClickListener(listener);
        return value;
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        return view;
    }

    private LinearLayout.LayoutParams weighted() { return new LinearLayout.LayoutParams(0, -2, 1); }
    private LinearLayout.LayoutParams margins(int width, int height, int left, int top, int right, int bottom) {
        LinearLayout.LayoutParams value = new LinearLayout.LayoutParams(width, height);
        value.setMargins(dp(left), dp(top), dp(right), dp(bottom));
        return value;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void handlePairIntent(Intent intent) {
        if (intent != null && intent.getData() != null && "morice".equals(intent.getScheme()) && "pair".equals(intent.getData().getHost())) {
            startActivityForResult(new Intent(this, PairDeviceActivity.class), 2201);
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == 2201) refreshStatus();
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == SpeechController.MICROPHONE_REQUEST && grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) speech.listen();
    }

    private void showFatal(String message) {
        TextView view = text(message, 17, Color.WHITE);
        view.setPadding(dp(22), dp(22), dp(22), dp(22));
        view.setBackgroundColor(Color.rgb(8, 16, 25));
        setContentView(view);
    }

    private static String safe(Exception error) {
        String message = error.getMessage();
        return message == null || message.isEmpty() ? error.getClass().getSimpleName() : message;
    }

    @Override protected void onDestroy() {
        if (speech != null) speech.destroy();
        tasks.shutdownNow();
        super.onDestroy();
    }

    private static final class RoutedTask {
        final String capability;
        final JSONObject arguments;
        final int timeoutMs;
        RoutedTask(String capability, JSONObject arguments, int timeoutMs) {
            this.capability = capability;
            this.arguments = arguments;
            this.timeoutMs = timeoutMs;
        }
    }
}
