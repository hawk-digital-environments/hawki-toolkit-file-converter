# Upgrading

## Docker Deployment

The Docker container no longer listens on port `8001`, but on port `80` by default (if not explicitly configured otherwise). Just like the main HAWKI container, the image is now based on [python-nginx](https://github.com/Neunerlei/docker-images/blob/main/docs/python-nginx.md) and provides nginx out of the box. To keep all existing configuration intact, we can simply map the new internal port `80` to the old external port `8001` in the Docker setup. This way, you can continue to access the API at `http://localhost:8001` without any changes on your side, while benefiting from the improved Docker setup under the hood.

### How to upgrade

#### Docker compose

The upgrade is fairly simple, especially if you are using the provided `docker-compose` setup. You just need to update the image tag and the port mapping in your `docker-compose.yml` file. Here is an example of how to do this:

```yaml
services:
  file-converter:
    image: digitalenvironments/hawki-toolkit-file-converter:latest
    ports:
      - "8001:80" # <-- This was "8001:8001" before
    environment:
      - F_API_KEY=Your-secret-api-key
    restart: unless-stopped
```

Start the updated container (ensure to pull): 

```bash
docker compose pull file-converter
docker compose up -d file-converter
```

#### Standalone Container

If you are running the container standalone, you first need to stop and remove the existing container, and then run a new one with the updated image and port mapping:

```bash
# Find the container ID
docker ps | grep hawki-toolkit-file-converter

# Stop and remove the container
docker stop <container_id>
docker rm <container_id>

# Restart the container with the new image and port mapping
docker run --rm -d -p 8001:80 -e F_API_KEY="Your-secret-api-key" digitalenvironments/hawki-toolkit-file-converter:latest
```
