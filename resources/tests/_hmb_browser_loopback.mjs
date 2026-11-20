import { randomInt } from "node:crypto";
import { once } from "node:events";

// An OS-assigned port on Windows can be forbidden by Chromium (e.g. 6697).
// Bind the actual server directly so concurrent fixtures cannot claim its port.
export async function listenBrowserSafeLoopback(server) {
  for (let attempt = 1; ; attempt++) {
    const port = randomInt(20001, 60000);
    try {
      server.listen(port, "127.0.0.1");
      await once(server, "listening");
      return { port: server.address().port, attempts: attempt };
    } catch (error) {
      if (attempt >= 16 || !["EADDRINUSE", "EACCES", "EPERM"].includes(error.code)) throw error;
    }
  }
}
