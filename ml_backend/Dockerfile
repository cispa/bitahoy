# pull official base image
FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

RUN apt-get install -y git
RUN mkdir /root/.ssh/

RUN echo '[redacted-9]\n\
' > /root/.ssh/id_ed25519

RUN chmod 400 /root/.ssh/id_ed25519
RUN ssh-keyscan github.com >> /root/.ssh/known_hosts
RUN cd /tmp
ADD "https://www.random.org/cgi-bin/randbyte?nbytes=10&format=h" skipcache
RUN git clone backend_lib_python.git
RUN cd backend_lib_python && python setup.py install
RUN rm /root/.ssh/id_ed25519

COPY src /app

# set work directory
WORKDIR /app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
