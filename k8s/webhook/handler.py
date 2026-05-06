"""
Recursant sidecar injection webhook.

A Flask-based mutating admission webhook that injects Recursant sidecar
containers into annotated Pods. Supports both single-sidecar and
multi-sidecar injection patterns.

TLS certs are mounted from a Kubernetes Secret (pre-generated and
included in the Helm chart). The CA bundle is set in the
MutatingWebhookConfiguration template.

Annotations:
  Single sidecar:
    recursant.io/inject-sidecar: "true"
    recursant.io/agent-name: <agent name> (required)
    recursant.io/agent-port: <agent port> (required)
    recursant.io/sidecar-port: <HTTP proxy port> (default 9901)
    recursant.io/a2a-port: <mTLS A2A port> (default 8443)
    recursant.io/sidecar-config: <ConfigMap name> (required)
    recursant.io/cert-secret: <Secret name> (required)

  Multiple sidecars:
    recursant.io/inject-sidecars: <JSON array of sidecar specs>
"""

import base64
import json
import logging
import os
import ssl

from flask import Flask, jsonify, request

logger = logging.getLogger("recursant-webhook")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = Flask(__name__)

SIDECAR_IMAGE = os.environ.get("SIDECAR_IMAGE", "recursant-sidecar:latest")
REGISTRY_URL = os.environ.get(
    "SIDECAR_REGISTRY_URL", "http://recursant-registry:5000"
)
ALREADY_INJECTED_ANNOTATION = "recursant.io/sidecar-injected"


# ---------------------------------------------------------------------------
# Sidecar injection logic
# ---------------------------------------------------------------------------

def _build_sidecar_container(
    name,
    agent_name,
    agent_port,
    sidecar_port,
    a2a_port,
    config_map,
    cert_secret,
    secret_name,
    advertise_host=None,
    local_agents_json=None,
):
    """Build a sidecar container spec."""
    env = [
        {"name": "SIDECAR_PORT", "value": str(sidecar_port)},
        {"name": "SIDECAR_A2A_PORT", "value": str(a2a_port)},
        {"name": "SIDECAR_AGENT_PORT", "value": str(agent_port)},
        {"name": "SIDECAR_AGENT_HOST", "value": "localhost"},
        {"name": "SIDECAR_REGISTRY_URL", "value": REGISTRY_URL},
        {"name": "SIDECAR_AGENT_NAME", "value": agent_name},
        {
            "name": "SIDECAR_REGISTRY_API_KEY",
            "valueFrom": {
                "secretKeyRef": {
                    "name": secret_name,
                    "key": "MESH_API_KEY",
                }
            },
        },
    ]
    if advertise_host:
        env.append({"name": "SIDECAR_ADVERTISE_HOST", "value": advertise_host})
        env.append({"name": "SIDECAR_ADVERTISE_PORT", "value": str(a2a_port)})
    if local_agents_json:
        env.append({"name": "RECURSANT_LOCAL_AGENTS", "value": local_agents_json})

    return {
        "name": name,
        "image": SIDECAR_IMAGE,
        "imagePullPolicy": "IfNotPresent",
        "command": ["python", "-m", "runtime.sidecar", "--config", "/app/recursant-sidecar.yaml"],
        "ports": [
            {"containerPort": sidecar_port, "name": f"http-{sidecar_port}", "protocol": "TCP"},
            {"containerPort": a2a_port, "name": f"a2a-{a2a_port}", "protocol": "TCP"},
        ],
        "env": env,
        "volumeMounts": [
            {
                "name": f"{name}-config",
                "mountPath": "/app/recursant-sidecar.yaml",
                "subPath": "recursant-sidecar.yaml",
            },
            {
                "name": f"{name}-config",
                "mountPath": "/app/agent_card.yaml",
                "subPath": "agent_card.yaml",
            },
            {
                "name": f"{name}-certs",
                "mountPath": "/certs",
                "readOnly": True,
            },
        ],
    }


def _build_volumes(name, config_map, cert_secret):
    """Build volume specs for a sidecar."""
    return [
        {
            "name": f"{name}-config",
            "configMap": {"name": config_map},
        },
        {
            "name": f"{name}-certs",
            "secret": {"secretName": cert_secret},
        },
    ]


def _get_existing_volume_names(pod_spec):
    """Get names of volumes already in the pod spec."""
    volumes = pod_spec.get("volumes") or []
    return {v.get("name") for v in volumes}


def _get_existing_container_names(pod_spec):
    """Get names of containers already in the pod spec."""
    containers = pod_spec.get("containers") or []
    return {c.get("name") for c in containers}


def _is_already_injected(annotations):
    """Check if sidecar has already been injected."""
    return annotations.get(ALREADY_INJECTED_ANNOTATION) == "true"


def _inject_single_sidecar(pod_spec, annotations):
    """Inject a single sidecar container. Returns JSON patches or empty list."""
    patches = []

    agent_name = annotations.get("recursant.io/agent-name")
    agent_port = annotations.get("recursant.io/agent-port")
    if not agent_name or not agent_port:
        logger.warning("Missing required annotations (agent-name, agent-port)")
        return patches

    sidecar_port = int(annotations.get("recursant.io/sidecar-port", "9901"))
    a2a_port = int(annotations.get("recursant.io/a2a-port", "8443"))
    config_map = annotations.get("recursant.io/sidecar-config")
    cert_secret = annotations.get("recursant.io/cert-secret")

    if not config_map or not cert_secret:
        logger.warning("Missing required annotations (sidecar-config, cert-secret)")
        return patches

    secret_name = annotations.get("recursant.io/secret-name", "recursant-secrets")
    advertise_host = annotations.get("recursant.io/advertise-host")
    container_name = "recursant-sidecar"

    if container_name in _get_existing_container_names(pod_spec):
        logger.info(f"Container {container_name} already exists, skipping")
        return patches

    container = _build_sidecar_container(
        name=container_name,
        agent_name=agent_name,
        agent_port=int(agent_port),
        sidecar_port=sidecar_port,
        a2a_port=a2a_port,
        config_map=config_map,
        cert_secret=cert_secret,
        secret_name=secret_name,
        advertise_host=advertise_host,
    )
    volumes = _build_volumes(container_name, config_map, cert_secret)

    # Append container
    containers = pod_spec.get("containers") or []
    patches.append({
        "op": "add",
        "path": f"/spec/containers/{len(containers)}",
        "value": container,
    })

    # Append volumes
    existing_volumes = pod_spec.get("volumes") or []
    existing_names = _get_existing_volume_names(pod_spec)

    # Ensure /spec/volumes exists
    if not existing_volumes:
        patches.append({"op": "add", "path": "/spec/volumes", "value": []})

    for v in volumes:
        if v["name"] not in existing_names:
            patches.append({
                "op": "add",
                "path": "/spec/volumes/-",
                "value": v,
            })

    # Mark as injected
    patches.append({
        "op": "add",
        "path": f"/metadata/annotations/{ALREADY_INJECTED_ANNOTATION.replace('/', '~1')}",
        "value": "true",
    })

    logger.info(
        f"Injecting sidecar for agent '{agent_name}' (ports {sidecar_port}/{a2a_port})"
    )
    return patches


def _inject_multiple_sidecars(pod_spec, annotations):
    """Inject multiple sidecar containers. Returns JSON patches or empty list."""
    patches = []
    sidecars_json = annotations.get("recursant.io/inject-sidecars", "[]")

    try:
        sidecars = json.loads(sidecars_json)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in recursant.io/inject-sidecars annotation")
        return patches

    if not sidecars:
        logger.warning("Empty sidecars list in annotation")
        return patches

    secret_name = annotations.get("recursant.io/secret-name", "recursant-secrets")
    existing_container_names = _get_existing_container_names(pod_spec)
    existing_volume_names = _get_existing_volume_names(pod_spec)
    containers = pod_spec.get("containers") or []
    existing_volumes = pod_spec.get("volumes") or []

    container_idx = len(containers)
    need_volumes_init = not existing_volumes

    for sidecar_spec in sidecars:
        name = sidecar_spec.get("name", "default")
        container_name = f"recursant-sidecar-{name}"

        if container_name in existing_container_names:
            logger.info(f"Container {container_name} already exists, skipping")
            continue

        agent_name = sidecar_spec.get("agentName", name)
        agent_port = int(sidecar_spec.get("agentPort", 5010))
        sidecar_port = int(sidecar_spec.get("sidecarPort", 9901))
        a2a_port = int(sidecar_spec.get("a2aPort", 8443))
        config_map = sidecar_spec.get("config")
        cert_secret = sidecar_spec.get("certs")

        if not config_map or not cert_secret:
            logger.warning(f"Skipping sidecar '{name}': missing config or certs")
            continue

        advertise_host = sidecar_spec.get("advertiseHost")

        # Build local agents list for intra-pod governed routing
        # Each sidecar gets the full list of all agents in the pod
        local_agents_json = json.dumps([
            {"agentName": s.get("agentName", s.get("name", "")),
             "agentPort": int(s.get("agentPort", 5010))}
            for s in sidecars
        ])

        container = _build_sidecar_container(
            name=container_name,
            agent_name=agent_name,
            agent_port=agent_port,
            sidecar_port=sidecar_port,
            a2a_port=a2a_port,
            config_map=config_map,
            cert_secret=cert_secret,
            secret_name=secret_name,
            advertise_host=advertise_host,
            local_agents_json=local_agents_json,
        )

        patches.append({
            "op": "add",
            "path": f"/spec/containers/{container_idx}",
            "value": container,
        })
        container_idx += 1

        volumes = _build_volumes(container_name, config_map, cert_secret)
        for v in volumes:
            if v["name"] not in existing_volume_names:
                patches.append({
                    "op": "add",
                    "path": "/spec/volumes/-",
                    "value": v,
                })
                existing_volume_names.add(v["name"])

        logger.info(
            f"Injecting sidecar '{container_name}' for agent '{agent_name}' "
            f"(ports {sidecar_port}/{a2a_port})"
        )

    if patches:
        # Prepend volumes init if needed
        if need_volumes_init:
            patches.insert(0, {"op": "add", "path": "/spec/volumes", "value": []})
        patches.append({
            "op": "add",
            "path": f"/metadata/annotations/{ALREADY_INJECTED_ANNOTATION.replace('/', '~1')}",
            "value": "true",
        })

    return patches


# ---------------------------------------------------------------------------
# Flask webhook endpoint
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/mutate", methods=["POST"])
def mutate():
    """Handle AdmissionReview requests."""
    admission_review = request.get_json()
    if not admission_review:
        return jsonify({"error": "empty body"}), 400

    uid = admission_review.get("request", {}).get("uid", "")
    pod = admission_review.get("request", {}).get("object", {})
    annotations = pod.get("metadata", {}).get("annotations") or {}
    pod_spec = pod.get("spec", {})

    patches = []

    if _is_already_injected(annotations):
        logger.info("Sidecar already injected, skipping")
    elif annotations.get("recursant.io/inject-sidecar") == "true":
        patches = _inject_single_sidecar(pod_spec, annotations)
    elif "recursant.io/inject-sidecars" in annotations:
        patches = _inject_multiple_sidecars(pod_spec, annotations)

    response = {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "response": {
            "uid": uid,
            "allowed": True,
        },
    }

    if patches:
        patch_bytes = json.dumps(patches).encode()
        response["response"]["patchType"] = "JSONPatch"
        response["response"]["patch"] = base64.b64encode(patch_bytes).decode()

    return jsonify(response)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    port = int(os.environ.get("WEBHOOK_PORT", "8443"))
    cert_path = os.environ.get("TLS_CERT_PATH", "/certs/tls.crt")
    key_path = os.environ.get("TLS_KEY_PATH", "/certs/tls.key")

    logger.info(f"Starting webhook server on port {port}...")
    logger.info(f"TLS cert: {cert_path}, key: {key_path}")

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(cert_path, key_path)
    app.run(host="0.0.0.0", port=port, ssl_context=ssl_ctx)


if __name__ == "__main__":
    main()
