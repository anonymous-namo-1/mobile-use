package dev.mobileuse.agent;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

/** Keeps a connection out to the owner's server (over Tailscale) and runs its commands.
 *  Protocol: newline-delimited JSON. Phone sends {"hello": key, "model": ...}; then the
 *  server sends {"id", "cmd", "args"} and the phone answers {"id", "ok", "result"|"error"}. */
class Link extends Thread {
    private static Link current;
    private volatile AgentService svc;
    private volatile boolean running = true;
    private volatile Socket sock;

    private Link(AgentService svc) {
        super("mobile-use-link");
        this.svc = svc;
        setDaemon(true);
    }

    /** The single connection for this phone: reuse it if it's alive, else start one. */
    static synchronized Link ensure(AgentService svc) {
        if (current != null && current.isAlive() && current.running) {
            current.svc = svc;
            return current;
        }
        current = new Link(svc);
        current.start();
        return current;
    }

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("config", Context.MODE_PRIVATE);
    }

    void shutdown() {
        running = false;
        synchronized (Link.class) { if (current == this) current = null; }
        try { if (sock != null) sock.close(); } catch (Exception ignored) { }
        interrupt();
    }

    /** Drop the current connection so it reconnects with new settings. */
    void reconnect() {
        try { if (sock != null) sock.close(); } catch (Exception ignored) { }
    }

    @Override public void run() {
        long backoff = 1000;
        while (running) {
            SharedPreferences p = prefs(svc);
            String host = p.getString("host", ""), key = p.getString("key", "");
            int port = p.getInt("port", 0);
            if (host.isEmpty() || port == 0 || key.isEmpty()) { pause(3000); continue; }
            try (Socket s = new Socket()) {
                sock = s;
                s.connect(new InetSocketAddress(host, port), 10000);
                s.setTcpNoDelay(true);
                s.setKeepAlive(true);
                s.setSoTimeout(90000); // the server pings every 25 s
                OutputStream out = s.getOutputStream();
                BufferedReader in = new BufferedReader(new InputStreamReader(s.getInputStream(), StandardCharsets.UTF_8));
                send(out, new JSONObject().put("hello", key).put("model", android.os.Build.MODEL).put("version", 1));
                backoff = 1000;
                String line;
                while (running && (line = in.readLine()) != null) {
                    JSONObject req = new JSONObject(line);
                    JSONObject res = new JSONObject().put("id", req.opt("id"));
                    try {
                        res.put("ok", true).put("result", svc.handle(req.getString("cmd"), req.optJSONObject("args") == null ? new JSONObject() : req.getJSONObject("args")));
                    } catch (Throwable e) {
                        res.put("ok", false).put("error", String.valueOf(e.getMessage()));
                    }
                    send(out, res);
                }
            } catch (Exception e) {
                // network down, server restarting, Tailscale off: try again shortly
            }
            pause(backoff);
            backoff = Math.min(backoff * 2, 30000);
        }
    }

    private static synchronized void send(OutputStream out, JSONObject o) throws Exception {
        out.write((o.toString() + "\n").getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    private static void pause(long ms) {
        try { Thread.sleep(ms); } catch (InterruptedException ignored) { }
    }
}
