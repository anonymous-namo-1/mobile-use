package dev.mobileuse.agent;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Buttons in the notifications: Stop / Resume the agent, and Deny (or Allow once, if the card could not be shown). */
public class ActionReceiver extends BroadcastReceiver {
    static final String STOP = "stop", RESUME = "resume", ALLOW = "allow", DENY = "deny";

    @Override public void onReceive(Context c, Intent i) {
        AgentService s = AgentService.instance;
        String a = i.getAction() == null ? "" : i.getAction();
        if (s == null) return;
        switch (a) {
            case STOP: s.stopAgent(); break;
            case RESUME: s.resumeAgent(); break;
            case ALLOW: AgentService.resolveAsk("allow_once"); break;
            case DENY: AgentService.resolveAsk("deny"); break;
            default: break;
        }
    }
}
