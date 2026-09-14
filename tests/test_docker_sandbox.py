from harness.docker_sandbox import DockerSandbox


def test_image_for_uses_default_without_version_hint():
    sandbox = DockerSandbox(default_image="node:22-bookworm")
    assert sandbox._image_for(None) == "node:22-bookworm"
    assert sandbox._image_for({}) == "node:22-bookworm"


def test_image_for_picks_major_version_from_hint():
    sandbox = DockerSandbox()
    assert sandbox._image_for({"TSBENCH_NODE_VERSION": "22.18.0"}) == "node:22-bookworm"
    assert sandbox._image_for({"TSBENCH_NODE_VERSION": "20.11.1"}) == "node:20-bookworm"
    assert sandbox._image_for({"TSBENCH_NODE_VERSION": "24"}) == "node:24-bookworm"
