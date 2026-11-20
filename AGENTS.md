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
- The node-aware `get_task` is serialized by an advisory lock
  (`_lock_dispatch` in `alws/crud/build_node.py`). It waits for the lock at
  most `BUILD_NODE_DISPATCH_LOCK_TIMEOUT` seconds and then answers `null`:
  every waiting request holds a database connection, and without the limit
  the pool runs out, pings fail and the nodes look dead. Don't take the lock
  without a timeout.
- A node is dead (its tasks are handed out again) or gone (another instance
  with its name is a restart) only when it was silent while the server was
  working, `last_seen` alone doesn't tell it: after a downtime of the server
  or its database every node has an old `last_seen` and the first node back
  would take the tasks the others are building. `build_nodes.online_since`
  is since when a node comes without a gap longer than
  `BUILD_NODE_OFFLINE_TIMEOUT`, and the earliest one of the online nodes
  (`server_seen_since_query` in `alws/crud/build_nodes.py`) is since when the
  server is known to work. Use `BuildNode.is_silent_for` or
  `dispatchable_task_condition` for such decisions, not `is_online`, which is
  for the UI and the balancing pool only.
- `dispatch_count` of a build task counts only the handouts the node
  confirmed: the task was in its ping or its build_done came. A claim sets
  `ts` and `claimed_at` to the same value, so `ts == claimed_at` of a STARTED
  task means "not confirmed yet" (`unconfirmed_claim_condition` in
  `alws/crud/build_nodes.py`). Code that writes `ts` of a handed-out task has
  to keep this: count the confirmation with `confirmed_dispatch_count()`
  together with the new `ts`, or the lost responses of `get_task` fail
  healthy tasks via `BUILD_NODE_TASK_MAX_DISPATCHES`.
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
