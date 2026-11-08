package com.safesignal.screener;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.app.role.RoleManager;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** One screen: call screening on/off, and the API address the bank-code listener reports to. */
public class MainActivity extends Activity {
    private static final int REQ_ROLE = 1;
    private static final String PREFS = "safe_signal";
    private TextView status;

    /** The laptop running the Safe Signal API, e.g. http://192.168.1.20:8000 (no trailing slash). */
    static String apiUrl(Context c) {
        String saved = c.getSharedPreferences(PREFS, MODE_PRIVATE).getString("api_url", null);
        String url = saved != null ? saved : BuildConfig.PHONE_API_URL;
        return url.trim().replaceAll("/+$", "");
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ScamScreeningService.ensureChannel(getSystemService(NotificationManager.class));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(48, 96, 48, 48);

        TextView title = new TextView(this);
        title.setText("Safe Signal Screener");
        title.setTextSize(24);
        root.addView(title);

        status = new TextView(this);
        status.setTextSize(16);
        status.setPadding(0, 48, 0, 48);
        root.addView(status);

        Button enable = new Button(this);
        enable.setText("Turn on call screening");
        enable.setOnClickListener(v -> requestRole());
        root.addView(enable);

        Button test = new Button(this);
        test.setText("Show a test alert");
        test.setOnClickListener(v -> testAlert());
        root.addView(test);

        TextView apiLabel = new TextView(this);
        apiLabel.setText("Bank-code listener: Safe Signal API address");
        apiLabel.setPadding(0, 64, 0, 8);
        root.addView(apiLabel);

        EditText api = new EditText(this);
        api.setSingleLine(true);
        api.setHint("http://192.168.1.20:8000");
        api.setText(apiUrl(this));
        root.addView(api);

        Button save = new Button(this);
        save.setText("Save API address");
        save.setOnClickListener(v -> {
            getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                    .putString("api_url", api.getText().toString().trim()).apply();
            refresh();
        });
        root.addView(save);

        setContentView(root);

        java.util.List<String> need = new java.util.ArrayList<>();
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            need.add(Manifest.permission.POST_NOTIFICATIONS);
        }
        if (checkSelfPermission(Manifest.permission.RECEIVE_SMS) != PackageManager.PERMISSION_GRANTED) {
            need.add(Manifest.permission.RECEIVE_SMS);
        }
        if (!need.isEmpty()) requestPermissions(need.toArray(new String[0]), 2);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    private void refresh() {
        RoleManager rm = getSystemService(RoleManager.class);
        boolean on = rm.isRoleHeld(RoleManager.ROLE_CALL_SCREENING);
        int count = ScamScreeningService.scamNumbers().size();
        boolean sms = checkSelfPermission(Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED;
        String api = apiUrl(this);
        status.setText((on ? "ON: checking incoming calls" : "OFF: tap the button below")
                + "\nNumbers on the scam list: " + count
                + "\nBank-code listener: "
                + (!sms ? "OFF (allow SMS)" : api.isEmpty() ? "OFF (set the API address)" : "ON -> " + api));
    }

    private void requestRole() {
        RoleManager rm = getSystemService(RoleManager.class);
        if (!rm.isRoleHeld(RoleManager.ROLE_CALL_SCREENING)) {
            startActivityForResult(rm.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING), REQ_ROLE);
        }
    }

    private void testAlert() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.notify(2, new android.app.Notification.Builder(this, ScamScreeningService.CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_alert)
                .setContentTitle("Scam Likely (test)")
                .setContentText("This is what a known scam call looks like")
                .setAutoCancel(true)
                .build());
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, android.content.Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        refresh();
    }
}
