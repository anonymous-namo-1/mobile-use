package dev.mobileuse.agent;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Set the server address and key. Only the shell (adb) may send this:
 *  adb shell am broadcast -a dev.mobileuse.agent.CONFIG -n dev.mobileuse.agent/.ConfigReceiver \
 *      --es host 100.x.y.z --ei port 8765 --es key SECRET */
public class ConfigReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context c, Intent i) {
        Link.prefs(c).edit()
                .putString("host", i.getStringExtra("host"))
                .putInt("port", i.getIntExtra("port", 0))
                .putString("key", i.getStringExtra("key"))
                .apply();
        if (AgentService.instance != null) AgentService.instance.reconnectLink();
        setResultData("saved");
    }
}
