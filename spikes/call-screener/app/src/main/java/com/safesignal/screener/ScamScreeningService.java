package com.safesignal.screener;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.net.Uri;
import android.telecom.Call;
import android.telecom.CallScreeningService;
import android.util.Log;

import java.util.HashSet;
import java.util.Set;

/**
 * Android calls this for every incoming call from a number that is NOT in the phone's contacts.
 * We compare the number to the scam list and, on a match, show a "Scam Likely" alert.
 * The call is always allowed to ring: Safe Signal never blocks or ends a call.
 */
public class ScamScreeningService extends CallScreeningService {
    static final String CHANNEL_ID = "scam_alerts";
    private static final String TAG = "SafeSignalScreener";

    /** Digits only, without a leading US "1", so +1 614-401-1536 and 6144011536 match. */
    static String normalize(String number) {
        if (number == null) return "";
        String digits = number.replaceAll("[^0-9]", "");
        if (digits.length() == 11 && digits.startsWith("1")) digits = digits.substring(1);
        return digits;
    }

    static Set<String> scamNumbers() {
        Set<String> out = new HashSet<>();
        for (String n : BuildConfig.SCAM_NUMBERS.split(",")) {
            String d = normalize(n);
            if (!d.isEmpty()) out.add(d);
        }
        return out;
    }

    static String masked(String digits) {
        return digits.length() <= 4 ? "****" : "***" + digits.substring(digits.length() - 4);
    }

    @Override
    public void onScreenCall(Call.Details details) {
        // Always let the call through, whatever we find.
        respondToCall(details, new CallResponse.Builder().build());

        if (details.getCallDirection() != Call.Details.DIRECTION_INCOMING) return;
        Uri handle = details.getHandle();
        String digits = normalize(handle == null ? null : handle.getSchemeSpecificPart());
        boolean hit = scamNumbers().contains(digits);
        Log.i(TAG, "incoming " + masked(digits) + (hit ? " -> on scam list" : " -> not on list"));
        if (hit) showAlert(digits);
    }

    private void showAlert(String digits) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        ensureChannel(nm);
        String pretty = digits.length() == 10
                ? "(" + digits.substring(0, 3) + ") " + digits.substring(3, 6) + "-" + digits.substring(6)
                : digits;
        Notification n = new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_alert)
                .setContentTitle("Scam Likely")
                .setContentText(pretty + " is on a known scam list")
                .setCategory(Notification.CATEGORY_CALL)
                .setAutoCancel(true)
                .build();
        nm.notify(1, n);
    }

    static void ensureChannel(NotificationManager nm) {
        NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "Scam call alerts", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("Shown when an incoming call is from a known scam number");
        nm.createNotificationChannel(ch);
    }
}
