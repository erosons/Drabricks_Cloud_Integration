FROM python:3.9-slim-buster as builder

ARG DEBIAN_FRONTEND=noninteractive
# install git
RUN apt-get update
RUN apt-get install -y git software-properties-common \
    unixodbc \
    unixodbc-dev \
    g++\
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY ./devdir /devdir 

WORKDIR /devdir
RUN pip3 install --upgrade pip
RUN pip3 install --trusted-host=pypi.python.org --trusted-host=pypi.org --trusted-host=files.pythonhosted.org --no-cache-dir -r requirements.txt

FROM apache/airflow:2.6.1-python3.9
USER root
COPY --from=builder /devdir /devdir 
COPY --from=builder /usr/local/lib/python3.9/site-packages /home/airflow/.local/lib/python3.9/site-packages
ARG AIRFLOW_VERSION=2.6.1
ARG CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-3.10.txt"
RUN pip3 install "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"
WORKDIR /devdir
RUN pip3 install cryptography==38.0.4
RUN pip3 install pyodbc
RUN pip3 install attrs==23.1.0
RUN pip3 install --no-cache-dir -q -r requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    openjdk-11-jre-headless \
    vim \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
USER airflow
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64