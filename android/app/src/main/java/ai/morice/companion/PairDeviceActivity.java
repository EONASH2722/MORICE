package ai.morice.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Arrays;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class PairDeviceActivity extends Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EditText hostInput;
    private EditText portInput;
    private TextView status;
    private Button pairButton;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setTitle("Pair MORICE device");
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(22), dp(28), dp(22), dp(22));
        root.setBackgroundColor(Color.rgb(8, 16, 25));

        TextView title = text("Pair a MORICE Desktop", 24, Color.WHITE);
        TextView detail = text(
                "On the desktop, open Panel → Pair a device. Enter its LAN address here, then compare the six-digit code on both devices.",
                15, Color.rgb(156, 176, 194)
        );
        hostInput = input("Desktop IP address", InputType.TYPE_CLASS_PHONE);
        portInput = input("Port", InputType.TYPE_CLASS_NUMBER);
        portInput.setText(String.valueOf(MoriceProtocol.DEFAULT_PORT));
        pairButton = new Button(this);
        pairButton.setText("Connect securely");
        pairButton.setOnClickListener(view -> beginPairing());
        status = text("Pairing is authenticated and encrypted. Devices on Wi-Fi are not trusted automatically.", 14, Color.rgb(84, 230, 194));

        root.addView(title, params(-1, -2, 0, 0, 0, 12));
        root.addView(detail, params(-1, -2, 0, 0, 0, 18));
        root.addView(hostInput, params(-1, -2, 0, 0, 0, 10));
        root.addView(portInput, params(-1, -2, 0, 0, 0, 14));
        root.addView(pairButton, params(-1, -2, 0, 0, 0, 16));
        root.addView(status, params(-1, -2, 0, 0, 0, 0));
        setContentView(root);
    }

    private void beginPairing() {
        String host = hostInput.getText().toString().trim();
        int port;
        try {
            port = Integer.parseInt(portInput.getText().toString().trim());
        } catch (NumberFormatException error) {
            status.setText("Enter a valid port.");
            return;
        }
        if (host.isEmpty()) {
            status.setText("Enter the desktop's LAN IP address.");
            return;
        }
        pairButton.setEnabled(false);
        status.setText("Creating an authenticated pairing challenge…");
        final int selectedPort = port;
        executor.execute(() -> {
            try {
                SecureNodeStore store = new SecureNodeStore(this);
                NodeClient client = new NodeClient(store);
                NodeClient.PairingSession session = client.beginPairing(host, selectedPort);
                runOnUiThread(() -> showCode(client, session));
            } catch (Exception error) {
                runOnUiThread(() -> {
                    pairButton.setEnabled(true);
                    status.setText("Pairing failed: " + safe(error));
                });
            }
        });
    }

    private void showCode(NodeClient client, NodeClient.PairingSession session) {
        new AlertDialog.Builder(this)
                .setTitle("Does this code match?")
                .setMessage(session.verificationCode + "\n\nDesktop: " + session.peer.deviceName +
                        "\nOnly approve if the desktop shows the same code.")
                .setNegativeButton("Cancel", (dialog, which) -> {
                    pairButton.setEnabled(true);
                    status.setText("Pairing cancelled. No trust was stored.");
                })
                .setPositiveButton("Codes match", (dialog, which) -> confirm(client, session))
                .setCancelable(false)
                .show();
    }

    private void confirm(NodeClient client, NodeClient.PairingSession session) {
        status.setText("Saving device-scoped permissions…");
        executor.execute(() -> {
            try {
                SecureNodeStore.Peer peer = client.confirmPairing(
                        session,
                        Arrays.asList(
                                "system.status", "chat.complete", "vision.analyze", "application.open",
                                "media.control", "project.status", "notification.receive", "file.receive"
                        ),
                        Arrays.asList("device.status", "media.control", "application.open", "notification.receive")
                );
                runOnUiThread(() -> {
                    pairButton.setEnabled(true);
                    status.setText("Paired with " + peer.descriptor.deviceName + ". Keys are stored in Android Keystore.");
                    if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                        requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 4401);
                    }
                    startForegroundService(new Intent(this, NodeConnectionService.class));
                    setResult(RESULT_OK);
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    pairButton.setEnabled(true);
                    status.setText("Pairing was not completed: " + safe(error));
                });
            }
        });
    }

    private EditText input(String hint, int inputType) {
        EditText value = new EditText(this);
        value.setHint(hint);
        value.setHintTextColor(Color.rgb(120, 145, 165));
        value.setTextColor(Color.WHITE);
        value.setInputType(inputType);
        value.setSingleLine(true);
        return value;
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setGravity(Gravity.START);
        return view;
    }

    private LinearLayout.LayoutParams params(int width, int height, int left, int top, int right, int bottom) {
        LinearLayout.LayoutParams value = new LinearLayout.LayoutParams(width, height);
        value.setMargins(dp(left), dp(top), dp(right), dp(bottom));
        return value;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static String safe(Exception error) {
        String message = error.getMessage();
        return message == null || message.isEmpty() ? error.getClass().getSimpleName() : message;
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        executor.shutdownNow();
    }
}
