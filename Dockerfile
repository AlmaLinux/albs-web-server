FROM almalinux:8

RUN mkdir -p /code && \
    yum update -y && \
    yum install python3-virtualenv python38 -y && \
    yum clean all
RUN curl https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh -o wait_for_it.sh && chmod +x wait_for_it.sh
COPY requirements.txt /tmp/requirements.txt
RUN cd /code && virtualenv -p python3.8 env && source env/bin/activate \
    && pip3 install -r /tmp/requirements.txt --no-cache-dir
COPY alws /code/alws
COPY tests /code/tests
WORKDIR /code
CMD ["/bin/bash", "-c", "source env/bin/activate && uvicorn --workers 4 --host 0.0.0.0 alws.app:app"]
