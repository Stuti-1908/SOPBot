FROM caddy:2-alpine
COPY index.html /srv/index.html
EXPOSE 80
CMD ["caddy", "file-server", "--root", "/srv", "--listen", ":80"]
