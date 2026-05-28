from datetime import datetime, timezone

from .config import NODE_ID


# Reports the identity and health of this Model A server node.
class NodeStatus:
    def __init__(self) -> None:
        self._node_id = NODE_ID

    def health(self) -> dict:
        return {
            "node_id": self._node_id,
            "cluster_role": "active-active server node",
            "status": "healthy",
            "accepts_safe_reads": True,
            "writes_must_be_gateway_leader_routed": True,
            "cluster_mode": "Model A: active-active read scaling with leader-routed writes.",
            "participates_in_active_active_cluster": True,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


node_status = NodeStatus()
