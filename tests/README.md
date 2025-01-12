# Unit tests
## Content
`conftest.py` - a module where setups pytest plugins and contains some base fixtures

`fixtures/` - a directory with pytest fixtures, new module should be also added in `conftest.pytest_plugins`

`mock_classes.py` - a module which contain base class with `httpx` request method, setup logic for each test suite and HTTP status codes

`export_new_errata_rec.py` - a helper module for exporting NewErrataRecords from a DB to json file.

## How to run tests locally
1. Adjust variables in `vars.env`
    ```
    POSTGRES_DB="test-almalinux-bs"
    POSTGRES_PASSWORD="password"
    DATABASE_URL="postgresql+asyncpg://postgres:password@test_db/test-almalinux-bs"
    SYNC_DATABASE_URL="postgresql+psycopg2://postgres:password@test_db/test-almalinux-bs"
    PULP_DATABASE_URL="postgresql+psycopg2://postgres:password@test_db/test-almalinux-bs"
    ```
   or use `test-vars.env` in the `tests` folder
   ```bash
   ln -sf tests/test-vars.env vars.env
   ```
2. Start the `test_db` service
    ```bash
    docker compose up -d test_db
    ```

3. To run packages_exporter tests start `sign-file` service and prepare GPG keys
    ```bash
    . tests/prepare_gpg_key.sh
    docker compose up -d sign_file
    ```

4. Update `tests/samples/new_errata_records.json`:
    Needed only on major changes in `NewErrataRecord` model that affect OVAL generation.

    Note: In order to export data you'll need DB with some data,\
    ideally the data must be as similar to production as possible
    ```bash
    export SQLALCHEMY_URL="postgresql+psycopg2://<your-db-address>"
    python3 tests/export_new_errata_rec.py
    ```
    Also, you'll need to update `tests/samples/test_oval.xml`.\
    For that uncomment block inside the test case in `tests/test_oval/test_oval_generation.py` file

5. Run `pytest` within `web_server_tests` container
    ```bash
    docker compose run --rm web_server_tests pytest -v
    ```
