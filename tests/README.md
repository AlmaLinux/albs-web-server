# Unit tests
## Content
`conftest.py` - a module which contains all fixtures for unit tests, new fixtures should be placed here (probably can be changed in the future)

`mock_classes.py` - a module which contain base class with `httpx` request method, setup logic for each test suite and HTTP status codes
## How to run tests locally
1. Create `test-almalinux-bs` database
2. Adjust variables in `vars.env`
    ```
    POSTGRES_DB="test-almalinux-bs"
    POSTGRES_PASSWORD="password"
    DATABASE_URL="postgresql+asyncpg://postgres:password@db/test-almalinux-bs"
    PULP_DATABASE_URL="postgresql+psycopg2://postgres:password@db/test-almalinux-bs"
    ```
3. Up docker-compose services
    ```bash
    docker-compose up -d --build --force-recreate --no-deps web_server db
    ```
4. Run `pytest` within `web_server` container
    ```bash
    docker-compose run --no-deps --rm web_server bash -c 'source env/bin/activate && pytest -v --ignore alws/'
    ```
    - we ignore `alws/` directory because it's contains files which names starts with `test*.py`
