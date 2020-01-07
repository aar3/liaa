FROM ubuntu:18.04

RUN apt-get update && apt-get install

RUN apt-get install -y \
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

RUN mkdir -p /var/www/kademlia
WORKDIR /var/www/kademlia
COPY . /var/www/kademlia

ENV WORKDIR=/var/www/kademlia
ENV APPDIR=$WORKDIR/kademlia

RUN rm -rf ./venv
RUN python3.7 -m pip install --upgrade virtualenv
RUN virtualenv -p $(which python3.7) ./venv
ENV PATH="${WORKDIR}/venv/bin:${PATH}"

RUN python -m pip install --upgrade -r .requirements.lock

CMD ["python", "app.py"]
