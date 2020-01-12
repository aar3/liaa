FROM ubuntu:18.04

RUN apt-get update && \
   apt-get install -y \
   python \
   python3-pip \
   python3.7 \
   python3.7-dev \
   python3.7-venv \
   ca-certificates \
   curl \
   git \
   apt-transport-https \
   software-properties-common

RUN mkdir -p /var/www/liaa
WORKDIR /var/www/liaa
COPY . /var/www/liaa

ENV ROOTDIR=/var/www/liaa

RUN rm -rf ./venv
RUN python3.7 -m venv ${ROOTDIR}/virtualenv
ENV PATH="${ROOTDIR}/virtualenv/bin:${PATH}"

RUN python -m pip install --upgrade -r .requirements.lock --trusted-host pypi.python.org

CMD ["python", "app.py", "-p", "8000", "-n", "False"]
