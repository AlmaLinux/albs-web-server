# Unit tests
## Content
`conftest.py` - a module where setups pytest plugins and contains some base fixtures

`fixtures/` - a directory with pytest fixtures, new module should be also added in `conftest.pytest_plugins`

`mock_classes.py` - a module which contain base class with `httpx` request method, setup logic for each test suite and HTTP status codes
## How to run tests locally
1. Create `test_vars.env` in the root folder of project
2. Adjust variables in `test_vars.env`
    ```
    POSTGRES_DB="test-almalinux-bs"
    POSTGRES_PASSWORD="password"
    DATABASE_URL="postgresql+asyncpg://postgres:password@db/test-almalinux-bs"
    SYNC_DATABASE_URL="postgresql+psycopg2://postgres:password@db/test-almalinux-bs"
    PULP_DATABASE_URL="postgresql+psycopg2://postgres:password@db/test-almalinux-bs"
    GITHUB_CLIENT="test-github-client"
    GITHUB_CLIENT_SECRET="test-github-secret"
    ALTS_TOKEN="test"
    JWT_SECRET="test"
    ```
    also if you don’t have `vars.env` created, you need to create it and fill it out
3. Up docker-compose services. Before starting docker, make sure that you have local postgres disabled
    ```bash
    docker-compose up -d --no-deps web_server db
    ```
4. Run `pytest` within `web_server` container
    ```bash
    docker-compose run --rm web_server_tests
    ```
    - we ignore `alws/` directory because it's contains files which names starts with `test*.py`
