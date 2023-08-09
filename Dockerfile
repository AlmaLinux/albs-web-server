FROM fedora:34

RUN curl https://packages.codenotary.org/codenotary.repo -o /etc/yum.repos.d/codenotary.repo
RUN mkdir -p /code && \
    yum update -y && \
    yum install --enablerepo="codenotary-repo" cas python3-virtualenv python39 libmodulemd python3-libmodulemd \
                python3-libmodulemd1 modulemd-tools python-gobject git -y && \
    yum clean all
RUN curl https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh -o wait_for_it.sh && chmod +x wait_for_it.sh
COPY requirements.txt /code/requirements.txt
RUN cd /code && virtualenv -p python3.9 --system-site-packages env && source env/bin/activate \
    && pip3 install --upgrade pip && pip3 install -r /code/requirements.txt --no-cache-dir
WORKDIR /code
CMD ["/bin/bash", "-c", "source env/bin/activate && pip3 install --upgrade pip && pip3 install -r requirements.txt --no-cache-dir && uvicorn --workers 4 --host 0.0.0.0 alws.app:app"]
