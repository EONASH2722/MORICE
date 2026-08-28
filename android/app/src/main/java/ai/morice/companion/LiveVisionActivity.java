package ai.morice.companion;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.media.Image;
import android.media.ImageReader;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Base64;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class LiveVisionActivity extends Activity {
    private static final int CAMERA_PERMISSION = 4301;
    private TextureView preview;
    private TextView overlay;
    private EditText prompt;
    private CameraDevice camera;
    private CameraCaptureSession session;
    private ImageReader reader;
    private HandlerThread cameraThread;
    private Handler cameraHandler;
    private String selectedCameraId = "";
    private boolean preferFront;
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private SecureNodeStore store;
    private NodeClient client;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        store = new SecureNodeStore(this);
        try {
            client = new NodeClient(store);
        } catch (Exception error) {
            finishWithError("Secure node identity unavailable: " + safe(error));
            return;
        }
        buildUi();
    }

    private void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        preview = new TextureView(this);
        preview.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
            @Override public void onSurfaceTextureAvailable(SurfaceTexture surface, int width, int height) { openCamera(); }
            @Override public void onSurfaceTextureSizeChanged(SurfaceTexture surface, int width, int height) {}
            @Override public boolean onSurfaceTextureDestroyed(SurfaceTexture surface) { return true; }
            @Override public void onSurfaceTextureUpdated(SurfaceTexture surface) {}
        });
        root.addView(preview, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout controls = new LinearLayout(this);
        controls.setOrientation(LinearLayout.VERTICAL);
        controls.setPadding(dp(14), dp(14), dp(14), dp(14));
        controls.setBackgroundColor(Color.argb(205, 8, 16, 25));
        prompt = new EditText(this);
        prompt.setText("What am I looking at?");
        prompt.setTextColor(Color.WHITE);
        prompt.setHintTextColor(Color.LTGRAY);
        prompt.setSingleLine(false);
        LinearLayout buttons = new LinearLayout(this);
        Button close = button("Close", value -> finish());
        Button switchCamera = button("Switch", value -> switchCamera());
        Button analyze = button("Analyze frame", value -> captureForAnalysis());
        buttons.addView(close, weighted());
        buttons.addView(switchCamera, weighted());
        buttons.addView(analyze, weighted());
        controls.addView(prompt, new LinearLayout.LayoutParams(-1, -2));
        controls.addView(buttons, new LinearLayout.LayoutParams(-1, -2));
        FrameLayout.LayoutParams bottom = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        root.addView(controls, bottom);

        overlay = new TextView(this);
        overlay.setText("CAMERA ACTIVE • frames stay on device until you tap Analyze");
        overlay.setTextColor(Color.WHITE);
        overlay.setTextSize(14);
        overlay.setPadding(dp(12), dp(8), dp(12), dp(8));
        overlay.setBackgroundColor(Color.argb(210, 82, 56, 160));
        FrameLayout.LayoutParams top = new FrameLayout.LayoutParams(-1, -2, Gravity.TOP);
        top.setMargins(dp(10), dp(10), dp(10), 0);
        root.addView(overlay, top);
        setContentView(root);
    }

    private void openCamera() {
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, CAMERA_PERMISSION);
            return;
        }
        startCameraThread();
        CameraManager manager = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
        try {
            selectedCameraId = chooseCamera(manager, preferFront);
            if (selectedCameraId.isEmpty()) throw new CameraAccessException(CameraAccessException.CAMERA_ERROR, "No camera is available.");
            manager.openCamera(selectedCameraId, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice value) { camera = value; createSession(); }
                @Override public void onDisconnected(CameraDevice value) { value.close(); camera = null; show("Camera disconnected."); }
                @Override public void onError(CameraDevice value, int error) { value.close(); camera = null; show("Camera error " + error + "."); }
            }, cameraHandler);
        } catch (Exception error) {
            show("Camera unavailable: " + safe(error));
        }
    }

    private String chooseCamera(CameraManager manager, boolean front) throws CameraAccessException {
        String fallback = "";
        int desired = front ? CameraCharacteristics.LENS_FACING_FRONT : CameraCharacteristics.LENS_FACING_BACK;
        for (String id : manager.getCameraIdList()) {
            if (fallback.isEmpty()) fallback = id;
            Integer facing = manager.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING);
            if (facing != null && facing == desired) return id;
        }
        return fallback;
    }

    private void createSession() {
        if (camera == null || !preview.isAvailable()) return;
        try {
            reader = ImageReader.newInstance(1280, 720, android.graphics.ImageFormat.JPEG, 2);
            reader.setOnImageAvailableListener(this::onImage, cameraHandler);
            SurfaceTexture texture = preview.getSurfaceTexture();
            texture.setDefaultBufferSize(1280, 720);
            Surface previewSurface = new Surface(texture);
            camera.createCaptureSession(Arrays.asList(previewSurface, reader.getSurface()), new CameraCaptureSession.StateCallback() {
                @Override public void onConfigured(CameraCaptureSession value) {
                    session = value;
                    try {
                        CaptureRequest.Builder request = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
                        request.addTarget(previewSurface);
                        request.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE);
                        value.setRepeatingRequest(request.build(), null, cameraHandler);
                    } catch (CameraAccessException error) {
                        show("Preview failed: " + safe(error));
                    }
                }
                @Override public void onConfigureFailed(CameraCaptureSession value) { show("Camera session configuration failed."); }
            }, cameraHandler);
        } catch (CameraAccessException error) {
            show("Camera session failed: " + safe(error));
        }
    }

    private void captureForAnalysis() {
        if (camera == null || session == null || reader == null) {
            show("Camera isn't ready yet.");
            return;
        }
        show("CAPTURING • one JPEG will be sent encrypted to your paired desktop");
        try {
            CaptureRequest.Builder request = camera.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE);
            request.addTarget(reader.getSurface());
            request.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE);
            session.capture(request.build(), null, cameraHandler);
        } catch (CameraAccessException error) {
            show("Capture failed: " + safe(error));
        }
    }

    private void onImage(ImageReader source) {
        try (Image image = source.acquireLatestImage()) {
            if (image == null) return;
            ByteBuffer buffer = image.getPlanes()[0].getBuffer();
            byte[] jpeg = new byte[buffer.remaining()];
            buffer.get(jpeg);
            sendForAnalysis(jpeg, prompt.getText().toString().trim());
        }
    }

    private void sendForAnalysis(byte[] jpeg, String question) {
        network.execute(() -> {
            try {
                List<SecureNodeStore.Peer> peers = store.peers();
                if (peers.isEmpty()) throw new IllegalStateException("Pair a MORICE Desktop first.");
                JSONObject arguments = new JSONObject();
                arguments.put("jpegBase64", Base64.encodeToString(jpeg, Base64.NO_WRAP));
                arguments.put("prompt", question.isEmpty() ? "Describe what is visible." : question);
                MoriceProtocol.Message response = client.task(peers.get(0), "vision.analyze", arguments, 150_000);
                JSONObject result = response.payload.optJSONObject("result");
                String summary = result == null ? "No visual result was returned." : result.optString("summary", result.optString("message", "No visual result was returned."));
                show("MORICE • " + summary);
            } catch (Exception error) {
                show("Vision unavailable: " + safe(error));
            }
        });
    }

    private void switchCamera() {
        preferFront = !preferFront;
        closeCamera();
        openCamera();
    }

    private void show(String value) { runOnUiThread(() -> overlay.setText(value)); }

    private Button button(String text, android.view.View.OnClickListener listener) {
        Button value = new Button(this);
        value.setText(text);
        value.setOnClickListener(listener);
        return value;
    }

    private LinearLayout.LayoutParams weighted() { return new LinearLayout.LayoutParams(0, -2, 1); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void startCameraThread() {
        if (cameraThread != null) return;
        cameraThread = new HandlerThread("morice-camera");
        cameraThread.start();
        cameraHandler = new Handler(cameraThread.getLooper());
    }

    private void closeCamera() {
        if (session != null) session.close();
        session = null;
        if (camera != null) camera.close();
        camera = null;
        if (reader != null) reader.close();
        reader = null;
    }

    private void stopCameraThread() {
        HandlerThread value = cameraThread;
        cameraThread = null;
        cameraHandler = null;
        if (value != null) value.quitSafely();
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == CAMERA_PERMISSION && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) openCamera();
        else if (requestCode == CAMERA_PERMISSION) show("Camera permission denied. Live Vision remains off.");
    }

    private void finishWithError(String value) {
        TextView message = new TextView(this);
        message.setText(value);
        message.setTextColor(Color.WHITE);
        message.setTextSize(17);
        message.setPadding(dp(22), dp(22), dp(22), dp(22));
        message.setBackgroundColor(Color.rgb(8, 16, 25));
        setContentView(message);
    }

    private static String safe(Exception error) {
        String message = error.getMessage();
        return message == null || message.isEmpty() ? error.getClass().getSimpleName() : message;
    }

    @Override protected void onResume() { super.onResume(); if (preview != null && preview.isAvailable()) openCamera(); }
    @Override protected void onPause() { closeCamera(); stopCameraThread(); super.onPause(); }
    @Override protected void onDestroy() { network.shutdownNow(); super.onDestroy(); }
}
