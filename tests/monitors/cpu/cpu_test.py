import os
import pytest

from tests.kubernetes.utils import (
    run_k8s_monitors_test,
    get_metrics_from_doc,
    get_dims_from_doc,
)

pytestmark = [pytest.mark.collectd, pytest.mark.cpu, pytest.mark.monitor_without_endpoints]


@pytest.mark.k8s
@pytest.mark.kubernetes
def test_cpu_in_k8s(agent_image, minikube, k8s_test_timeout, k8s_namespace):
    monitors = [
        {"type": "collectd/cpu"},
        {"type": "collectd/signalfx-metadata"}
    ]
    run_k8s_monitors_test(
        agent_image,
        minikube,
        monitors,
        namespace=k8s_namespace,
        expected_metrics=get_metrics_from_doc("collectd-cpu.md"),
        expected_dims=get_dims_from_doc("collectd-cpu.md"),
        test_timeout=k8s_test_timeout)
