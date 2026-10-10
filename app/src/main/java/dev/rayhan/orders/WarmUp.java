package dev.rayhan.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Simulates a slow warm-up (loading caches, connecting to dependencies, JIT warm-up).
 *
 * The HTTP port is already open during warm-up, but the app is not ready to serve:
 * business endpoints return 503, and WarmUpHealthIndicator keeps the readiness probe DOWN.
 * This is exactly the situation where a missing readinessProbe causes failed requests.
 */
@Component
public class WarmUp {

    private static final Logger log = LoggerFactory.getLogger(WarmUp.class);

    private final long warmUpSeconds;
    private final AtomicBoolean warm = new AtomicBoolean(false);

    public WarmUp(@Value("${app.warmup-seconds:0}") long warmUpSeconds) {
        this.warmUpSeconds = warmUpSeconds;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void startWarmUp() {
        if (warmUpSeconds <= 0) {
            warm.set(true);
            return;
        }
        log.info("Port is open, warming up for {}s (readiness DOWN)", warmUpSeconds);
        Thread.ofVirtual().start(() -> {
            try {
                Thread.sleep(warmUpSeconds * 1000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            warm.set(true);
            log.info("Warm-up finished (readiness UP)");
        });
    }

    public boolean isWarm() {
        return warm.get();
    }
}
