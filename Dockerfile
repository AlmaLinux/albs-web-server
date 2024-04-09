FROM almalinux/9-base:latest

RUN <<EOT
  set -ex
  dnf upgrade -y
  dnf install -y git modulemd-tools libmodulemd python3-libmodulemd python3-gobject
  dnf clean all
EOT

WORKDIR /code

COPY requirements.txt .
RUN <<EOT
  set -ex
  python3 -m ensurepip
  pip3 install -r requirements.txt
  rm requirements.txt
EOT

ADD --chmod=755 https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh /
