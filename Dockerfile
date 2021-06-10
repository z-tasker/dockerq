FROM python:3.8-slim

RUN mkdir -p /etc/sudoers.d && \  
  addgroup --gid 1000 admin && \
  adduser --disabled-password --gecos "" --uid 1000 --gid 1000 admin && \
  echo "admin ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/admin && chmod 400 /etc/sudoers.d/admin

USER admin
RUN mkdir /home/admin/dockerq
WORKDIR /home/admin/dockerq

ADD requirements.txt /home/admin/dockerq/
RUN pip install -r requirements.txt

ADD ./ /home/admin/dockerq

ENTRYPOINT ["/home/admin/dockerq/entry-point.sh"]
