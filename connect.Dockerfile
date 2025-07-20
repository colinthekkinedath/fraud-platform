# connect.Dockerfile
FROM confluentinc/cp-kafka-connect:7.6.0

USER root

# Install curl + unzip (UBI uses microdnf)
RUN microdnf install -y curl unzip && microdnf clean all

# Pick a version that exists. For the original Aiven connector repo:
ARG AIVEN_VERSION=2.19.0
RUN curl -L -o /tmp/aiven-s3.zip \
    https://github.com/Aiven-Open/cloud-storage-connectors-for-apache-kafka/releases/download/v3.4.0/s3-sink-connector-for-apache-kafka-3.4.0.zip \
 && unzip /tmp/aiven-s3.zip -d /usr/share/java/aiven-s3 \
 && rm /tmp/aiven-s3.zip

# OR (comment previous RUN, uncomment next) if you prefer the new “Aiven-Open/cloud-storage…” bundle:
# ARG AIVEN_OPEN_VERSION=3.4.0
# RUN curl -L -o /tmp/aiven-open-s3.zip \
#       https://github.com/Aiven-Open/cloud-storage-connectors-for-apache-kafka/releases/download/v${AIVEN_OPEN_VERSION}/s3-sink-connector-for-apache-kafka-${AIVEN_OPEN_VERSION}.zip \
#  && unzip /tmp/aiven-open-s3.zip -d /usr/share/java/aiven-s3 \
#  && rm /tmp/aiven-open-s3.zip

# Drop back to non-root (Confluent uses appuser)
USER appuser

ENV CONNECT_PLUGIN_PATH="/usr/share/java,/usr/share/confluent-hub-components,/usr/share/java/aiven-s3"