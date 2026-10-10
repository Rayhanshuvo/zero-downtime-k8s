# ---- build stage: compile the jar with Maven ----
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

# ---- runtime stage: only a JRE and the jar ----
FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd --system --uid 10001 app
COPY --from=build /src/target/orders-api.jar app.jar
USER 10001
EXPOSE 8080
# exec form: java runs as PID 1 and receives SIGTERM directly from Kubernetes
# small, fixed footprint so several pods fit on a ~2 GB lab node
ENTRYPOINT ["java", "-Xmx200m", "-Xss512k", "-XX:+UseSerialGC", "-jar", "app.jar"]
