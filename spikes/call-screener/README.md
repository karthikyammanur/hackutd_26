# Call Screener (Android): the "before" scene

A small Android app for the demo's "before" call. When a call rings from a number on the scam list, it
shows a **"Scam Likely"** alert. This is what T-Mobile already does today for known scam numbers. Safe
Signal's own work starts on the calls this list misses. The call always rings: the app never blocks or
ends a call (R2).

The scam list is `DEMO_SCAM_NUMBER` in the repo's `.env` (comma-separated, E.164, teammates' own numbers
only, R10). It is baked into the APK at build time, so rebuild after changing it.

## Build

```
cd spikes/call-screener
export JAVA_HOME="/c/Program Files/Android/Android Studio/jbr"   # any JDK 17+
./gradlew assembleDebug
# -> app/build/outputs/apk/debug/app-debug.apk
```

`local.properties` (not committed) needs `sdk.dir=<path to Android SDK>`.

## Install on the receiving teammate's phone (Android 10+)

1. Get the APK onto the phone. Either plug in with USB debugging on and run
   `adb install -r app/build/outputs/apk/debug/app-debug.apk`, or send the APK file to the phone and open
   it (allow "install unknown apps" when asked).
2. Open **Safe Signal Screener** and allow notifications.
3. Tap **Turn on call screening** and pick this app. On Samsung phones this is
   Settings > Apps > Choose default apps > Caller ID & spam app. Turning this on switches off the
   phone's built-in spam check, which is fine for the demo.
4. Tap **Show a test alert** to check that alerts appear.

## Before the demo

- **Delete the scam teammate from the receiving phone's contacts.** Android only asks the app about
  calls from numbers that are not saved contacts.
- Have the scam teammate call. The alert pops up while the phone rings. Calls from anyone else show
  nothing.
- Check that it's working: `adb logcat -s SafeSignalScreener` prints one line per incoming call, with
  the number masked.
