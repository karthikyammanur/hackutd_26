package com.safesignal.screener;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.provider.Telephony;
import android.telephony.SmsMessage;
import android.util.Log;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

/**
 * Hears every incoming text. If it looks like a one-time code, tells the Safe Signal API what kind of sender it
 * came from and which bank it named: POST {API}/live/sms {"sender_type", "org"}. The API decides whether a call is
 * live; a code with no call running is ignored there.
 *
 * The code and the message text never leave the phone and are never logged.
 */
public class OtpReceiver extends BroadcastReceiver {
    private static final String TAG = "SafeSignalOtp";

    private static final Pattern CODE = Pattern.compile("(?<!\\d)\\d{4,8}(?!\\d)");
    private static final Pattern OTP_WORDS = Pattern.compile(
            "\\b(code|passcode|verification|verify|one[- ]time|otp|security code|authenticat\\w*|log ?in|sign ?in)\\b",
            Pattern.CASE_INSENSITIVE);

    /** Bank names to look for in the text, as the org Safe Signal reports. First match wins. */
    private static final String[][] BANKS = {
            {"lone star bank", "Lone Star Bank"},
            {"chase", "Chase"},
            {"bank of america", "Bank of America"},
            {"bofa", "Bank of America"},
            {"wells fargo", "Wells Fargo"},
            {"citi", "Citi"},
            {"capital one", "Capital One"},
            {"u.s. bank", "U.S. Bank"},
            {"us bank", "U.S. Bank"},
            {"pnc", "PNC"},
            {"truist", "Truist"},
            {"td bank", "TD Bank"},
            {"discover", "Discover"},
            {"american express", "American Express"},
            {"amex", "American Express"},
            {"usaa", "USAA"},
            {"navy federal", "Navy Federal"},
            {"ally", "Ally"},
            {"schwab", "Schwab"},
            {"fidelity", "Fidelity"},
            {"paypal", "PayPal"},
            {"venmo", "Venmo"},
            {"zelle", "Zelle"},
    };

    static boolean looksLikeOtp(String body) {
        return CODE.matcher(body).find() && OTP_WORDS.matcher(body).find();
    }

    static String bankIn(String body) {
        String lower = body.toLowerCase();
        for (String[] b : BANKS) {
            if (Pattern.compile("\\b" + Pattern.quote(b[0]) + "\\b").matcher(lower).find()) return b[1];
        }
        return null;
    }

    /** US short codes are 5 or 6 digits; anything else (a full phone number, an email) is a long code. */
    static String senderType(String sender, String org) {
        String digits = sender == null ? "" : sender.replaceAll("[^0-9]", "");
        boolean shortcode = digits.length() >= 5 && digits.length() <= 6 && digits.equals(sender.trim());
        if (!shortcode) return "longcode";
        return org != null ? "bank_shortcode" : "other_shortcode";
    }

    static String json(String senderType, String org) {
        String o = org == null ? "null" : "\"" + org.replace("\"", "") + "\"";
        return "{\"sender_type\":\"" + senderType + "\",\"org\":" + o + "}";
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Telephony.Sms.Intents.SMS_RECEIVED_ACTION.equals(intent.getAction())) return;
        SmsMessage[] parts = Telephony.Sms.Intents.getMessagesFromIntent(intent);
        if (parts == null || parts.length == 0) return;
        String sender = parts[0].getDisplayOriginatingAddress();
        StringBuilder sb = new StringBuilder();
        for (SmsMessage p : parts) sb.append(p.getDisplayMessageBody());
        String body = sb.toString();
        if (!looksLikeOtp(body)) return;

        String org = bankIn(body);
        String type = senderType(sender, org);
        String api = MainActivity.apiUrl(context);
        if (api.isEmpty()) {
            Log.w(TAG, "one-time code seen but no API URL set in the app");
            return;
        }
        Log.i(TAG, "one-time code seen: " + type + (org != null ? " " + org : "") + "; telling the API");

        PendingResult pending = goAsync();  // network is not allowed on the receiver's main thread
        new Thread(() -> {
            try {
                post(api + "/live/sms", json(type, org));
            } finally {
                pending.finish();
            }
        }).start();
    }

    private static void post(String url, String payload) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(url).openConnection();
            c.setRequestMethod("POST");
            c.setConnectTimeout(4000);
            c.setReadTimeout(4000);
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            try (OutputStream out = c.getOutputStream()) {
                out.write(payload.getBytes(StandardCharsets.UTF_8));
            }
            Log.i(TAG, "API answered " + c.getResponseCode());
        } catch (Exception e) {
            Log.w(TAG, "could not reach the API: " + e.getClass().getSimpleName());
        } finally {
            if (c != null) c.disconnect();
        }
    }
}
