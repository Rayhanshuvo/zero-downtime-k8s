package dev.rayhan.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

@RestController
@RequestMapping("/api")
public class OrdersController {

    private final WarmUp warmUp;
    private final String version;
    private final String podName;
    private final Instant startedAt = Instant.now();
    private final AtomicLong served = new AtomicLong();

    public OrdersController(WarmUp warmUp,
                            @Value("${app.version:v1}") String version,
                            @Value("${POD_NAME:${HOSTNAME:local}}") String podName) {
        this.warmUp = warmUp;
        this.version = version;
        this.podName = podName;
    }

    /** Which version and which pod answered. The load tester uses this to show a rollout live. */
    @GetMapping("/info")
    public Map<String, Object> info() {
        requireWarm();
        return Map.of(
                "version", version,
                "pod", podName,
                "startedAt", startedAt.toString(),
                "served", served.incrementAndGet());
    }

    /**
     * Simulates a request that takes time (a DB call, a downstream call).
     * Used to show whether in-flight requests survive a pod shutdown.
     */
    @GetMapping("/work")
    public Map<String, Object> work(@RequestParam(defaultValue = "200") long ms) throws InterruptedException {
        requireWarm();
        Thread.sleep(Math.min(ms, 10_000));
        return Map.of("version", version, "pod", podName, "tookMs", ms);
    }

    /** Burns CPU so the HorizontalPodAutoscaler has something to react to. */
    @GetMapping("/cpu")
    public Map<String, Object> cpu(@RequestParam(defaultValue = "100") long ms) {
        requireWarm();
        long end = System.nanoTime() + Math.min(ms, 5_000) * 1_000_000;
        double x = 0;
        while (System.nanoTime() < end) {
            x += Math.sqrt(x + 1);
        }
        return Map.of("version", version, "pod", podName, "burnedMs", ms, "x", (long) x % 10);
    }

    private void requireWarm() {
        if (!warmUp.isWarm()) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "warming up");
        }
    }
}
