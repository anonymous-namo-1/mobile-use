package dev.mobileuse.agent;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.app.KeyguardManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Bitmap;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Base64;
import android.view.Display;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Mobile Use: lets the owner's AI agent (on their server, over Tailscale) see and drive
 * this phone. Shows a glowing blue border and a notification with a Stop button while active.
 * Risky actions wait on an approval card (slide to approve, or deny when the timer ends).
 * Password and PIN fields are refused and the approval flag does not unlock them.
 */
public class AgentService extends AccessibilityService {
    static AgentService instance;
    static final int GLOW_MS = 15000;
    static final String CH_ACTIVE = "active", CH_ASK = "ask", CH_READY = "ready";

    final Handler main = new Handler(Looper.getMainLooper());
    private Link link;
    private GlowView glow;
    private ApprovalOverlay approval;
    private PowerManager.WakeLock wake;
    private long lastCommand;
    volatile long stoppedUntil;
    private final List<AccessibilityNodeInfo> nodes = new ArrayList<>();
    static final AtomicReference<CountDownLatch> askLatch = new AtomicReference<>();
    static volatile String askAnswer;

    @Override protected void onServiceConnected() {
        instance = this;
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CH_ACTIVE, "Agent active", NotificationManager.IMPORTANCE_LOW));
        nm.createNotificationChannel(new NotificationChannel(CH_ASK, "Agent asks for approval", NotificationManager.IMPORTANCE_HIGH));
        nm.createNotificationChannel(new NotificationChannel(CH_READY, "Mobile Use ready", NotificationManager.IMPORTANCE_MIN));
        // A foreground service is not frozen by Samsung's battery saver, so the link stays up.
        startForeground(10, new Notification.Builder(this, CH_READY)
                .setSmallIcon(android.R.drawable.ic_menu_view)
                .setContentTitle("Mobile Use ready")
                .setContentText("Your AI agent can reach this phone. A blue glow shows when it's active.")
                .setOngoing(true).build(), android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        link = Link.ensure(this);  // one connection per phone, even if Android rebinds the service
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent e) { }
    @Override public void onInterrupt() { }

    @Override public void onDestroy() {
        if (link != null && instance == this) link.shutdown();
        main.post(() -> { hideApproval(); hideGlow(); });
        instance = null;
        super.onDestroy();
    }

    // ---------------- command dispatch (called from the Link thread) ----------------

    JSONObject handle(String cmd, JSONObject a) throws Exception {
        if (cmd.equals("ping")) return status();
        if (System.currentTimeMillis() < stoppedUntil)
            throw new Exception("stopped by the owner (Stop button on the phone); ask the owner to tap Resume");
        if (!cmd.equals("status")) touch();
        switch (cmd) {
            case "status": return status();
            case "look": {
                JSONObject r = tree();
                if (a.optBoolean("shot", true)) r.put("jpeg", screenshot(a.optInt("width", 540), a.optInt("quality", 55)));
                return r;
            }
            case "tree": return tree();
            case "screenshot": return new JSONObject().put("jpeg", screenshot(a.optInt("width", 540), a.optInt("quality", 55)));
            case "click": return click(a.getInt("i"), a.optBoolean("approved", false));
            case "long_click": {
                AccessibilityNodeInfo held = node(a.getInt("i"));
                if (held.isPassword())
                    throw new Exception("password field: never touched by the agent");
                return gesture(center(a.getInt("i")), center(a.getInt("i")), 800);
            }
            case "tap": return gesture(new int[]{a.getInt("x"), a.getInt("y")}, new int[]{a.getInt("x"), a.getInt("y")}, 60);
            case "long_tap": return gesture(new int[]{a.getInt("x"), a.getInt("y")}, new int[]{a.getInt("x"), a.getInt("y")}, 800);
            case "swipe": return gesture(new int[]{a.getInt("x1"), a.getInt("y1")}, new int[]{a.getInt("x2"), a.getInt("y2")}, a.optInt("ms", 300));
            case "set_text": return setText(a.optInt("i", -1), a.getString("text"), a.optBoolean("clear", true),
                    a.optBoolean("enter", false), a.optBoolean("approved", false));
            case "global": return global(a.getString("key"));
            case "open_app": return openApp(a.getString("package"));
            case "apps": return apps();
            case "wait_for": return waitFor(a.getString("text"), a.optInt("timeout", 15));
            case "find": return find(a.getString("text"), a.optInt("max_scrolls", 8));
            case "ask": return ask(a.getString("text"), a.optInt("timeout", 60),
                    a.optString("why", ""), a.optString("risk", ""), a.optString("title", ""));
            case "wake": return wakeUp();
            case "glow": if (!a.optBoolean("on", true)) { lastCommand = 0; main.post(this::hideGlow); } return status();
            default: throw new Exception("unknown command " + cmd);
        }
    }

    JSONObject status() throws Exception {
        PowerManager pm = getSystemService(PowerManager.class);
        KeyguardManager km = getSystemService(KeyguardManager.class);
        return new JSONObject()
                .put("model", android.os.Build.MODEL)
                .put("screen_on", pm.isInteractive())
                .put("locked", km.isKeyguardLocked())
                .put("stopped", System.currentTimeMillis() < stoppedUntil)
                .put("app", frontPackage());
    }

    String frontPackage() {
        AccessibilityNodeInfo r = getRootInActiveWindow();
        return r != null && r.getPackageName() != null ? r.getPackageName().toString() : "";
    }

    // ---------------- seeing ----------------

    JSONObject tree() throws Exception {
        nodes.clear();
        JSONArray out = new JSONArray();
        AccessibilityNodeInfo root = getRootInActiveWindow();
        boolean keyboard = false;
        for (AccessibilityWindowInfo w : getWindows()) {
            if (w.getType() == AccessibilityWindowInfo.TYPE_INPUT_METHOD) keyboard = true;
            // permission pop-ups and system dialogs on top of the app
            if (w.getType() == AccessibilityWindowInfo.TYPE_SYSTEM && w.isActive() && w.getRoot() != null) root = w.getRoot();
        }
        if (root != null) collect(root, out, 0);
        PowerManager pm = getSystemService(PowerManager.class);
        KeyguardManager km = getSystemService(KeyguardManager.class);
        Rect screen = new Rect();
        if (root != null) root.getBoundsInScreen(screen);
        return new JSONObject().put("app", root != null && root.getPackageName() != null ? root.getPackageName() : "")
                .put("keyboard", keyboard).put("locked", km.isKeyguardLocked()).put("screen_on", pm.isInteractive())
                .put("w", getResources().getDisplayMetrics().widthPixels)
                .put("h", getResources().getDisplayMetrics().heightPixels)
                .put("els", out);
    }

    private void collect(AccessibilityNodeInfo n, JSONArray out, int depth) throws Exception {
        if (n == null || depth > 60 || !n.isVisibleToUser()) return;
        Rect b = new Rect();
        n.getBoundsInScreen(b);
        String cls = n.getClassName() == null ? "" : n.getClassName().toString();
        boolean edit = n.isEditable() || cls.endsWith("EditText");
        boolean act = n.isClickable() || n.isLongClickable() || n.isCheckable();
        boolean scroll = n.isScrollable();
        String label = label(n);
        if (act && label.isEmpty()) label = childText(n, new StringBuilder(), 0).toString().trim();
        if ((act || edit || scroll || !label.isEmpty()) && b.width() > 6 && b.height() > 6) {
            JSONObject e = new JSONObject()
                    .put("kind", edit ? "field" : scroll ? "list" : act ? "button" : "text")
                    .put("label", label.length() > 90 ? label.substring(0, 90) : label)
                    .put("b", new JSONArray().put(b.left).put(b.top).put(b.right).put(b.bottom));
            String id = n.getViewIdResourceName();
            if (id != null && label.isEmpty()) e.put("id", id.substring(id.indexOf('/') + 1));
            if (n.isPassword()) e.put("password", true);
            if (n.isCheckable()) e.put("checked", n.isChecked());
            if (n.isSelected()) e.put("selected", true);
            if (!n.isEnabled()) e.put("disabled", true);
            e.put("i", nodes.size());
            nodes.add(n);
            out.put(e);
        }
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo c = n.getChild(i);
            if (c == null) continue;
            // plain text inside a button was already used as the button's label
            if (act && !c.isClickable() && !c.isEditable() && !c.isScrollable() && c.getChildCount() == 0) continue;
            collect(c, out, depth + 1);
        }
    }

    private static String label(AccessibilityNodeInfo n) {
        CharSequence t = n.getText();
        if (t == null || t.length() == 0) t = n.getContentDescription();
        if ((t == null || t.length() == 0) && n.isEditable()) t = n.getHintText();
        return t == null ? "" : t.toString().replace('\n', ' ').trim();
    }

    private static StringBuilder childText(AccessibilityNodeInfo n, StringBuilder sb, int depth) {
        if (depth > 6 || sb.length() > 90) return sb;
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo c = n.getChild(i);
            if (c == null) continue;
            String l = label(c);
            if (!l.isEmpty()) sb.append(sb.length() > 0 ? " " : "").append(l);
            childText(c, sb, depth + 1);
        }
        return sb;
    }

    String screenshot(int width, int quality) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Object> res = new AtomicReference<>();
        takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new TakeScreenshotCallback() {
            @Override public void onSuccess(ScreenshotResult s) { res.set(s); done.countDown(); }
            @Override public void onFailure(int code) { res.set("screenshot failed (" + code + "): the app may block screenshots"); done.countDown(); }
        });
        if (!done.await(5, TimeUnit.SECONDS)) throw new Exception("screenshot timed out");
        if (res.get() instanceof String) throw new Exception((String) res.get());
        ScreenshotResult s = (ScreenshotResult) res.get();
        Bitmap hw = Bitmap.wrapHardwareBuffer(s.getHardwareBuffer(), s.getColorSpace());
        Bitmap soft = hw.copy(Bitmap.Config.ARGB_8888, false);
        hw.recycle();
        s.getHardwareBuffer().close();
        int h = Math.round(soft.getHeight() * (width / (float) soft.getWidth()));
        Bitmap small = Bitmap.createScaledBitmap(soft, width, h, true);
        soft.recycle();
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        small.compress(Bitmap.CompressFormat.JPEG, quality, bos);
        small.recycle();
        return Base64.encodeToString(bos.toByteArray(), Base64.NO_WRAP);
    }

    // ---------------- acting ----------------

    private AccessibilityNodeInfo node(int i) throws Exception {
        if (i < 0 || i >= nodes.size()) throw new Exception("no element [" + i + "]; look again");
        AccessibilityNodeInfo n = nodes.get(i);
        if (!n.refresh()) throw new Exception("element [" + i + "] is gone; look again");
        return n;
    }

    private int[] center(int i) throws Exception {
        Rect b = new Rect();
        node(i).getBoundsInScreen(b);
        return new int[]{b.centerX(), b.centerY()};
    }

    JSONObject click(int i, boolean approved) throws Exception {
        AccessibilityNodeInfo n = node(i);
        if (n.isPassword()) throw new Exception("password field: never touched by the agent");
        if (n.isClickable() && n.performAction(AccessibilityNodeInfo.ACTION_CLICK))
            return new JSONObject().put("done", "click");
        int[] c = center(i);
        return gesture(c, c, 60);
    }

    JSONObject gesture(int[] from, int[] to, int ms) throws Exception {
        Path p = new Path();
        p.moveTo(from[0], from[1]);
        p.lineTo(to[0], to[1]);
        GestureDescription g = new GestureDescription.Builder()
                .addStroke(new GestureDescription.StrokeDescription(p, 0, Math.max(ms, 1))).build();
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Boolean> ok = new AtomicReference<>(false);
        main.post(() -> dispatchGesture(g, new GestureResultCallback() {
            @Override public void onCompleted(GestureDescription d) { ok.set(true); done.countDown(); }
            @Override public void onCancelled(GestureDescription d) { done.countDown(); }
        }, null));
        done.await(ms + 3000L, TimeUnit.MILLISECONDS);
        if (!ok.get()) throw new Exception("gesture was cancelled");
        return new JSONObject().put("done", "gesture");
    }

    JSONObject setText(int i, String text, boolean clear, boolean enter, boolean approved) throws Exception {
        AccessibilityNodeInfo n = i >= 0 ? node(i) : findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (n == null) throw new Exception("no text field focused; give the field number");
        if (n.isPassword()) throw new Exception("password field: never typed into by the agent");
        n.performAction(AccessibilityNodeInfo.ACTION_FOCUS);
        if (n.isClickable()) n.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        String now = n.getText() == null || n.isShowingHintText() ? "" : n.getText().toString();
        Bundle args = new Bundle();
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, clear ? text : now + text);
        if (!n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) throw new Exception("this field does not accept text");
        if (enter) {
            n.refresh();
            n.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.getId());
        }
        return new JSONObject().put("done", "text");
    }

    JSONObject global(String key) throws Exception {
        int a;
        switch (key) {
            case "back": a = GLOBAL_ACTION_BACK; break;
            case "home": a = GLOBAL_ACTION_HOME; break;
            case "recent": a = GLOBAL_ACTION_RECENTS; break;
            case "notifications": a = GLOBAL_ACTION_NOTIFICATIONS; break;
            case "quick_settings": a = GLOBAL_ACTION_QUICK_SETTINGS; break;
            case "lock": a = GLOBAL_ACTION_LOCK_SCREEN; break;
            default: throw new Exception("key must be back, home, recent, notifications, quick_settings or lock");
        }
        performGlobalAction(a);
        return new JSONObject().put("done", key);
    }

    JSONObject openApp(String pkg) throws Exception {
        Intent i = getPackageManager().getLaunchIntentForPackage(pkg);
        if (i == null) throw new Exception("no app " + pkg + "; use apps to list them");
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
        startActivity(i);
        long end = System.currentTimeMillis() + 6000;
        while (System.currentTimeMillis() < end && !pkg.equals(frontPackage())) Thread.sleep(150);
        return new JSONObject().put("done", "open").put("app", frontPackage());
    }

    JSONObject apps() throws Exception {
        PackageManager pm = getPackageManager();
        Intent i = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        JSONArray out = new JSONArray();
        for (ResolveInfo r : pm.queryIntentActivities(i, 0))
            out.put(new JSONObject().put("name", r.loadLabel(pm).toString()).put("package", r.activityInfo.packageName));
        return new JSONObject().put("apps", out);
    }

    private boolean onScreen(String text) {
        AccessibilityNodeInfo r = getRootInActiveWindow();
        if (r == null) return false;
        List<AccessibilityNodeInfo> hits = r.findAccessibilityNodeInfosByText(text);
        for (AccessibilityNodeInfo h : hits) if (h.isVisibleToUser()) return true;
        return false;
    }

    JSONObject waitFor(String text, int timeout) throws Exception {
        long end = System.currentTimeMillis() + timeout * 1000L;
        while (System.currentTimeMillis() < end) {
            if (onScreen(text)) return new JSONObject().put("found", true);
            Thread.sleep(250);
        }
        return new JSONObject().put("found", false);
    }

    JSONObject find(String text, int maxScrolls) throws Exception {
        for (int s = 0; s <= maxScrolls; s++) {
            if (onScreen(text)) return new JSONObject().put("found", true).put("scrolls", s);
            AccessibilityNodeInfo r = getRootInActiveWindow();
            AccessibilityNodeInfo list = r == null ? null : firstScrollable(r, 0);
            if (list == null || !list.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD))
                return new JSONObject().put("found", false).put("scrolls", s);
            Thread.sleep(450);
        }
        return new JSONObject().put("found", false).put("scrolls", maxScrolls);
    }

    private AccessibilityNodeInfo firstScrollable(AccessibilityNodeInfo n, int depth) {
        if (n == null || depth > 40) return null;
        if (n.isScrollable() && n.isVisibleToUser()) return n;
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo f = firstScrollable(n.getChild(i), depth + 1);
            if (f != null) return f;
        }
        return null;
    }

    JSONObject wakeUp() throws Exception {
        PowerManager pm = getSystemService(PowerManager.class);
        @SuppressWarnings("deprecation")
        PowerManager.WakeLock w = pm.newWakeLock(PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP, "mobileuse:wake");
        w.acquire(3000);
        return status();
    }

    // ---------------- owner approval on the phone ----------------

    static synchronized void beginAsk(CountDownLatch latch) {
        askAnswer = null;
        askLatch.set(latch);
    }

    /** First answer wins. Called from the card (main thread) and from Stop. */
    static synchronized void resolveAsk(String answer) {
        if (askLatch.get() == null || askAnswer != null) return;
        askAnswer = answer;
        askLatch.get().countDown();
    }

    JSONObject ask(String text, int timeout, String why, String risk, String title) throws Exception {
        final int wait = timeout <= 0 ? 60 : timeout;
        final String chip = title == null || title.isEmpty() ? "Approve" : title;
        final String because = why == null ? "" : why;
        final String kind = risk == null ? "" : risk;
        CountDownLatch latch = new CountDownLatch(1);
        beginAsk(latch);
        try { wakeUp(); } catch (Exception ignored) { }
        main.post(() -> showApproval(chip, text, because, kind, wait));
        try {
            latch.await(wait, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
            resolveAsk("timeout");
        }
        String answer;
        synchronized (AgentService.class) {
            answer = askAnswer == null ? "timeout" : askAnswer;
            askAnswer = null;
            askLatch.set(null);
        }
        main.post(this::hideApproval);
        if (System.currentTimeMillis() < stoppedUntil)
            throw new Exception("stopped by the owner (Stop button on the phone); ask the owner to tap Resume");
        return new JSONObject().put("answer", answer).put("risk", kind);
    }

    private void showApproval(String title, String what, String why, String risk, int seconds) {
        hideApproval();
        boolean overlay = false;
        try {
            approval = ApprovalOverlay.show(this, title, what, why, risk, seconds);
            overlay = true;
        } catch (Throwable ignored) {
            approval = null;
        }
        notifyAsk(title, what, why, overlay);
    }

    /** The card is how you approve. The notification only mirrors it, plus Deny. Allow is a
     *  fallback for the rare case where the overlay cannot be added. */
    private void notifyAsk(String title, String what, String why, boolean overlayUp) {
        String body = (what == null ? "" : what) + (why == null || why.isEmpty() ? "" : "\n" + why);
        Notification.Builder b = new Notification.Builder(this, CH_ASK)
                .setSmallIcon(android.R.drawable.ic_dialog_alert)
                .setContentTitle(title == null || title.isEmpty() ? "Approve this?" : title)
                .setContentText(what)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setCategory(Notification.CATEGORY_STATUS)
                .setAutoCancel(true);
        if (!overlayUp)
            b.addAction(new Notification.Action.Builder(null, "Allow once", pi(ActionReceiver.ALLOW, 1)).build());
        b.addAction(new Notification.Action.Builder(null, "Deny", pi(ActionReceiver.DENY, 2)).build());
        getSystemService(NotificationManager.class).notify(2, b.build());
    }

    void hideApproval() {
        if (approval != null) {
            approval.dismiss();
            approval = null;
        }
        getSystemService(NotificationManager.class).cancel(2);
    }

    PendingIntent pi(String action, int code) {
        Intent i = new Intent(this, ActionReceiver.class).setAction(action);
        return PendingIntent.getBroadcast(this, code, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    // ---------------- glow + "agent active" notification ----------------

    private void touch() {
        lastCommand = System.currentTimeMillis();
        main.post(() -> {
            showGlow();
            main.removeCallbacks(idleCheck);
            main.postDelayed(idleCheck, GLOW_MS);
        });
    }

    private final Runnable idleCheck = new Runnable() {
        @Override public void run() {
            if (approval != null) {
                main.postDelayed(this, GLOW_MS);
                return;
            }
            if (System.currentTimeMillis() - lastCommand >= GLOW_MS - 50) hideGlow();
        }
    };

    private void showGlow() {
        if (glow != null) return;
        WindowManager wm = getSystemService(WindowManager.class);
        glow = new GlowView(this);
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE | WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                        | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON,
                PixelFormat.TRANSLUCENT);
        p.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
        p.setTitle("PhoneAgentGlow");
        wm.addView(glow, p);
        getSystemService(NotificationManager.class).notify(1, new Notification.Builder(this, CH_ACTIVE)
                .setSmallIcon(android.R.drawable.ic_menu_view)
                .setContentTitle("AI agent is using your phone")
                .setContentText("Tap Stop to halt it right away")
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(null, "Stop", pi(ActionReceiver.STOP, 3)).build())
                .build());
    }

    void hideGlow() {
        if (glow == null) return;
        glow.stop();
        getSystemService(WindowManager.class).removeView(glow);
        glow = null;
        getSystemService(NotificationManager.class).cancel(1);
    }

    void stopAgent() {
        stoppedUntil = System.currentTimeMillis() + 30 * 60 * 1000L;
        resolveAsk("deny");
        main.post(() -> { hideApproval(); hideGlow(); });
        getSystemService(NotificationManager.class).notify(3, new Notification.Builder(this, CH_ACTIVE)
                .setSmallIcon(android.R.drawable.ic_media_pause)
                .setContentTitle("AI agent stopped")
                .setContentText("It can't touch your phone for 30 minutes. Tap Resume to allow it again.")
                .addAction(new Notification.Action.Builder(null, "Resume", pi(ActionReceiver.RESUME, 4)).build())
                .setOngoing(true).build());
    }

    void reconnectLink() {
        if (link != null) link.reconnect();
    }

    void resumeAgent() {
        stoppedUntil = 0;
        getSystemService(NotificationManager.class).cancel(3);
    }
}
