package ai.morice.companion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.media.AudioManager;
import android.os.BatteryManager;
import android.os.IBinder;
import android.view.KeyEvent;

import org.json.JSONObject;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class NodeConnectionService extends Service {
    static final int PHONE_NODE_PORT = 47661;
    private static final String CHANNEL = "morice-node-connectivity";
    private static final int NOTIFICATION_ID = 4601;
    private final ExecutorService workers = Executors.newCachedThreadPool();
    private volatile boolean running;
    private ServerSocket server;
    private SecureNodeStore store;
    private MoriceProtocol.Descriptor local;

    @Override public void onCreate() {
        super.onCreate();
        store = new SecureNodeStore(this);
        local = store.localDescriptor();
        createChannel();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIFICATION_ID, notification("Reachable by paired MORICE devices"));
        if (!running) {
            running = true;
            workers.execute(this::acceptLoop);
        }
        return START_STICKY;
    }

    private void acceptLoop() {
        try (ServerSocket value = new ServerSocket(PHONE_NODE_PORT)) {
            server = value;
            while (running) {
                Socket connection = value.accept();
                workers.execute(() -> handle(connection));
            }
        } catch (Exception error) {
            if (running) updateNotification("Connection stopped: " + safe(error));
        } finally {
            server = null;
        }
    }

    private void handle(Socket socket) {
        try (Socket connection = socket) {
            connection.setSoTimeout(60_000);
            DataInputStream input = new DataInputStream(connection.getInputStream());
            int size = input.readInt();
            if (size <= 0 || size > MoriceProtocol.MAX_FRAME_BYTES) throw new IllegalArgumentException("Invalid frame size.");
            byte[] bytes = new byte[size];
            input.readFully(bytes);
            JSONObject envelope = new JSONObject(new String(bytes, StandardCharsets.UTF_8));
            String senderId = envelope.getString("senderId");
            SecureNodeStore.Peer peer = store.peer(senderId);
            if (peer == null) throw new SecurityException("Unpaired node.");
            MoriceProtocol.Message request = MoriceProtocol.open(envelope, peer.sessionKey, local.deviceId, senderId);
            MoriceProtocol.Message response = dispatch(request, peer);
            byte[] responseBytes = MoriceProtocol.seal(response, peer.sessionKey).toString().getBytes(StandardCharsets.UTF_8);
            DataOutputStream output = new DataOutputStream(connection.getOutputStream());
            output.writeInt(responseBytes.length);
            output.write(responseBytes);
            output.flush();
        } catch (Exception ignored) {
            // Fail closed. Authentication errors are intentionally not reflected
            // to an unauthenticated network peer.
        }
    }

    private MoriceProtocol.Message dispatch(MoriceProtocol.Message request, SecureNodeStore.Peer peer) throws Exception {
        String capability = request.payload.optString("capability", "");
        JSONObject arguments = request.payload.optJSONObject("arguments");
        if (arguments == null) arguments = new JSONObject();
        if (!peer.localPermissions.contains(capability)) return error(request, "This desktop is not authorized for " + capability + ".");
        JSONObject result = new JSONObject();
        boolean verified = false;
        if ("device.status".equals(capability)) {
            BatteryManager battery = (BatteryManager) getSystemService(BATTERY_SERVICE);
            result.put("batteryPercent", battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY));
            result.put("charging", battery.isCharging());
            result.put("platform", "android");
            result.put("device", android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL);
            verified = true;
        } else if ("media.control".equals(capability)) {
            String action = arguments.optString("action", "");
            int keyCode;
            if ("pause".equals(action) || "resume".equals(action) || "play-pause".equals(action)) keyCode = KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE;
            else if ("next".equals(action)) keyCode = KeyEvent.KEYCODE_MEDIA_NEXT;
            else if ("previous".equals(action)) keyCode = KeyEvent.KEYCODE_MEDIA_PREVIOUS;
            else return error(request, "Unsupported Android media action.");
            AudioManager audio = (AudioManager) getSystemService(AUDIO_SERVICE);
            audio.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, keyCode));
            audio.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, keyCode));
            result.put("action", action);
            result.put("accepted", true);
            verified = true;
        } else if ("application.open".equals(capability)) {
            String packageName = arguments.optString("package", "");
            Intent launch = getPackageManager().getLaunchIntentForPackage(packageName);
            if (launch == null) return error(request, "Android package is not installed: " + packageName);
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(launch);
            result.put("package", packageName);
            result.put("launched", true);
            verified = true;
        } else if ("notification.receive".equals(capability)) {
            String title = arguments.optString("title", "MORICE Desktop");
            String text = arguments.optString("message", "Task update");
            NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            manager.notify((int) (System.currentTimeMillis() & 0x7fffffff), notification(title + ": " + text));
            result.put("shown", true);
            verified = true;
        } else {
            return error(request, "This Android capability requires the app in the foreground and explicit approval.");
        }
        JSONObject payload = new JSONObject();
        payload.put("capability", capability);
        payload.put("verified", verified);
        payload.put("result", result);
        return response(request, "TASK_RESULT", payload);
    }

    private MoriceProtocol.Message error(MoriceProtocol.Message request, String message) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("verified", false);
        payload.put("error", message);
        return response(request, "ERROR", payload);
    }

    private MoriceProtocol.Message response(MoriceProtocol.Message request, String type, JSONObject payload) {
        return new MoriceProtocol.Message(
                type, local.deviceId, request.senderId, payload,
                java.util.UUID.randomUUID().toString().replace("-", ""), request.taskId,
                System.currentTimeMillis() / 1000.0
        );
    }

    private void createChannel() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "MORICE device connection", NotificationManager.IMPORTANCE_LOW));
    }

    private Notification notification(String message) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL)
                .setSmallIcon(ai.morice.companion.R.drawable.ic_morice)
                .setContentTitle("MORICE Android node")
                .setContentText(message)
                .setContentIntent(pending)
                .setOngoing(true)
                .build();
    }

    private void updateNotification(String message) {
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(NOTIFICATION_ID, notification(message));
    }

    @Override public void onDestroy() {
        running = false;
        try { if (server != null) server.close(); } catch (Exception ignored) {}
        workers.shutdownNow();
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    private static String safe(Exception error) {
        String message = error.getMessage();
        return message == null || message.isEmpty() ? error.getClass().getSimpleName() : message;
    }
}
