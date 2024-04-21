FROM caveconnectome/pychunkedgraph:base_042124

ENV GIT_SSL_NO_VERIFY=1
RUN mkdir -p /home/nginx/.cloudvolume/secrets && chown -R nginx /home/nginx && usermod -d /home/nginx -s /bin/bash nginx

COPY . /app
RUN pip install --no-cache-dir --upgrade -r requirements.txt \
    && pip install --upgrade git+https://github.com/CAVEconnectome/PyChunkedGraph.git@pcgv1 \
    && pip install --upgrade git+https://github.com/seung-lab/KVDbClient.git@main