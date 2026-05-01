FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y openjdk-21-jre-headless wget && \
    rm -rf /var/lib/apt/lists/*

ARG LIQUIBASE_VERSION=4.29.2
RUN wget -q https://github.com/liquibase/liquibase/releases/download/v${LIQUIBASE_VERSION}/liquibase-${LIQUIBASE_VERSION}.tar.gz -O /tmp/liquibase.tar.gz && \
    mkdir -p /opt/liquibase && \
    tar -xzf /tmp/liquibase.tar.gz -C /opt/liquibase && \
    ln -s /opt/liquibase/liquibase /usr/local/bin/liquibase && \
    rm /tmp/liquibase.tar.gz

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY app/liquibase/changelog ./app/changelog
COPY entrypoint.sh .

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
