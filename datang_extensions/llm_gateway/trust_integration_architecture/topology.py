"""Offline topology and data-flow validation for R2C-F."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_integration_architecture.contracts import (
    DISALLOWED_FLOW_CLASSES,
    REQUIRED_DATA_CLASSES,
    REQUIRED_NODES,
    architecture_error,
    hash_value,
    require_safe_id,
    scan_architecture_surface,
    sorted_records,
)


def _as_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _class_errors(classes: Any, field_path: str, code: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(classes, list) or not classes:
        return [architecture_error(code, "data classes must be a non-empty list", field_path=field_path)]
    for data_class in classes:
        if data_class not in REQUIRED_DATA_CLASSES:
            errors.append(architecture_error(code, "data class is not declared in the contract", field_path=field_path))
        if data_class in DISALLOWED_FLOW_CLASSES:
            errors.append(architecture_error("undeclared_data_flow", "restricted material is not allowed in planned flows", field_path=field_path))
    return errors


def validate_deployment_topology(topology: Mapping[str, Any]) -> tuple[str, str, str, list[dict[str, str]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_architecture_surface(topology, code="invalid_deployment_topology", field_path="deployment_topology")
    if forbidden:
        errors.append(forbidden)
    if topology.get("deployment_topology_version") != "1.0":
        errors.append(architecture_error("invalid_deployment_topology", "unsupported topology version", field_path="deployment_topology_version"))
    if topology.get("status") != "draft_for_architecture_review":
        errors.append(architecture_error("invalid_deployment_topology", "topology must remain draft", field_path="status"))
    if topology.get("environment") != "sandbox":
        errors.append(architecture_error("invalid_deployment_topology", "only sandbox architecture review is allowed", field_path="environment"))
    if topology.get("deployment_approved") is not False:
        errors.append(architecture_error("invalid_deployment_topology", "deployment approval is outside R2C-F", field_path="deployment_approved"))
    if topology.get("network_configuration_applied") is not False:
        errors.append(architecture_error("network_connection_must_be_disabled", "network configuration must remain unapplied", field_path="network_configuration_applied"))
    if topology.get("real_endpoints_present") is not False:
        errors.append(architecture_error("real_endpoint_not_allowed", "real endpoint evidence is outside R2C-F", field_path="real_endpoints_present"))

    nodes = _as_records(topology.get("nodes"))
    node_ids = {str(node.get("node_id", "")) for node in nodes}
    if not REQUIRED_NODES.issubset(node_ids):
        errors.append(architecture_error("invalid_deployment_topology", "required logical nodes are missing", field_path="nodes"))
    for index, node in enumerate(nodes):
        require_safe_id(node.get("node_id"), errors, "invalid_deployment_topology", f"nodes[{index}].node_id")
        if node.get("deployment_state") != "planned":
            errors.append(architecture_error("invalid_deployment_topology", "nodes must remain planned", field_path=f"nodes[{index}].deployment_state"))
        if not node.get("trust_zone"):
            errors.append(architecture_error("invalid_deployment_topology", "node trust zone is required", field_path=f"nodes[{index}].trust_zone"))

    edges = _as_records(topology.get("edges"))
    for index, edge in enumerate(edges):
        require_safe_id(edge.get("edge_id"), errors, "invalid_deployment_topology", f"edges[{index}].edge_id")
        if edge.get("connection_state") != "disabled":
            errors.append(architecture_error("network_connection_must_be_disabled", "planned connections must remain disabled", field_path=f"edges[{index}].connection_state"))
        if edge.get("public_callback_allowed") is not False:
            errors.append(architecture_error("network_connection_must_be_disabled", "public callbacks are not allowed", field_path=f"edges[{index}].public_callback_allowed"))
        if edge.get("audited_path_required") is not True:
            errors.append(architecture_error("invalid_deployment_topology", "audited path is required", field_path=f"edges[{index}].audited_path_required"))
        if edge.get("source_node_id") not in node_ids or edge.get("target_node_id") not in node_ids:
            errors.append(architecture_error("invalid_deployment_topology", "edge endpoints must reference declared nodes", field_path=f"edges[{index}]"))
        errors.extend(_class_errors(edge.get("data_classes"), f"edges[{index}].data_classes", "invalid_deployment_topology"))

    flows = _as_records(topology.get("data_flows"))
    for index, flow in enumerate(flows):
        require_safe_id(flow.get("flow_id"), errors, "invalid_deployment_topology", f"data_flows[{index}].flow_id")
        if flow.get("declared") is not True:
            errors.append(architecture_error("undeclared_data_flow", "each data flow must be explicitly declared", field_path=f"data_flows[{index}].declared"))
        if flow.get("source_node_id") not in node_ids or flow.get("destination_node_id") not in node_ids:
            errors.append(architecture_error("undeclared_data_flow", "flow endpoints must reference declared nodes", field_path=f"data_flows[{index}]"))
        if flow.get("retention_class") not in {"redacted_metadata_only", "not_allowed"}:
            errors.append(architecture_error("undeclared_data_flow", "retention class must be declared", field_path=f"data_flows[{index}].retention_class"))
        errors.extend(_class_errors(flow.get("data_classes"), f"data_flows[{index}].data_classes", "undeclared_data_flow"))

    policies = _as_records(topology.get("data_class_policies"))
    policy_classes = {str(item.get("data_class", "")) for item in policies}
    if not REQUIRED_DATA_CLASSES.issubset(policy_classes):
        errors.append(architecture_error("invalid_deployment_topology", "all data classes require policies", field_path="data_class_policies"))
    for index, policy in enumerate(policies):
        if policy.get("real_material_present") is not False:
            errors.append(architecture_error("invalid_deployment_topology", "real material must not be present", field_path=f"data_class_policies[{index}].real_material_present"))
        if policy.get("data_class") in DISALLOWED_FLOW_CLASSES and policy.get("retention_class") != "not_allowed":
            errors.append(architecture_error("invalid_deployment_topology", "restricted material retention must be not_allowed", field_path=f"data_class_policies[{index}].retention_class"))

    zones = _as_records(topology.get("trust_zones"))
    for index, zone in enumerate(zones):
        if not zone.get("trust_zone"):
            errors.append(architecture_error("invalid_deployment_topology", "trust zone id is required", field_path=f"trust_zones[{index}].trust_zone"))
        errors.extend(_class_errors(zone.get("data_classes_allowed"), f"trust_zones[{index}].data_classes_allowed", "invalid_deployment_topology"))

    canonical_topology = dict(topology)
    canonical_topology["nodes"] = sorted_records(nodes, "node_id")
    canonical_topology["edges"] = sorted_records(edges, "edge_id")
    canonical_topology["data_flows"] = sorted_records(flows, "flow_id")
    canonical_topology["data_class_policies"] = sorted_records(policies, "data_class")
    canonical_topology["trust_zones"] = sorted_records(zones, "trust_zone")
    trust_zone_model = {"nodes": canonical_topology["nodes"], "trust_zones": canonical_topology["trust_zones"], "data_class_policies": canonical_topology["data_class_policies"]}
    return hash_value(canonical_topology), hash_value(trust_zone_model), hash_value(canonical_topology["data_flows"]), errors, trust_zone_model, canonical_topology["edges"], canonical_topology["data_flows"]
