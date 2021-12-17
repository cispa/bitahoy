# pull official base image
FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt


COPY dependencies/backend_lib_python /tmp/backend_lib_python
RUN cd /tmp/backend_lib_python && python setup.py install
RUN rm -rf /tmp/backend_lib_python

COPY src .git*/modules/dependencies/backend_lib_python/HEAD /app

# set work directory
WORKDIR /app


# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1


EXPOSE 50000-60000