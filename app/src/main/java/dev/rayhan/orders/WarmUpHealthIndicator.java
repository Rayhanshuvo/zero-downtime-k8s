package dev.rayhan.orders;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

/**
 * Reported as "warmUp" and included in the readiness group (see application.yml),
 * so /actuator/health/readiness returns 503 until warm-up is done.
 * Liveness is NOT affected: a warming-up app is alive, just not ready.
 */
@Component
public class WarmUpHealthIndicator implements HealthIndicator {

    private final WarmUp warmUp;

    public WarmUpHealthIndicator(WarmUp warmUp) {
        this.warmUp = warmUp;
    }

    @Override
    public Health health() {
        return warmUp.isWarm() ? Health.up().build() : Health.down().withDetail("reason", "warming up").build();
    }
}
