# Agent instructions

## Build nodes

- `build_node_name` of every build node must be unique. The server's node
  registry (`build_nodes`, `alws/crud/build_nodes.py`) keeps one row per
  name. Nodes sharing a name are merged into one row: they overwrite each
  other's capacity, version, arches and resources on every ping (observed
  on a test stand: capacity flapped 2↔1 and the node with fewer slots got
  no tasks for 7 minutes), so the balancer counts slots wrongly.
- albs-node derives the default name from the hostname without the last
  two domain labels, so hosts that differ only by domain collide. Set
  `build_node_name` explicitly when configuring or deploying nodes.
- When changing the registration or balancing code, don't rely on unique
  names for safety: a shared name must not lead to double builds or lost
  results. But treat a name shared by two live instances as a
  misconfiguration, not as a case to support.
- The build nodes authenticate with the tokens of build node service users
  (`users.is_build_node`, see "Build node tokens" in README.md and
  `scripts/build_node_token.py`). Such a token works on `/api/v1/build_node/*`
  only, and with its `build_node_name` only if the user is bound to a node.
  The script issues shared tokens without `exp` by default, so revoking the
  user (`--revoke`, `is_active = false`) is the only way to reject one: keep
  the inactive users rejected with 401.
  Keep this in `alws/auth` (`get_current_user`, `get_current_superuser`,
  `get_current_build_node`), not in the routers. Don't issue superuser tokens
  to the nodes: superusers are accepted on `/api/v1/build_node/*` for the
  nodes deployed before only.
