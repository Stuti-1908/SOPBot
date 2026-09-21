FROM caddy:2-alpine
COPY index.html sopbot.html workflowiq.html /srv/
COPY assets/ /srv/assets/
EXPOSE 80
CMD ["caddy", "file-server", "--root", "/srv", "--listen", ":80"]
