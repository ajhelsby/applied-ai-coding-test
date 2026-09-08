"""Internal DAG representation for workflow traversal."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from app.domain.models.workflow import Workflow


class DAGNode:
    """Internal immutable node representation used by DAG traversal."""

    def __init__(
        self,
        node_id: str,
        handler: str,
        config: Mapping[str, Any],
        dependencies: tuple[str, ...],
    ) -> None:
        self._id = node_id
        self._handler = handler
        self._config = MappingProxyType(dict(config))
        self._dependencies = dependencies
        self._dependants: tuple[str, ...] = ()

    @property
    def node_id(self) -> str:
        return self._id

    @property
    def handler(self) -> str:
        return self._handler

    @property
    def config(self) -> Mapping[str, Any]:
        return self._config

    @property
    def dependencies(self) -> tuple[str, ...]:
        return self._dependencies

    @property
    def dependants(self) -> tuple[str, ...]:
        return self._dependants

    def _set_dependants(self, dependants: tuple[str, ...]) -> None:
        self._dependants = dependants


class DAG:
    """Internal graph with efficient node lookup and adjacency traversal."""

    def __init__(
        self,
        nodes_by_id: dict[str, DAGNode],
        root_node_ids: tuple[str, ...],
        terminal_node_ids: tuple[str, ...],
    ) -> None:
        self._nodes_by_id = nodes_by_id
        self._root_node_ids = root_node_ids
        self._terminal_node_ids = terminal_node_ids

    def get_node(self, node_id: str) -> DAGNode:
        return self._nodes_by_id[node_id]

    def get_dependencies(self, node_id: str) -> tuple[DAGNode, ...]:
        node = self.get_node(node_id)
        return tuple(self.get_node(dependency_id) for dependency_id in node.dependencies)

    def get_dependants(self, node_id: str) -> tuple[DAGNode, ...]:
        node = self.get_node(node_id)
        return tuple(self.get_node(dependant_id) for dependant_id in node.dependants)

    def get_roots(self) -> tuple[DAGNode, ...]:
        return tuple(self.get_node(node_id) for node_id in self._root_node_ids)

    def get_terminals(self) -> tuple[DAGNode, ...]:
        return tuple(self.get_node(node_id) for node_id in self._terminal_node_ids)

    @classmethod
    def from_workflow(cls, workflow: Workflow) -> DAG:
        nodes_by_id: dict[str, DAGNode] = {}
        dependants_by_id: dict[str, list[str]] = {}

        for node in workflow.dag.nodes:
            dependencies = tuple(node.dependencies)
            nodes_by_id[node.id] = DAGNode(
                node_id=node.id,
                handler=node.handler,
                config=node.config,
                dependencies=dependencies,
            )
            dependants_by_id[node.id] = []

        for node in workflow.dag.nodes:
            for dependency_id in node.dependencies:
                dependants_by_id[dependency_id].append(node.id)

        for node_id, dag_node in nodes_by_id.items():
            dag_node._set_dependants(tuple(dependants_by_id[node_id]))

        root_node_ids = tuple(
            node_id for node_id, dag_node in nodes_by_id.items() if not dag_node.dependencies
        )
        terminal_node_ids = tuple(
            node_id for node_id, dag_node in nodes_by_id.items() if not dag_node.dependants
        )
        return cls(
            nodes_by_id=nodes_by_id,
            root_node_ids=root_node_ids,
            terminal_node_ids=terminal_node_ids,
        )
