## Development

### Run infrastructure

```bash
# Run PostgreSQL + Redis
docker compose -f docker-compose.dev.yml up -d

# Stop (data is preserved)
docker compose -f docker-compose.dev.yml stop

# Restart
docker compose -f docker-compose.dev.yml restart

# Stop and completely delete data (reset DB and Redis)
docker compose -f docker-compose.dev.yml down -v

# View logs
docker compose -f docker-compose.dev.yml logs -f

# Access in psql
docker compose -f docker-compose.dev.yml exec db psql -U bot -d vacancy_bot

# Access in redis-cli
docker compose -f docker-compose.dev.yml exec redis redis-cli
```
