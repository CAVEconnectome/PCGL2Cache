FROM caveconnectome/pychunkedgraph:base_042124
ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV GIT_SSL_NO_VERIFY=1
ENV CHUNKEDGRAPH_VERSION=2

RUN mkdir -p /home/nginx/.cloudvolume/secrets && chown -R nginx /home/nginx && usermod -d /home/nginx -s /bin/bash nginx

COPY requirements.txt .
RUN pip install --upgrade --no-cache-dir -r requirements.txt \
    && pip install --upgrade git+https://github.com/CAVEconnectome/PyChunkedGraph.git@main \
    && pip install --upgrade git+https://github.com/seung-lab/KVDbClient.git@main

COPY . /app