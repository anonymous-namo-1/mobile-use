package dev.mobileuse.agent;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.View;

/** Pulsing blue glow around the screen edge (touches pass through). */
class GlowView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF r = new RectF();
    private final ValueAnimator pulse = ValueAnimator.ofFloat(0.55f, 1f);
    private float level = 1f;

    GlowView(Context c) {
        super(c);
        paint.setStyle(Paint.Style.STROKE);
        pulse.setDuration(1400);
        pulse.setRepeatMode(ValueAnimator.REVERSE);
        pulse.setRepeatCount(ValueAnimator.INFINITE);
        pulse.addUpdateListener(a -> { level = (float) a.getAnimatedValue(); invalidate(); });
        pulse.start();
    }

    void stop() { pulse.cancel(); }

    @Override protected void onDraw(Canvas c) {
        float w = getWidth(), h = getHeight(), radius = 110f;
        int layers = 14;
        for (int i = 0; i < layers; i++) {   // soft glow: faint strokes fading inwards
            float inset = i * 3.2f, alpha = 1f - i / (float) layers;
            paint.setStrokeWidth(7f);
            paint.setColor(Color.argb((int) (230 * alpha * alpha * level), 40, 140, 255));
            r.set(inset, inset, w - inset, h - inset);
            c.drawRoundRect(r, radius - inset, radius - inset, paint);
        }
        paint.setStrokeWidth(5f);           // bright core line at the very edge
        paint.setColor(Color.argb((int) (255 * level), 120, 200, 255));
        r.set(2, 2, w - 2, h - 2);
        c.drawRoundRect(r, radius, radius, paint);
    }
}
