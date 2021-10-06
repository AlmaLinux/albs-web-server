# al-web-server

# Create new migration
(inside web_server container)
`PYTHONPATH="." alembic --config alws/alembic.ini revision --autogenerate -m "Migration name"`
