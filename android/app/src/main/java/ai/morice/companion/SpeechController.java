package ai.morice.companion;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.function.Consumer;

final class SpeechController implements RecognitionListener, TextToSpeech.OnInitListener {
    static final int MICROPHONE_REQUEST = 4201;
    private final Activity activity;
    private final Consumer<String> transcriptCallback;
    private final Consumer<String> statusCallback;
    private final SecureNodeStore store;
    private final ExecutorService audioExecutor = Executors.newSingleThreadExecutor();
    private SpeechRecognizer recognizer;
    private TextToSpeech fallbackTts;
    private AudioTrack audioTrack;
    private Future<?> audioJob;
    private boolean voiceSession;

    SpeechController(Activity activity, SecureNodeStore store, Consumer<String> transcriptCallback, Consumer<String> statusCallback) {
        this.activity = activity;
        this.store = store;
        this.transcriptCallback = transcriptCallback;
        this.statusCallback = statusCallback;
        fallbackTts = new TextToSpeech(activity, this);
    }

    void setVoiceSession(boolean enabled) {
        voiceSession = enabled;
        if (enabled) listen();
        else stopAll();
    }

    boolean isVoiceSession() {
        return voiceSession;
    }

    void listen() {
        if (!voiceSession) return;
        if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            activity.requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, MICROPHONE_REQUEST);
            return;
        }
        interruptSpeech();
        if (!SpeechRecognizer.isRecognitionAvailable(activity)) {
            statusCallback.accept("Speech recognition is unavailable on this phone.");
            return;
        }
        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(activity);
            recognizer.setRecognitionListener(this);
        }
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault().toLanguageTag());
        recognizer.startListening(intent);
        statusCallback.accept("Listening…");
    }

    void speak(String text) {
        if (!voiceSession || text == null || text.trim().isEmpty()) return;
        interruptSpeech();
        String apiKey = "";
        String voiceId = "";
        try {
            apiKey = store.secret("elevenlabs.api-key");
            voiceId = store.secret("elevenlabs.voice-id");
        } catch (Exception ignored) {}
        if (!apiKey.isEmpty() && !voiceId.isEmpty()) {
            final String key = apiKey;
            final String voice = voiceId;
            audioJob = audioExecutor.submit(() -> streamElevenLabs(text, key, voice));
        } else {
            fallbackTts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "morice-response");
        }
    }

    void interruptSpeech() {
        if (audioJob != null) audioJob.cancel(true);
        audioJob = null;
        if (audioTrack != null) {
            try { audioTrack.pause(); audioTrack.flush(); audioTrack.stop(); } catch (IllegalStateException ignored) {}
            audioTrack.release();
            audioTrack = null;
        }
        if (fallbackTts != null) fallbackTts.stop();
    }

    private void streamElevenLabs(String text, String apiKey, String voiceId) {
        HttpURLConnection connection = null;
        try {
            String encodedVoice = URLEncoder.encode(voiceId, StandardCharsets.UTF_8.name());
            URL url = new URL("https://api.elevenlabs.io/v1/text-to-speech/" + encodedVoice + "/stream?output_format=pcm_24000");
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(12_000);
            connection.setReadTimeout(60_000);
            connection.setRequestMethod("POST");
            connection.setRequestProperty("xi-api-key", apiKey);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setDoOutput(true);
            JSONObject request = new JSONObject();
            request.put("text", text);
            request.put("model_id", "eleven_flash_v2_5");
            try (OutputStream output = connection.getOutputStream()) {
                output.write(request.toString().getBytes(StandardCharsets.UTF_8));
            }
            if (connection.getResponseCode() < 200 || connection.getResponseCode() >= 300) {
                throw new IllegalStateException("ElevenLabs returned " + connection.getResponseCode());
            }
            int bufferSize = Math.max(
                    AudioTrack.getMinBufferSize(24_000, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT),
                    24_000
            );
            AudioTrack track = new AudioTrack.Builder()
                    .setAudioAttributes(new AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ASSISTANT)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                            .build())
                    .setAudioFormat(new AudioFormat.Builder()
                            .setSampleRate(24_000)
                            .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                            .build())
                    .setBufferSizeInBytes(bufferSize)
                    .setTransferMode(AudioTrack.MODE_STREAM)
                    .build();
            audioTrack = track;
            track.play();
            byte[] buffer = new byte[8_192];
            try (BufferedInputStream input = new BufferedInputStream(connection.getInputStream())) {
                int count;
                while (!Thread.currentThread().isInterrupted() && (count = input.read(buffer)) >= 0) {
                    if (count > 0) track.write(buffer, 0, count, AudioTrack.WRITE_BLOCKING);
                }
            }
        } catch (Exception error) {
            activity.runOnUiThread(() -> {
                statusCallback.accept("Online voice failed; using Android speech.");
                if (voiceSession) fallbackTts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "morice-fallback");
            });
        } finally {
            if (connection != null) connection.disconnect();
            AudioTrack track = audioTrack;
            audioTrack = null;
            if (track != null) {
                try { track.stop(); } catch (IllegalStateException ignored) {}
                track.release();
            }
            if (voiceSession) activity.runOnUiThread(this::listen);
        }
    }

    private void stopAll() {
        if (recognizer != null) recognizer.cancel();
        interruptSpeech();
        statusCallback.accept("Voice off");
    }

    void destroy() {
        voiceSession = false;
        stopAll();
        if (recognizer != null) recognizer.destroy();
        recognizer = null;
        if (fallbackTts != null) fallbackTts.shutdown();
        fallbackTts = null;
        audioExecutor.shutdownNow();
    }

    @Override public void onInit(int status) {
        if (status == TextToSpeech.SUCCESS && fallbackTts != null) fallbackTts.setLanguage(Locale.getDefault());
    }
    @Override public void onReadyForSpeech(Bundle params) { statusCallback.accept("Listening…"); }
    @Override public void onBeginningOfSpeech() { interruptSpeech(); }
    @Override public void onRmsChanged(float rmsdB) {}
    @Override public void onBufferReceived(byte[] buffer) {}
    @Override public void onEndOfSpeech() { statusCallback.accept("Understanding…"); }
    @Override public void onError(int error) {
        if (voiceSession) activity.getWindow().getDecorView().postDelayed(this::listen, error == SpeechRecognizer.ERROR_NO_MATCH ? 250 : 700);
    }
    @Override public void onResults(Bundle results) {
        ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        if (matches != null && !matches.isEmpty()) transcriptCallback.accept(matches.get(0));
        else if (voiceSession) listen();
    }
    @Override public void onPartialResults(Bundle partialResults) {
        ArrayList<String> matches = partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        if (matches != null && !matches.isEmpty()) statusCallback.accept(matches.get(0));
    }
    @Override public void onEvent(int eventType, Bundle params) {}
}
