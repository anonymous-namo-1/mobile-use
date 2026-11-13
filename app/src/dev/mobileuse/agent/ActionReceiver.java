package dev.mobileuse.agent;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

import java.util.concurrent.CountDownLatch;

/** Buttons in the notifications: Stop / Resume the agent, Allow / Deny a request. */
public class ActionReceiver extends BroadcastReceiver {
    static final String STOP = "stop", RESUME = "resume", ALLOW = "allow", DENY = "deny";

    @Override public void onReceive(Context c, Intent i) {
        AgentService s = AgentService.instance;
        String a = i.getAction() == null ? "" : i.getAction();
        if (s == null) return;
        switch (a) {
            case STOP: s.stopAgent(); break;
            case RESUME: s.resumeAgent(); break;
            case ALLOW:
            case DENY:
                AgentService.askAnswer = a.equals(ALLOW);
                CountDownLatch l = AgentService.askLatch.get();
                if (l != null) l.countDown();
                break;
        }
    }
}
