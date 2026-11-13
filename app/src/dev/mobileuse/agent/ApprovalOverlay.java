package dev.mobileuse.agent;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.RectF;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * The on-phone approval card. A tap does not approve: the owner drags the thumb
 * from the left of the slider to the right. "Once" and "This session" only choose
 * which grant that slide creates. Deny is a tap, and the timer denies on its own.
 * The card sits at the bottom in the same blue as the glow, and does not cover the
 * notification shade, so Stop keeps working.
 */
final class ApprovalOverlay {
    final View root;
    final Handler handler;
    final Runnable tick;
    boolean dismissed;
    int left;

    private ApprovalOverlay(View root, Handler handler, Runnable tick, int seconds) {
        this.root = root;
        this.handler = handler;
        this.tick = tick;
        this.left = seconds;
    }

    static ApprovalOverlay show(AgentService svc, String title, String what, String why, String risk, int seconds) {
        float d = svc.getResources().getDisplayMetrics().density;
        Handler handler = svc.main;
        int accent = riskColor(risk);

        LinearLayout card = new LinearLayout(svc);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setFilterTouchesWhenObscured(true);
        int pad = dp(d, 16);
        card.setPadding(pad, dp(d, 14), pad, dp(d, 12));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xF0121828);
        bg.setCornerRadius(dp(d, 22));
        bg.setStroke(dp(d, 2), 0xFF7EC8FF);
        card.setBackground(bg);

        LinearLayout head = new LinearLayout(svc);
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(Gravity.CENTER_VERTICAL);

        TextView chip = new TextView(svc);
        chip.setText(title == null || title.isEmpty() ? "Approve" : title);
        chip.setTextColor(0xFF071018);
        chip.setTextSize(12);
        chip.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        chip.setPadding(dp(d, 10), dp(d, 4), dp(d, 10), dp(d, 4));
        GradientDrawable chipBg = new GradientDrawable();
        chipBg.setCornerRadius(dp(d, 20));
        chipBg.setColor(accent);
        chip.setBackground(chipBg);

        TextView timer = new TextView(svc);
        timer.setText(clock(seconds));
        timer.setTextColor(0xFF9AD0FF);
        timer.setTextSize(16);
        timer.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        timer.setGravity(Gravity.END);
        LinearLayout.LayoutParams timerLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        timerLp.leftMargin = dp(d, 12);

        head.addView(chip);
        head.addView(timer, timerLp);
        card.addView(head);

        TextView whatView = body(svc, what, 17, 0xFFF4F8FF);
        whatView.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams whatLp = lp();
        whatLp.topMargin = dp(d, 12);
        card.addView(whatView, whatLp);

        if (why != null && !why.isEmpty()) {
            TextView whyView = body(svc, why, 14, 0xFFC5D4EA);
            LinearLayout.LayoutParams whyLp = lp();
            whyLp.topMargin = dp(d, 6);
            card.addView(whyView, whyLp);
        }

        final boolean[] session = new boolean[]{false};
        TextView once = modeChip(svc, d, "Once", true);
        TextView sess = modeChip(svc, d, "This session", false);
        once.setOnClickListener(v -> {
            session[0] = false;
            paintMode(once, true);
            paintMode(sess, false);
        });
        sess.setOnClickListener(v -> {
            session[0] = true;
            paintMode(once, false);
            paintMode(sess, true);
        });
        LinearLayout modes = new LinearLayout(svc);
        modes.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams chipLp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        chipLp.rightMargin = dp(d, 8);
        modes.addView(once, chipLp);
        modes.addView(sess, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        LinearLayout.LayoutParams modesLp = lp();
        modesLp.topMargin = dp(d, 14);
        card.addView(modes, modesLp);

        SlideRail slide = new SlideRail(svc, d, () ->
                AgentService.resolveAsk(session[0] ? "allow_session" : "allow_once"));
        LinearLayout.LayoutParams slideLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(d, 52));
        slideLp.topMargin = dp(d, 12);
        card.addView(slide, slideLp);

        TextView hint = body(svc, "A tap will not approve. Doing nothing denies when the timer ends.", 12, 0xFF8EA3BE);
        LinearLayout.LayoutParams hintLp = lp();
        hintLp.topMargin = dp(d, 8);
        card.addView(hint, hintLp);

        TextView deny = new TextView(svc);
        deny.setText("Deny");
        deny.setTextColor(0xFFFF8B9A);
        deny.setTextSize(16);
        deny.setGravity(Gravity.CENTER);
        deny.setPadding(0, dp(d, 12), 0, dp(d, 4));
        deny.setOnClickListener(v -> AgentService.resolveAsk("deny"));
        card.addView(deny, lp());

        LinearLayout root = new LinearLayout(svc);
        root.setPadding(dp(d, 12), 0, dp(d, 12), dp(d, 14));
        root.addView(card, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        WindowManager wm = svc.getSystemService(WindowManager.class);
        WindowManager.LayoutParams p = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                        | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED,
                PixelFormat.TRANSLUCENT);
        p.gravity = Gravity.BOTTOM;
        p.setTitle("MobileUseApproval");
        wm.addView(root, p);

        ApprovalOverlay[] box = new ApprovalOverlay[1];
        Runnable tick = new Runnable() {
            @Override public void run() {
                ApprovalOverlay self = box[0];
                if (self == null || self.dismissed) return;
                self.left -= 1;
                if (self.left <= 0) {
                    timer.setText("0:00");
                    AgentService.resolveAsk("timeout");
                    return;
                }
                timer.setText(clock(self.left));
                handler.postDelayed(this, 1000);
            }
        };
        box[0] = new ApprovalOverlay(root, handler, tick, seconds);
        handler.postDelayed(tick, 1000);
        return box[0];
    }

    void dismiss() {
        if (dismissed) return;
        dismissed = true;
        handler.removeCallbacks(tick);
        try {
            WindowManager wm = (WindowManager) root.getContext().getSystemService(AgentService.WINDOW_SERVICE);
            wm.removeView(root);
        } catch (Throwable ignored) { }
    }

    private static int riskColor(String risk) {
        if ("payment".equals(risk) || "password".equals(risk)) return 0xFFFFB15A;
        if ("delete".equals(risk)) return 0xFFFF8B9A;
        return 0xFF7EC8FF;
    }

    private static TextView body(AgentService svc, String text, int sp, int color) {
        TextView v = new TextView(svc);
        v.setText(text == null ? "" : text);
        v.setTextSize(sp);
        v.setTextColor(color);
        return v;
    }

    private static TextView modeChip(AgentService svc, float d, String label, boolean on) {
        TextView v = new TextView(svc);
        v.setText(label);
        v.setGravity(Gravity.CENTER);
        v.setTextSize(14);
        v.setPadding(dp(d, 8), dp(d, 10), dp(d, 8), dp(d, 10));
        paintMode(v, on);
        return v;
    }

    private static void paintMode(TextView v, boolean on) {
        GradientDrawable g = new GradientDrawable();
        g.setCornerRadius(v.getResources().getDisplayMetrics().density * 14);
        g.setColor(on ? 0xFF2B7FFF : 0xFF243044);
        v.setBackground(g);
        v.setTextColor(on ? Color.WHITE : 0xFFD5E4F7);
    }

    private static LinearLayout.LayoutParams lp() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private static int dp(float density, int value) {
        return Math.round(value * density);
    }

    private static String clock(int seconds) {
        int s = Math.max(0, seconds);
        return s / 60 + ":" + (s % 60 < 10 ? "0" : "") + (s % 60);
    }

    /** Thumb starts on the left. Only a drag that begins on the thumb and reaches the end approves. */
    private static final class SlideRail extends View {
        private final float density;
        private final Paint track = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint thumb = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint label = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Runnable onDone;
        private float progress;
        private boolean drag;
        private boolean fired;

        SlideRail(AgentService svc, float density, Runnable onDone) {
            super(svc);
            this.density = density;
            this.onDone = onDone;
            track.setColor(0xFF243044);
            fill.setColor(0xFF1E6FE0);
            thumb.setColor(0xFF9AD0FF);
            label.setColor(0xFFF4F8FF);
            label.setTextAlign(Paint.Align.CENTER);
            label.setFakeBoldText(true);
            setClickable(true);
        }

        @Override public boolean onTouchEvent(MotionEvent e) {
            if (fired) return true;
            float h = getHeight();
            float travel = Math.max(1f, getWidth() - h);
            float thumbX = h / 2f + travel * progress;
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    drag = Math.abs(e.getX() - thumbX) <= h * 0.7f;
                    return drag;
                case MotionEvent.ACTION_MOVE:
                    if (!drag) return false;
                    progress = clamp((e.getX() - h / 2f) / travel);
                    invalidate();
                    return true;
                case MotionEvent.ACTION_UP:
                    if (drag && progress >= 0.92f) {
                        progress = 1f;
                        invalidate();
                        fired = true;
                        performHapticFeedback(HapticFeedbackConstants.CONFIRM);
                        onDone.run();
                    } else {
                        progress = 0f;
                        invalidate();
                    }
                    drag = false;
                    return true;
                case MotionEvent.ACTION_CANCEL:
                    drag = false;
                    progress = 0f;
                    invalidate();
                    return true;
                default:
                    return drag;
            }
        }

        @Override protected void onDraw(Canvas c) {
            float w = getWidth(), h = getHeight(), r = h / 2f;
            RectF all = new RectF(0, 0, w, h);
            c.drawRoundRect(all, r, r, track);
            float cx = r + (w - h) * progress;
            if (progress > 0.01f) {
                c.drawRoundRect(new RectF(0, 0, Math.min(w, cx + r), h), r, r, fill);
            }
            label.setTextSize(h * 0.32f);
            label.setColor(progress > 0.55f ? Color.WHITE : 0xFFD5E4F7);
            c.drawText("Slide to approve", w / 2f, h / 2f - (label.descent() + label.ascent()) / 2f, label);
            c.drawCircle(cx, r, r - 4f * density, thumb);
        }

        private static float clamp(float v) {
            return v < 0f ? 0f : Math.min(1f, v);
        }
    }
}
