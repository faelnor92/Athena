import sys
import os
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def test_terminal_ws_unauthorized_if_auth_active():
    import routers.auth
    original_auth_active = routers.auth._auth_active
    routers.auth._auth_active = lambda: True
    
    try:
        client = TestClient(server.app)
        # S'attend à ce que le websocket ferme immédiatement la connexion car le token est absent/invalide
        with pytest.raises(Exception):
            with client.websocket_connect("/api/terminal/ws?token=invalid_token") as websocket:
                websocket.send_text("echo test\n")
                websocket.receive_bytes()
    finally:
        routers.auth._auth_active = original_auth_active


def test_terminal_ws_connects_and_runs_bash():
    import routers.auth
    original_auth_active = routers.auth._auth_active
    routers.auth._auth_active = lambda: False
    
    try:
        client = TestClient(server.app)
        with client.websocket_connect("/api/terminal/ws") as websocket:
            # Envoie une commande simple à exécuter
            websocket.send_text("echo hello_terminal_test\n")
            
            found_output = False
            for _ in range(50):
                try:
                    data = websocket.receive_bytes()
                    text = data.decode("utf-8", errors="ignore")
                    if "hello_terminal_test" in text:
                        found_output = True
                        break
                except Exception:
                    break
            
            assert found_output, "Impossible de trouver la sortie attendue dans la session terminal"
    finally:
        routers.auth._auth_active = original_auth_active


def test_terminal_ws_uses_dev_container_when_enabled():
    from unittest import mock
    from tools import dev_container
    import subprocess
    import routers

    original_auth_active = routers.auth._auth_active
    routers.auth._auth_active = lambda: False

    # Mock dev_container functions
    mock_enabled = mock.patch.object(dev_container, "enabled", return_value=True)
    mock_ensure = mock.patch.object(dev_container, "ensure", return_value=("mock-athena-dev-container", None))
    
    # We want to mock subprocess.Popen to capture the command it was called with
    captured_args = []
    original_popen = subprocess.Popen

    def mock_popen(args, *a, **k):
        captured_args.append(args)
        # We can't let it run docker exec since it's mock, so we fall back or mock a process.
        # But we want to simulate Popen success/mock. Let's just spawn a simple bash command instead of docker exec
        # to let the PTY run, but verify that it attempted to run docker exec.
        # Actually, let's just return a mock Popen or call the original Popen with a harmless command
        # like ["/bin/bash", "-c", "echo mock_docker_running && sleep 1"]
        return original_popen(["/bin/bash", "-c", "echo mock_docker_running && sleep 1"], *a, **k)

    try:
        with mock_enabled, mock_ensure, mock.patch("subprocess.Popen", side_effect=mock_popen):
            client = TestClient(server.app)
            with client.websocket_connect("/api/terminal/ws") as websocket:
                # Wait a bit or try to read
                for _ in range(50):
                    try:
                        data = websocket.receive_bytes()
                        text = data.decode("utf-8", errors="ignore")
                        if "mock_docker_running" in text:
                            break
                    except Exception:
                        break
        
        # Verify that subprocess.Popen was called with docker exec and mock-athena-dev-container
        assert len(captured_args) > 0
        cmd = captured_args[0]
        assert cmd[0] == "docker"
        assert "exec" in cmd
        assert "mock-athena-dev-container" in cmd
    finally:
        routers.auth._auth_active = original_auth_active
